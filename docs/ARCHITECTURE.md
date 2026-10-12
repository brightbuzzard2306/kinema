# Architecture

Kinema is three layers with one rule: **the recommender decides which movies are shown; Claude only interprets the request and words the reply.**

```
Browser (Next.js)  ──HTTP/JSON──▶  FastAPI  ──▶  ChatService ──▶ Recommender (popularity / content / collaborative / hybrid)
  chat, cards, profile                │              │
  localStorage: session id            │              ├──▶ ClaudeService (optional)  ──▶ Anthropic API
                                      │              └──▶ rule-based parser (always available)
                                      ├──▶ SessionStore  (data/cache/sessions.json)
                                      └──▶ PosterService (optional)  ──▶ TMDB API
```

## Responsibilities

| Component | File(s) | Does | Never does |
|---|---|---|---|
| **Frontend** | `frontend/src` | Renders chat, cards, taste drawer, evaluation page; sends messages/feedback; optimistic UI with rollback | Holds secrets; computes recommendations |
| **API** | `backend/app/main.py` | Validation, consistent errors, CORS, routing | Business logic |
| **Orchestrator** | `backend/app/service.py` | One chat turn: interpret → update profile → rank → compose reply; profile edits; feedback | Choose movies itself |
| **Recommender** | `backend/app/engine/*` | Filtering, scoring, score fusion, explanations | Talk to the network |
| **NLU** | `backend/app/nlu.py` | Rule-based parser; validates *any* NLU output (Claude's or the rules') against the catalogue | Trust a title or genre it hasn't verified |
| **Claude layer** | `backend/app/llm.py` | `parse` (message → structured preferences) and `compose` (facts → short reply + follow-ups) | Pick, rank or invent movies |
| **Sessions** | `backend/app/sessions.py` | Per-browser profile, shown movies, last cards, short history | Accounts or passwords |
| **Posters** | `backend/app/posters.py` | Optional TMDB poster URLs, cached on disk | Block the app when absent |
| **Evaluation** | `backend/app/evaluation.py`, `scripts/run_evaluation.py` | Offline split, metrics, tuning, report | Share state with the live app |

## One chat turn

