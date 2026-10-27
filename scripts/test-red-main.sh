#!/usr/bin/env bash
# Tests for red_main.py: uncovered = no owner and no fix past the 1h grace; alarms only when a threshold is set; missing file is clean.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RM="$ROOT/.claude/skills/agentic-delivery/scripts/red_main.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-red-main.XXXXXX")"
trap '[ -n "$WORK" ] && rm -rf "$WORK"' EXIT
export PERUN_POLICY="$WORK/policy.json"; echo '{}' >"$PERUN_POLICY"
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
NOW=1000000
cat >"$WORK/r.json" <<JSON
[{"id":"t_old_nobody","since":$((NOW - 7200))},
 {"id":"t_old_owned","since":$((NOW - 36000)),"owner":"lane-a"},
 {"id":"t_new_nobody","since":$((NOW - 600))},
 {"id":"t_fixed","since":$((NOW - 7200)),"fix":"PR 5"}]
JSON
r() { python3 "$RM" --file "$WORK/r.json" --now $NOW "$@"; }
out=$(r); rc=$?
[ "$rc" -eq 0 ] && grep -q 'reds=4 uncovered=1 oldest_h=10.0' <<<"$out"; ok $? "defaults off: reports counts, exit 0"
grep -q '^UNCOVERED t_old_nobody 2.0h' <<<"$out"; ok $? "only the overdue ownerless red is uncovered"
r --max-uncovered 1 >/dev/null; [ $? -eq 1 ]; ok $? "uncovered >= max: exit 1"
r --max-uncovered 2 >/dev/null; [ $? -eq 0 ]; ok $? "uncovered < max: exit 0"
r --max-age-h 10 >/dev/null; [ $? -eq 1 ]; ok $? "oldest age >= limit: exit 1"
echo '{"red_uncovered_max": 1}' >"$PERUN_POLICY"; r >/dev/null; [ $? -eq 1 ]; ok $? "policy key red_uncovered_max drives the alarm"
echo '{}' >"$PERUN_POLICY"; python3 "$RM" --file "$WORK/none.json" | grep -q 'reds=0'; ok $? "missing file, alarm off: no reds, clean"
echo 'not json' >"$WORK/bad.json"; python3 "$RM" --file "$WORK/bad.json" 2>/dev/null; [ $? -eq 2 ]; ok $? "bad input fails closed (2)"
out=$(python3 "$RM" --file "$WORK/none.json" --max-uncovered 1 2>&1); grep -q 'missing' <<<"$out"; ok $? "missing file with alarm on: message"
python3 "$RM" --file "$WORK/none.json" --max-uncovered 1 >/dev/null 2>&1; [ $? -eq 2 ]; ok $? "missing file with alarm on: exit 2 (fail closed)"
echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
