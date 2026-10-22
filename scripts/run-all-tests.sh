#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Backend pytest =="
cd backend
if [[ -x .venv/bin/pytest ]]; then
  PY=.venv/bin/pytest
elif [[ -x venv/bin/pytest ]]; then
  PY=venv/bin/pytest
else
  echo "No backend venv pytest found" >&2
  exit 1
fi
"$PY" -q --tb=short

echo "== Frontend typecheck + vitest =="
cd ../frontend
npm run typecheck
npm run test

if [[ "${RUN_E2E:-0}" == "1" ]]; then
  echo "== Playwright E2E (ports 5174/8001; Postgres + MinIO required) =="
  bash "$ROOT/scripts/run-e2e-tests.sh"
fi

echo "All tests passed."