1. `POST /chat {session_id, message}` → length/format validation.
2. Load the session (created lazily from the client-generated id).
3. **Interpret.** If an Anthropic key exists, Claude returns JSON constrained by a schema (genres limited to the dataset's real genres). On *any* failure (no key, timeout, rate limit, refusal, malformed JSON) the rule parser handles the message and the response says why (`llm.mode = "fallback"`).
4. **Validate.** Every title is resolved against the real catalogue (exact → article-insensitive → fuzzy ≥ 0.86); unknown titles are dropped and reported to the user. Numbers are clamped; runtime limits are flagged *unsupported* because MovieLens has no runtime data.
5. **Update the profile** (liked/disliked titles, excluded genres, focus genres, rating/year/novelty). A new topic clears stale soft constraints so old filters don't silently carry over; every change is returned in `changes` and shown to the user.
6. **Rank** with the recommender (see `ALGORITHMS.md`). Previously shown movies are excluded; if the pool is exhausted, repeats are allowed and disclosed.
7. **Compose.** With Claude: facts only (titles, ratings, reasons) go in; a reply and three follow-ups come out. The reply is rejected if it contains any number not present in the facts. Without Claude: a template built from the same facts.
8. The cards, notes, profile and LLM status go back to the UI. Cards carry the engine's reasons and the score breakdown, so "Why this?" is always exactly what the engine computed.

### Streaming (progressive delivery)

`/chat/stream` runs the same `service.chat(...)` in a worker thread and passes it an `emit` callback; the events go through a queue to the HTTP response (`backend/app/streaming.py`). The picks are sent **before** the reply is written, so the cards appear ~2 s earlier while Claude is still framing the answer. This is deliberately *not* token streaming: Claude's reply is validated (grounded numbers, no invented titles) before it is shown, so showing half-written text would defeat that check. The browser client (`frontend/src/lib/stream.ts`) falls back to the plain endpoints if the stream cannot be opened, so a proxy that buffers or blocks SSE costs the animation, not the feature. Errors inside the stream are sent as a generic `error` event without internals.

## Project dialog and team data (frontend)

`ProjectDialog` (About + Team tabs) is opened from anywhere with `openProject("about" | "team")` (`src/lib/project.ts`, a tiny external store). Team content comes from `src/lib/team.ts`: placeholders by default, or a validated `NEXT_PUBLIC_TEAM` JSON list so names can stay out of the repository.

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Dataset size, whether Claude/TMDB are configured (never returns keys) |
| `GET /meta` | Genres, strategies, limits |
| `GET /movies?q=&limit=` · `GET /movies/{id}` | Title search (autocomplete) and lookup |
| `GET /posters?ids=` | Poster URLs (all `null` without a TMDB key) |
| `POST /chat` | One conversational turn |
| `POST /recommend` | Picks from the current profile, optionally "more like" a movie (`anchor_movie_id`) |
| `POST /compare` | Same request ranked by all four strategies (read-only; used by the comparison panel) |
| `POST /chat/stream` · `POST /recommend/stream` | The same turn as `/chat` and `/recommend`, delivered as Server-Sent Events: `step` (interpret → rank → write), then `cards` as soon as the picks are ranked, then `done` (the full response, identical to the non-streaming endpoint) or `error`. A `: keep-alive` comment is sent every 10 s so proxies don't close an idle connection |
| `GET /llm/status` | Cached live check that the Claude key and model actually work (what the status badge reads) |
| `POST /feedback` | like / dislike / clear (idempotent) |
| `GET/PUT /sessions/{id}/profile` | Read / edit the taste profile |
| `GET /sessions/{id}` | Restore the UI after a reload |
| `POST /sessions/{id}/reset?keep_profile=` | New conversation |
| `GET /evaluation` | The real offline evaluation report |

Errors always look like `{"error": {"code", "message"}}`; stack traces stay in the server log. CORS allows only `FRONTEND_ORIGIN`.

## Data & state

* **Dataset:** MovieLens `ml-latest-small` (9,742 movies, 100,836 ratings, 610 users, 3,683 tag applications), downloaded and validated by `scripts/setup_data.py` (zip-slip-safe extraction, schema checks).
* **Models** are built once at startup (about 2 s) and held in memory; per-request ranking takes a few milliseconds.
* **Sessions** live in memory and are mirrored atomically to `data/cache/sessions.json`; corrupt entries are skipped, not fatal.
* **Frontend state** lives in `WorkspaceProvider`; the only browser storage is the random session id.

## Security notes

* Keys are read from the environment in the backend only; nothing secret is `NEXT_PUBLIC_*`. `.env` is git-ignored; `.env.example` has placeholders.
* User text reaches Claude inside `<message>` tags with a system rule to treat it as data.
* **Security audit hardening (2026-10-12):** the access code is only ever compared on `POST /access/verify` (8 wrong guesses per visitor, 60 per site, per 10 minutes). It returns a derived token (PBKDF2-SHA256, 200k rounds, stateless) which is what the browser keeps and sends; every other route accepts only that token, so the code cannot be guessed through them. Visitor identity comes from `CF-Connecting-IP` / the last `X-Forwarded-For` entry, never the first (forgeable). Request bodies above 128 KB are refused with 413 before anything reads them (`BodyLimitMiddleware`), API responses carry `nosniff`, `X-Frame-Options: DENY`, `no-store` and HSTS, HTTP-client logs are silenced so URLs (and TMDB's key) never reach the log, `GET /sessions/{id}` is read-only, and a hosted copy (Render sets `RENDER`) refuses to start without `ACCESS_CODE` unless `ALLOW_PUBLIC=true`.
* **Public deployment safeguards** (`backend/app/protect.py`, wired in `main.py`): an optional shared `ACCESS_CODE` (constant-time comparison, wrong guesses counted per visitor and locked out after 8 in 10 minutes, API docs switched off while it is set), per-visitor sliding-window rate limits (stricter on the routes that can cost a Claude call), and a daily cap on Claude calls after which replies fall back to the offline parser. All in memory, single instance, by design; the hard spending limit belongs in the Anthropic console.
* CORS lists the exact site origins (`FRONTEND_ORIGIN`, comma-separated) and allows only the `Content-Type` and `X-Access-Code` request headers.
* Inputs are bounded (message length, result counts, list sizes, id formats). Logs contain no chat text or keys.
