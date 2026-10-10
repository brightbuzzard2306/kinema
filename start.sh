#!/usr/bin/env bash
# One-command launcher: sets everything up on first run, then starts the API (8000) and the web app (3000).
#   ./start.sh            start both
#   ./start.sh --setup    only install/download, don't start servers
set -euo pipefail
cd "$(dirname "$0")"

say() { printf "\033[1m==>\033[0m %s\n" "$1"; }

if [ ! -x backend/.venv/bin/python ]; then
  say "Creating Python virtual environment"
  python3 -m venv backend/.venv
fi
say "Installing backend dependencies"
backend/.venv/bin/pip install -q -r backend/requirements.txt

say "Checking the MovieLens dataset"
(cd backend && .venv/bin/python -m scripts.setup_data)

if [ ! -d frontend/node_modules ]; then
  say "Installing frontend dependencies"
  (cd frontend && npm install --no-audit --no-fund)
fi

if [ ! -f reports/evaluation.json ]; then
  say "No evaluation report yet - the app still works with default weights."
  say "Run it any time:  cd backend && .venv/bin/python -m scripts.run_evaluation"
fi

[ "${1:-}" = "--setup" ] && { say "Setup complete."; exit 0; }

if [ ! -f .env ]; then
  say "No .env found - starting in offline mode (no Claude, no posters). Copy .env.example to .env to enable them."
fi

say "Starting API on http://localhost:8000 and web app on http://localhost:3000  (Ctrl+C stops both)"
(cd backend && exec .venv/bin/python -m uvicorn app.main:app --port 8000) &
API=$!
(cd frontend && exec npm run dev) &
WEB=$!
trap 'kill $API $WEB 2>/dev/null || true' EXIT INT TERM
wait
