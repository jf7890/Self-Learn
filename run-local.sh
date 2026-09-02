#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || { echo "Create .env from .env.example and set SECRET_KEY" >&2; exit 1; }
command -v ffprobe >/dev/null 2>&1 || {
  echo "FFprobe is required to read lesson durations. Install FFmpeg, then run again." >&2
  exit 1
}
set -a; source .env; set +a
export ULEARN_DB="${ULEARN_DB:-$PWD/data/ulearn.db}"
export COURSES_ROOT="${COURSES_ROOT:-$PWD/courses}"
mkdir -p "$(dirname "$ULEARN_DB")"
if [ ! -d .venv ]; then python3 -m venv .venv; .venv/bin/pip install -r server/requirements.txt; fi
if [ ! -d frontend/node_modules ]; then npm --prefix frontend install; fi
trap 'kill 0' EXIT INT TERM
.venv/bin/uvicorn main:app --app-dir server --host 0.0.0.0 --port "${API_PORT:-8000}" &
npm --prefix frontend run dev -- --host 0.0.0.0 --port "${WEB_PORT:-4173}" &
wait
