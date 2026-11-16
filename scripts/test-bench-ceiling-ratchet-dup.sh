#!/usr/bin/env bash
# Regression for scripts/test-bench-ceiling-ratchet.sh: a second definition of a ceiling (Python keeps the last one) must fail the gate, a single
# definition must not trip the duplicate check, and a missing definition fails.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
T=$(mktemp -d "${TMPDIR:-/tmp}/ratchet.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT
fail=0
t() { if BENCH_FILE="$T/b.py" CI= bash "$ROOT/scripts/test-bench-ceiling-ratchet.sh" >"$T/o" 2>&1; then r=0; else r=$?; fi
  if [ "$r" = "$1" ] && { [ -z "${3:-}" ] || grep -q "$3" "$T/o"; }; then echo "ok - $2"; else echo "FAIL - $2 (rc $r)"; cat "$T/o"; fail=1; fi; }
printf 'MAX_FALSE_POSITIVES = 25\nMAX_DEMOTED_ROWS = 5\nMAX_FALSE_POSITIVES = 999\n' >"$T/b.py"
t 1 "second MAX_FALSE_POSITIVES line fails" "MAX_FALSE_POSITIVES is defined 2 times"
printf 'MAX_FALSE_POSITIVES = 25\nMAX_DEMOTED_ROWS = 5\nMAX_DEMOTED_ROWS = 999\n' >"$T/b.py"
t 1 "second MAX_DEMOTED_ROWS line fails" "MAX_DEMOTED_ROWS is defined 2 times"
printf 'MAX_FALSE_POSITIVES = 25\n' >"$T/b.py"
t 1 "missing MAX_DEMOTED_ROWS fails" "MAX_DEMOTED_ROWS is defined 0 times"
exit $fail
