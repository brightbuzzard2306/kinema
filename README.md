# Kinema — a conversational movie recommender

> *Kinema* is from the Greek *kínēma*, "movement", the root of "cinema". The logo is a camera aperture with a play button in its centre: light in, film out. It is alive: the iris turns slowly, speeds up and glows on hover (hover the word and the icon wakes too, with a glint sweeping across "Kinema"), snaps on click, and spins and shimmers while Kinema is thinking (it is the loading indicator too). Reduced-motion users get a still logo.

*RS Mini Project · Recommendation Systems*

Tell Kinema what you feel like watching. A **hybrid recommender built on MovieLens** (popularity + content-based + item-item collaborative filtering) finds the films; **Claude** (optional) understands your sentence and words the reply. Every card says *why* it was picked.

* **Real algorithms, real data** — MovieLens `ml-latest-small` (9,742 movies · 100,836 ratings · 610 users).
* **Honest AI** — Claude never picks or invents movies; titles it mentions are verified against the dataset. No API key? A rule-based parser takes over and the UI says "Offline mode".
* **Cold start** — no account needed: pick genres/movies, or just type.
* **Feedback loop** — 👍/👎 change the next results; disliked movies never return.
* **Compare strategies** — one click ranks your request with Popular, Content, Collaborative and Hybrid side by side (with real offline scores and the overlap between them), so you can *see* what each algorithm does.
* **Streaming replies** — the picks appear as soon as they are ranked while the reply is still being written; the badge in the top bar shows what the engine is doing (reading → ranking → writing). If the connection can't stream, the app falls back to a normal request automatically.
* **Guided** — a 4-step first-visit tour (prompt → card → *Why this?* → *Compare*), and an *About this project* card on the badge (problem, the four algorithms, dataset numbers).
* **Evaluated** — Precision/Recall/NDCG on a held-out split, with confidence intervals ([report](reports/evaluation.md)).
* **Black-and-white glass UI** — cursor-reactive glass, 3D-tilting cards, a backdrop that follows what you hover, a projector-beam hero, an Apple-style dock on wide screens and a continuously scrolling poster ticker. Several effects come from [React Bits](https://github.com/DavidHDev/react-bits) (see Credits).

## Quick start (one command)

```bash
cd "RS Mini Project"
./start.sh
```

Open **http://localhost:3000**. The script creates the Python environment, downloads the dataset, installs the web dependencies and starts both servers (Ctrl+C stops them).

### Or run it by hand (two terminals)

Prerequisites: Python 3.10+, Node 20+, internet access for the first run.

```bash
# one-time setup
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
(cd backend && .venv/bin/python -m scripts.setup_data)     # downloads + validates MovieLens (~1 MB)
(cd frontend && npm install)
```

```bash
# terminal 1 — API on :8000
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000
```

```bash
# terminal 2 — web app on :3000
cd frontend && npm run dev
```

## Optional: turn on Claude and posters

```bash
cp .env.example .env      # then edit .env and fill in the keys you have
```

| Variable | Effect when set | When missing |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude interprets your messages and writes replies (model: `CLAUDE_MODEL`, default `claude-opus-5-5`; `claude-sonnet-5-5` or `claude-haiku-4-5` are cheaper/faster) | Rule-based parser + template replies; recommendations unchanged |
| `ANTHROPIC_WORKSPACE_ID` | Only needed if Claude fails with "API key is not scoped to a workspace" (see Troubleshooting) | Not sent |
| `ACCESS_CODE` | The site becomes private: every API call except `/health` needs the code (the site shows a code screen). Also turns off `/docs` | Open, as in local development |
| `TMDB_API_KEY` | Real posters from TMDB (cached) | Typographic posters generated from the title |

Restart the API after editing `.env`. Keys are read by the backend only and are git-ignored.

## Optional: your name on the page

To show a credit line in the footer and the *About* card, copy `frontend/.env.example` to `frontend/.env.local` and fill `NEXT_PUBLIC_AUTHOR`, `NEXT_PUBLIC_COLLEGE`, `NEXT_PUBLIC_COURSE`, `NEXT_PUBLIC_GUIDE` (all optional; blank = hidden). These values are baked into the page at build time and are public by design. Restart `npm run dev` (or rebuild) after changing them.

## Put it on the web

Step-by-step (Render for the API, Vercel for the site, a custom domain, an access code, a Claude budget): **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**. The API ships as a Docker image (`backend/Dockerfile`) that fits Render's free 512 MB plan (about 230 MB measured).

## Tests, checks and evaluation

```bash
# backend: 154 tests (dataset, algorithms, NLU, Claude failure modes, API, evaluation)
cd backend && .venv/bin/python -m pytest tests -q

# frontend: lint, types, production build
cd frontend && npm run lint && npx tsc --noEmit && npm run build   # also runs a guard that the glass blur survived minification

# offline evaluation (about 4 minutes) -> reports/evaluation.md + reports/evaluation.json
cd backend && .venv/bin/python -m scripts.run_evaluation
cd backend && .venv/bin/python -m scripts.run_evaluation --render-only   # re-render the markdown only
```

The app reads `reports/evaluation.json` at startup to use the validated settings, and the **Evaluation** page shows the same file.

## Project layout

```
backend/app/        protect (access code, rate limits, Claude budget) · catalog · dataset · engine/{content,collaborative,recommender} · nlu · llm · service · sessions · posters · evaluation · main
backend/tests/      pytest suite (synthetic MovieLens-shaped data with known taste clusters)
backend/scripts/    setup_data.py · run_evaluation.py
frontend/src/       app (pages) · components (UI) · lib (typed API client) · hooks
docs/               ARCHITECTURE.md · ALGORITHMS.md · VIVA_PREPARATION.md
reports/            evaluation.md / evaluation.json (generated)
PROJECT_STATUS.md   acceptance checklist with PASS / FAIL / BLOCKED
```

Read next: [Architecture](docs/ARCHITECTURE.md) · [Algorithms](docs/ALGORITHMS.md) · [Viva notes](docs/VIVA_PREPARATION.md).

## Troubleshooting

| Symptom | Fix |
|---|---|
| Page says "The recommender isn't reachable" | Start the API (terminal 1 above) and press *Try again* |
| `Dataset folder not found` | `cd backend && .venv/bin/python -m scripts.setup_data` |
| "Offline mode" badge although you set a key | The key must be in `.env` in the project root; restart the API; check `curl localhost:8000/health` → `llm.enabled` |
| "Claude API error (400) … not scoped to a workspace" | Your key has no workspace. Easiest: in console.anthropic.com create a *new* API key from inside a workspace (e.g. Default). Or copy that workspace's ID (`wrkspc_…`) into `ANTHROPIC_WORKSPACE_ID=` in `.env`; restart the API |
| Reply says it fell back, with a reason | The reason is shown (timeout, rate limit, rejected key…); recommendations still work |
| Port already in use | `lsof -i :8000` / `lsof -i :3000`, stop the old process |
| Posters are typographic | Expected without `TMDB_API_KEY` |
| Different results after editing the profile | Intended: filters and likes apply to the next picks; press *Apply & refresh picks* |

## Limitations (honest list)

* MovieLens small is old and small (610 users, up to 2018); offline metrics are a proxy and confidence intervals are wide.
* Popularity is very strong on MovieLens; the hybrid is statistically comparable to collaborative filtering alone.
* No runtime/cast/plot data, so requests like "under two hours" are acknowledged but cannot be filtered.
* Content-based filtering is weak on its own; with very few liked movies the personalised signal is thin.
* Dislikes and cold-start behaviour are tested functionally, not by offline metrics.
* Sessions are stored in a local JSON file: fine for a demo, not for production.
* Claude integration is covered by mocked-response tests and was exercised live with `claude-haiku-4-5`; it has not been run live with the default `claude-opus-5-5`.
* Replies are shown whole, not token by token, because they are validated against the data first (the *picks* stream ahead of the reply).


## Credits

* **Data:** [MovieLens](https://grouplens.org/datasets/movielens/) `ml-latest-small` by GroupLens (F. M. Harper & J. A. Konstan, 2015). Movie posters and metadata links come from [TMDB](https://www.themoviedb.org/) when a key is set; this product uses the TMDB API but is not endorsed or certified by TMDB.
* **UI effects:** LightRays, BlurText, ShinyText, LogoLoop, ClickSpark, CountUp, RubberSegment, Dock, Magnet and DecryptedText are vendored from [React Bits](https://github.com/DavidHDev/react-bits) by David Haz (MIT + Commons Clause; use inside an application is permitted). They live in `frontend/src/components/bits/` with the licence and a note on the few local changes (ClickSpark was made viewport-sized and idle-free; the others are unmodified).
* **Icons:** [Lucide](https://lucide.dev) (the aperture mark is built from its `aperture` icon geometry plus a play triangle).
