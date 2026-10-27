#!/usr/bin/env bash
# Tests for `flake_ledger.py serial`: a test failing only in the full parallel run (SUITE) yet passing solo on >= N trees is a
# SERIAL-CANDIDATE (exit 1); a real flake (solo FAIL too) and a test that passes in the suite are not.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FL="$ROOT/.claude/skills/agentic-delivery/scripts/flake_ledger.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-flake-serial.XXXXXX")"
trap '[ -n "$WORK" ] && rm -rf "$WORK"' EXIT
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
for t in t1 t2 t3; do
  printf 'SUITE test_serial\nPASS test_serial\nSUITE test_flaky\nFAIL test_flaky\nPASS test_flaky\nPASS test_fine\n' | python3 "$FL" --dir "$WORK" record --tree $t >/dev/null
done
out=$(python3 "$FL" --dir "$WORK" serial); rc=$?
[ "$rc" -eq 1 ]; ok $? "candidate present: exit 1"
grep -q '^SERIAL-CANDIDATE test_serial' <<<"$out"; ok $? "suite-only failure flagged"
! grep -q 'test_flaky\|test_fine' <<<"$out"; ok $? "flake and passing test not flagged"
python3 "$FL" --dir "$WORK" serial --n 4 >/dev/null; [ $? -eq 0 ]; ok $? "below --n: exit 0"
printf 'SUITE test_nosolo\n' | python3 "$FL" --dir "$WORK" record --tree t1 >/dev/null
for t in t2 t3; do printf 'SUITE test_nosolo\n' | python3 "$FL" --dir "$WORK" record --tree $t >/dev/null; done
! python3 "$FL" --dir "$WORK" serial | grep -q test_nosolo; ok $? "suite-only failure with zero solo runs is not flagged"
printf 'FAIL test_serial\n' | python3 "$FL" --dir "$WORK" record --tree t9 >/dev/null
! python3 "$FL" --dir "$WORK" serial | grep -q test_serial; ok $? "any solo fail on any tree clears the candidate (global rule)"
echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
