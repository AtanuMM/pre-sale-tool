#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/e2e"

if [[ ! -f .env ]] && [[ -f .env.example ]]; then
  cp .env.example .env
  echo "Created e2e/.env — admin credentials default from backend/.env via playwright.config"
fi

if [[ ! -d node_modules ]]; then
  npm install
fi

if [[ ! -d "$HOME/.cache/ms-playwright/chromium-"* ]] 2>/dev/null; then
  npx playwright install chromium
fi

npm test
