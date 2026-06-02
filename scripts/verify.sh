#!/usr/bin/env bash
set -euo pipefail

run_python_project() {
  local path="$1"

  echo
  echo "==> $path"
  (
    cd "$path"
    uv sync
    uv run pytest
    uv run ruff check .
    uv run ruff format --check .
  )
}

run_python_project shared
run_python_project api
run_python_project background
run_python_project notifications

echo
echo "==> web"
(
  cd web
  npm install
  npm run typecheck
  npm run lint
  npm run test
  npm run build
)

echo
echo "==> e2e"
(
  cd e2e
  npm install
  npx playwright install chromium
  npm run test
)
