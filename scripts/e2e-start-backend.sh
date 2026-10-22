#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
PORT="${E2E_API_PORT:-${PORT:-8001}}"
FRONT_PORT="${E2E_FRONTEND_PORT:-5174}"
# E2E must allow the Playwright Vite port; backend/.env often lists only 5173.
export ALLOWED_ORIGINS="http://localhost:${FRONT_PORT},http://127.0.0.1:${FRONT_PORT},http://localhost:5173,http://127.0.0.1:5173"
if [[ -x .venv/bin/uvicorn ]]; then
  PY=.venv/bin/uvicorn
elif [[ -x venv/bin/uvicorn ]]; then
  PY=venv/bin/uvicorn
else
  echo "No backend venv with uvicorn" >&2
  exit 1
fi
# Settings load backend/.env via pydantic; do not `source` it (values may contain spaces).
export SKIP_STARTUP_CHECKS="${SKIP_STARTUP_CHECKS:-false}"
export ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-http://localhost:5173},http://127.0.0.1:5173"
exec "$PY" app.main:app --host 127.0.0.1 --port "$PORT"
