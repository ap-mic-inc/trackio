#!/usr/bin/env bash
# Run the unit tests on HEAD and on the working tree; report only new failures.
# usage: unit_vs_head.sh [pytest args]   (default: tests/unit)
set -uo pipefail
ROOT=$(git rev-parse --show-toplevel)
PY="$ROOT/.venv/bin/python"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
ARGS=("${@:-tests/unit}")

git -C "$ROOT" archive HEAD | tar -x -C "$WORK"
cp -r "$ROOT/trackio/frontend/dist" "$WORK/trackio/frontend/dist" 2>/dev/null

(cd "$WORK" && PYTHONPATH="$WORK" "$PY" -m pytest -q -p no:cacheprovider "${ARGS[@]}" 2>&1) \
  | tee "$WORK/head.log" | tail -1 | sed 's/^/HEAD:        /'
(cd "$ROOT" && "$PY" -m pytest -q -p no:cacheprovider "${ARGS[@]}" 2>&1) \
  | tee "$WORK/tree.log" | tail -1 | sed 's/^/working tree: /'

grep '^FAILED\|^ERROR' "$WORK/head.log" | cut -d' ' -f2 | sort -u > "$WORK/head.txt"
grep '^FAILED\|^ERROR' "$WORK/tree.log" | cut -d' ' -f2 | sort -u > "$WORK/tree.txt"
NEW=$(comm -13 "$WORK/head.txt" "$WORK/tree.txt")
FIXED=$(comm -23 "$WORK/head.txt" "$WORK/tree.txt")
[ -n "$FIXED" ] && printf 'Now passing:\n%s\n' "$FIXED"
if [ -n "$NEW" ]; then
  printf 'NEW failures:\n%s\n' "$NEW"
  exit 1
fi
echo "No new failures ($(wc -l < "$WORK/head.txt") pre-existing on HEAD)."
