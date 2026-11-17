#!/usr/bin/env bash
# Bench ceilings only ever go down: MAX_FALSE_POSITIVES and MAX_DEMOTED_ROWS in scripts/bench_tool_only.py must be defined exactly once (Python uses the
# last assignment, so a second line would override the first) and be <= their value on origin/main. A ceiling that is new on this branch (absent on
# origin/main) has nothing to compare with and passes. No origin/main ref: skip locally, FAIL in CI (CI checks out full history, fetch-depth 0).
# BENCH_FILE overrides the file under test (the duplicate-definition regression test uses it).
set -euo pipefail
cd "$(dirname "$0")/.."
F=${BENCH_FILE:-scripts/bench_tool_only.py}
fail=0
for k in MAX_FALSE_POSITIVES MAX_DEMOTED_ROWS; do
  n=$(grep -cE "^$k *=" "$F" || true)
  [ "$n" = 1 ] || { echo "FAIL - $k is defined $n times in $F; want exactly once"; fail=1; }
done
[ "$fail" = 0 ] || exit 1
val() { grep -E "^$1 *= *[0-9]+" | sed -E "s/^$1 *= *([0-9]+).*/\1/"; }
if ! git rev-parse -q --verify origin/main >/dev/null; then
  [ "${CI:-}" = true ] && { echo "FAIL - origin/main not fetched; cannot enforce the ceiling ratchet"; exit 1; }
  echo "skip - no origin/main ref"; exit 0
fi
for k in MAX_FALSE_POSITIVES MAX_DEMOTED_ROWS; do
  now=$(val "$k" <"$F")
  [ -n "$now" ] || { echo "FAIL - $k in $F is not a plain integer"; fail=1; continue; }
  old=$(git show "origin/main:scripts/bench_tool_only.py" 2>/dev/null | val "$k" | tail -1 || true)
  if [ -z "$old" ] || [ "$now" -le "$old" ]; then echo "ok - $k $now <= ${old:-new}"; else echo "FAIL - $k raised from $old to $now; ceilings only go down"; fail=1; fi
done
exit $fail
