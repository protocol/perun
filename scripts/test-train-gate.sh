#!/usr/bin/env bash
# train_gate admission: shadow (also the no-policy default) logs WOULD-BLOCK and runs; off is silent; enforce holds a second
# browser stage and a train-verify stage (before compile/unit) while the heavy browser lock is held, honours heavy_trains,
# ignores stale/dead leases, and DEFERs (75) once its own gate wait runs out.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SR="$ROOT/.claude/skills/agentic-delivery/scripts/stage_run.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train-gate.XXXXXX")"
trap 'kill $(jobs -p) 2>/dev/null; [ -n "$WORK" ] && rm -rf "$WORK"' EXIT
export PERUN_HEAVY_DIR="$WORK/heavy" PERUN_POLICY="$WORK/policy.json" PERUN_TRAIN_GATE_WAIT_SECS=2
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
lease() { mkdir -p "$PERUN_HEAVY_DIR"; echo "$1 ${3:-$(date +%s)} $2" >"$PERUN_HEAVY_DIR/$1"; }
pol() { echo "{\"tokens\": 8$1}" >"$PERUN_POLICY"; }
# run NAME: the stage records its start time in $WORK/started; rc 75 = held, 0 = ran
run() { rm -f "$WORK/started"; python3 "$SR" --name "$1" --wait 1 -- python3 -c "import time;open('$WORK/started','w').write(str(time.time()))" 2>&1; }
sleep 120 & B=$!; lease $B browser
sleep 120 & P=$!

pol ''; out=$(run train-browser); rc=$?
[ $rc -eq 0 ] && [ -e "$WORK/started" ] && grep -q WOULD-BLOCK <<<"$out"; ok $? "shadow: second browser stage logs WOULD-BLOCK and runs"
echo "{}" >"$PERUN_POLICY"; out=$(run train-browser); rc=$?
[ $rc -eq 0 ] && grep -q WOULD-BLOCK <<<"$out"; ok $? "empty policy: default train_gate is shadow"
pol ', "train_gate": "off"'; out=$(run train-browser); rc=$?
[ $rc -eq 0 ] && ! grep -q WOULD-BLOCK <<<"$out"; ok $? "off: silent, runs"

pol ', "train_gate": "enforce"'; out=$(run train-browser); rc=$?
[ $rc -eq 75 ] && [ ! -e "$WORK/started" ] && grep -q 'retry later' <<<"$out"; ok $? "enforce: second browser stage held then DEFER 75 after gate wait"
pol ', "train_gate": "enforce", "heavy_trains": 2'; out=$(run train-browser); rc=$?
[ $rc -eq 0 ] && [ -e "$WORK/started" ]; ok $? "enforce + heavy_trains=2: second browser stage admitted"
pol ', "train_gate": "enforce"'
out=$(run train-verify); rc=$?
[ $rc -eq 0 ] && [ -e "$WORK/started" ]; ok $? "enforce: first prepared train-verify admitted while browser lock held"

# hold-before-compile: with the prepared slot full, train-verify must not start until the browser lock is released
lease $P train; rm -f "$WORK/started"
( PERUN_TRAIN_GATE_WAIT_SECS=30 python3 "$SR" --name train-verify --wait 1 -- python3 -c "import time;open('$WORK/started','w').write(str(time.time()))" >/dev/null 2>&1 ) & V=$!
sleep 3
[ ! -e "$WORK/started" ]; ok $? "enforce: train-verify not started while browser lock held and prepared slot full"
REL=$(python3 -c "import time;print(time.time())"); rm -f "$PERUN_HEAVY_DIR/$B"; wait $V; rc=$?
[ $rc -eq 0 ] && python3 -c "import sys;sys.exit(0 if float(open('$WORK/started').read())>=$REL else 1)"; ok $? "enforce: train-verify started only after the browser lock was released"

# stale leases never hold: dead pid, and a live pid whose start is older than the lease TTL
rm -f "$PERUN_HEAVY_DIR"/*; lease 999999 browser; out=$(run train-browser); rc=$?
[ $rc -eq 0 ] && ! grep -q 'retry later' <<<"$out"; ok $? "enforce: dead-pid browser lease ignored"
rm -f "$PERUN_HEAVY_DIR"/*; lease $P browser $(( $(date +%s) - 8000 )); out=$(run train-browser); rc=$?
[ $rc -eq 0 ]; ok $? "enforce: expired browser lease (older than TTL) ignored"
echo "train-gate: $pass passed, $fail failed"; [ "$fail" -eq 0 ]
