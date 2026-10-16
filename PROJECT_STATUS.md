# Project status

Last updated after the final verification pass. **PASS** = tested as described. **PARTIAL** = works but not fully verified. **BLOCKED** = needs something I did not have.

## Acceptance criteria

| # | Criterion | Status | Evidence / note |
|---|---|---|---|
| 1 | Premium, responsive UI | **PASS** (desktop + mobile) | Checked in a real browser at 1024 px and 375 px: no horizontal overflow, cards/drawer/dialogs usable. Tablet width not separately checked. |
| 2 | Real MovieLens dataset | **PASS** | `ml-latest-small` downloaded, validated, 9,742 movies / 100,836 ratings; fresh-download path re-tested from an empty folder. |
| 3 | Popularity baseline | **PASS** | Bayesian average; unit-tested; evaluated. |
| 4 | Content-based engine | **PASS** | TF-IDF (genres/tags/title) + cosine; tests for similarity, missing genres/tags, grounded reasons. |
| 5 | Collaborative filtering | **PASS** | Item-item top-N; tests for neighbours, exclusion of rated movies, cold fallback. |
| 6 | Hybrid ranking | **PASS** | Normalised components, per-candidate weight redistribution, weight regimes; tests. |
| 7 | Cold-start onboarding | **PASS** | Genre + movie picker verified in the browser (genre → search → pick → first picks); no-history popularity fallback tested. |
| 8 | Working multi-turn conversation | **PASS** | Verified in the browser and by 40+ API tests (follow-ups, "second one", reject, reset, explain). |
| 9 | Secure server-side Claude integration | **PASS (live, Haiku 4.5)** | Official SDK, key from env only, structured output, typed failure handling. Verified live with `claude-haiku-4-5`: status check, parsing the brief's example requests, replies. Live testing found and fixed: missing workspace header, `effort` rejected by Haiku, Claude adding opinions about films, and over-inferring genres/exclusions. **Not tested live with the default `claude-opus-5-5`.** |
| 10 | Functional no-API-key fallback | **PASS** | The whole browser session ran with no key; parser + templates; badge says "Offline mode". |
| 11 | Grounded explanations | **PASS** | Reasons come from data; Claude replies rejected if they contain a number not in the facts; tests. |
| 12 | Working likes / dislikes | **PASS** | Browser: like persisted to backend, rollback on failure; tests for idempotence and exclusion. |
| 13 | Preference-aware later recommendations | **PASS** | Tests: dislike never returns, like shapes "more like", new topic clears stale filters. |
| 14 | Functional filters | **PARTIAL** | Strategy and genre chips verified in the browser; min-rating, years, novelty verified through the API/tests but the slider/year inputs were not clicked in a browser. |
| 15 | Real evaluation metrics for all methods | **PASS** | `reports/evaluation.md/json` from `scripts.run_evaluation`: random, popularity, content, collaborative, hybrid, plus a few-likes regime and paired confidence intervals. |
| 16 | No fabricated evaluation results | **PASS** | The report text is generated from the JSON; a line that over-claimed (few-likes weights) was found and corrected. |
| 17 | Automated backend tests | **PASS** | 154 passed. |
| 18 | Frontend lint / type-check / build | **PASS** | `npm run lint`, `npx tsc --noEmit`, `npm run build` all clean. |
| 19 | End-to-end smoke test | **PASS (manual)** | Journey driven through a real browser: load → example prompt → cards → Why sheet → like → typed request → profile drawer → failure + retry → backend-down screen → evaluation page. **No automated browser suite exists.** |
| 20 | Clear setup instructions | **PASS** | README commands run: `./start.sh --setup`, tests, build, dataset download. |
| 21 | Architecture & algorithm docs | **PASS** | `docs/ARCHITECTURE.md`, `docs/ALGORITHMS.md`. |
| 22 | Viva preparation | **PASS** | `docs/VIVA_PREPARATION.md` (25 Q&A, numbers from the real run, demo script). |
| 23 | Optional posters (TMDB) | **PASS (live)** | Real posters load via the backend with the user's TMDB key (cached); typographic fallback verified when absent; TMDB attribution shown. |
| 26 | Strategy comparison view | **PASS** | `POST /compare` + panel: four lists for the same profile, honest fallbacks when there is no taste signal, real offline scores, cross-list highlighting, detail sheet on click. Verified in the browser (desktop + mobile, error + retry) and by 5 API tests. |
| 25 | React Bits UI elements | **PASS** | LightRays, BlurText, ShinyText, LogoLoop, ClickSpark, CountUp, RubberSegment, Dock, Magnet integrated (vendored with licence; credited). Focus order fixed for the looping ticker. |
| 27 | Streaming replies | **PASS** | `POST /chat/stream` and `/recommend/stream` (SSE): step → cards → done|error, keep-alive, validation before the stream opens, generic error events. 7 API tests incl. "same result as the non-streaming endpoint". Real Chrome run: picks visible ~2.5 s, reply ~4.8 s (Claude Haiku). Blocking the stream endpoint falls back to `/chat` and still shows 6 cards. Progressive delivery, not token streaming (see ARCHITECTURE). |
| 28 | Badge, About card, rotating line, first-visit tour, credit line | **PASS (desktop + phone, headless Chrome)** | Live status text follows the real request stage; About card shows the real dataset numbers and restarts the tour; tour spotlight aligned to its target within 0 px on all four steps (desktop), waits quietly until cards exist, Esc/Skip/Done persist; badge hidden and no horizontal overflow at 390 px. Credit text comes from `NEXT_PUBLIC_*` env and is hidden when unset. |
| 29 | Deployment readiness | **PASS (verified locally; not yet live)** | Docker image built and run with Render-free limits (512 MB, 0.1 CPU): ~230 MB resident (was 601 MB before the memory fix), models ready in ~30 s. Verified inside the container: access code, CORS for the real domain, streaming, rate limiting, HEAD /health. In a real browser: "waking the server" state, access screen (wrong/right code), reload keeps unlock, rotated code asks again, friendly rate-limit message. 18 new tests. Live Render/Vercel/domain checks come after the first deploy. |
| 30 | Navbar, About pill, tour reliability | **PASS (headless Chrome, 360-1440 px)** | After user feedback ("tour doesn't work, About not visible, navbar useless"): the About pill is now a visible bordered pill with an info icon at every width (it was hidden below 768 px and faint above); the navbar has real labelled actions (Compare, Taste with badge, Evaluation, Tour, Claude status, New chat) with an active state, and fits at 360 px; the tour has a "Show me" step that runs an example, and if its target isn't on screen (no results yet, or a saved mid-tour position) it points at the prompt and offers to create results instead of silently hiding; it can be restarted from the navbar. The About card scrolls inside small screens. |
| 31 | Project dialog (About + Team), decluttered navbar | **PASS (headless Chrome, 360-1440 px)** | "RS MINI PROJECT" moved from the navbar to a hero eyebrow (decrypt effect, rotates with the real dataset numbers, opens the dialog); navbar is Compare / Taste / Evaluation / Project / Claude; the live reading→ranking→writing status moved to a chip above the prompt. Project dialog: About tab + Team tab (React Bits SpotlightCard, BlurText, ShinyText; arrow-key tabs, Esc closes, works on the evaluation page). Team content is placeholder data in `src/lib/team.ts` or `NEXT_PUBLIC_TEAM`. |
| 32 | Real team details | **PASS (local; not yet pushed)** | Team tab, footer credit and guide card now show the real team and guide (from the project cover page), with the guide's photo (`frontend/public/team/guide.jpg`). Verified in headless Chrome at 1440 and 390 px; photo loads; no console errors. College name was inferred from the course code prefix (DJS23...) and the project folder name, not printed on the cover page excerpt. |
| 33 | Security audit and fixes | **PASS (fixes verified locally; live re-check after deploy)** | Audit of code, dependencies (pip-audit and npm audit: 0 known vulnerabilities), repo history (no secrets) and the live API. Found and fixed: unlimited access-code guessing through normal routes; lockout bypass by forging `X-Forwarded-For`; unauthenticated oversized bodies read into memory before the access check (60 MB added ~230 MB, enough to crash Render's 512 MB); TMDB key written to logs; missing browser-protection headers; read-only session lookups; Anthropic error text shown to visitors; fail-closed startup on hosted deployments. 9 regression tests (163 total). |
| 34 | NLP Lab (second course): spelling correction of titles | **PASS (local; not yet pushed)** | From-scratch noisy-channel corrector: Damerau-Levenshtein, BK-tree, add-k bigram LM, Viterbi; library baseline `difflib`; `/nlp` page with the candidate lattice and the evaluation; `reports/nlp_spellcheck.md`; 13 tests (176 total). Honest results: 100% vs difflib 88.3% on 1-edit typos of catalogue titles, but little gain on held-out titles. See docs/NLP_PROJECT.md. |
| 24 | Accessibility | **PARTIAL** | Semantic markup, labelled controls (card buttons name their movie), focus rings, reduced-motion CSS, Radix dialogs with focus trapping, dark-mode contrast by design. No automated audit or screen-reader pass. |

## Deployment hardening found during verification

A production-only bug: the minifier dropped the standard `backdrop-filter` when both it and `-webkit-backdrop-filter` were declared, so the glass lost its blur in `next build` but not in `next dev`. Only the standard property is declared now, and `npm run build` runs `scripts/verify-css.mjs` afterwards to fail loudly if it ever regresses. Confirmed in Chrome against the production build (`blur(28px) saturate(1.7)` on the navbar).

The automated browser check used for this is a throwaway script, not part of the repository; there is still **no committed browser test suite**.

## Performance pass (no visual changes)

Hover lag came from app-wide re-renders on every hover, plus work on layers that were never visible (the ambient backdrop is hidden by the
opaque `<body>` background and is now disabled; see `frontend/README.md`). Also: opaque poster tiles no longer compute a backdrop blur,
the WebGL beam renders at 1x density, the idle click-spark layer is `display: none`, the ticker pauses off-screen, and card pointer
handling does one layout read per frame. Measured in the preview: hovering across cards = idle frame rate, zero DOM changes outside the
hovered card, no long tasks, and a locked 60 fps / p99 17 ms in the best-case tab.

## Rebrand

The logo (`Logo.tsx`) is interactive: idle drift, hover acceleration + halo, click shutter-snap, fast spin while a request is running; the wordmark shimmers with it (hover or busy; unchanged at rest); no motion for reduced-motion users. A pivot bug (blades rotating about an off-centre point) was caught by measurement and fixed.

Renamed from *Lumen* to **Kinema** (Greek *kínēma*, "movement", root of "cinema") with a new aperture-and-play-button logo (`frontend/src/components/Logo.tsx`, `frontend/src/app/icon.svg`). An existing browser profile is migrated automatically.

## Honest evaluation summary

Hybrid NDCG@10 0.108 ≥ collaborative 0.105 > popularity 0.080 ≫ content 0.009 > random 0.005. Collaborative vs popularity is significant; **hybrid vs collaborative is not**. With only 3 liked movies popularity is as good as anything. See `reports/evaluation.md`.

## Known issues / limitations

* Cold-start picks for a genre + one liked movie are sensible at the top (e.g. Inception, Terminator 2, Contact) but the tail can include weaker titles (e.g. *Sleeper*); not tuned on anecdotes.
* Next.js dev overlay badge appears in dev mode only.
* Sessions are a local JSON file (demo-grade).
* Browser screenshots of scrolled pages/dialogs were unreliable in the preview tool, and animations pause while its tab is hidden; those states were verified through the DOM instead.
* Claude's replies are intentionally generic framing plus an engine-written "Top pick" line: free-form talk about film content was unverifiable (and once false), so it is rejected.
* With a key set, each message makes two Claude calls (about 4-6 s per turn with Haiku).

## Next steps (if continuing)

1. Try `CLAUDE_MODEL=claude-sonnet-5-5` or the default Opus for richer (slower, costlier) replies and re-run the live checks.
2. Optional: add a Playwright smoke suite; click-test the sliders/year inputs; tablet pass.
3. Optional: matrix factorisation as a fifth recommender and evaluate it the same way.

## Memory fix (found while preparing the deployment)

The API used about 600 MB right after start-up, more than Render's free 512 MB. Almost all of it was a temporary peak while the collaborative-filtering model was built (800-row dense blocks of the item-item similarity). Building it 25 rows at a time gives a **bit-identical** model (maximum difference 0.0, same 736,297 non-zeros), is faster, and the process now stays at about 230-335 MB.
