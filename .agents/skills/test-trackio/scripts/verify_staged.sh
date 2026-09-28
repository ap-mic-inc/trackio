#!/usr/bin/env bash
# Check that the staged index works on its own before committing it.
# usage: verify_staged.sh [--frontend] [pytest args]
set -uo pipefail
ROOT=$(git rev-parse --show-toplevel)
PY="$ROOT/.venv/bin/python"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
FRONTEND=0
if [ "${1:-}" = "--frontend" ]; then FRONTEND=1; shift; fi

git -C "$ROOT" checkout-index -a --prefix="$WORK/"
cp -r "$ROOT/trackio/frontend/dist" "$WORK/trackio/frontend/dist" 2>/dev/null
cd "$WORK" || exit 1
STATUS=0
"$ROOT/.venv/bin/ruff" check trackio tests -q && echo "ruff: ok" || STATUS=1
PYTHONPATH="$WORK" "$PY" -c "
import trackio, trackio.cli, trackio.server
assert trackio.__file__.startswith('$WORK'), trackio.__file__
print('import: ok')" || STATUS=1
if [ $# -gt 0 ]; then
  PYTHONPATH="$WORK" "$PY" -m pytest -q -p no:cacheprovider "$@" 2>&1 | tail -1
fi
if [ $FRONTEND = 1 ]; then
  cd "$WORK/trackio/frontend" && ln -s "$ROOT/trackio/frontend/node_modules" node_modules
  npx eslint src/ >/dev/null 2>&1 && echo "eslint: ok" || { echo "eslint: FAIL"; STATUS=1; }
  npx vite build --outDir "$WORK/dist-check" >/dev/null 2>&1 && echo "vite build: ok" || { echo "vite build: FAIL"; STATUS=1; }
  npx vitest run 2>&1 | grep -E "Tests |FAIL"
fi
exit $STATUS
