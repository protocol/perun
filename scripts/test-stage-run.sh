#!/usr/bin/env bash
# Tests for stage_run.py: a stage past its wall-clock timeout has its whole process group killed, its heavy lease released
# and its name logged (exit 124); a full heavy slot makes the stage wait a bounded time then DEFER (exit 75) without running it; a CMD that itself
# exits 75/124 is reported as 1; a SIGKILLed stage_run leaves an orphan child that the next stage_run reaps; a lease whose pid was reused is ignored.
# Private PERUN_HEAVY_DIR and PERUN_POLICY; writes only under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SR="$ROOT/.claude/skills/agentic-delivery/scripts/stage_run.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-stage-run.XXXXXX")"
trap '[ -n "$WORK" ] && rm -rf "$WORK"' EXIT
export WORK PERUN_HEAVY_DIR="$WORK/heavy" PERUN_POLICY="$WORK/policy.json"
echo '{"tokens": 1, "stage_timeout_min": 1}' >"$WORK/policy.json"  # tokens=1 -> exactly one heavy slot
# A stub `ps` answers only `ps -o lstart= -p PID` (a process start time is T<pid> while alive): deterministic, and works where the
# real ps is denied. A recorded start time that differs from it models a reused pid.
mkdir -p "$WORK/bin"; printf '%s\n' '#!/bin/sh' '[ "$1 $2 $3" = "-o lstart= -p" ] && kill -0 "$4" 2>/dev/null && echo "T$4" && exit 0' 'exit 1' >"$WORK/bin/ps"
chmod +x "$WORK/bin/ps"; export PATH="$WORK/bin:$PATH"
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

# 1. timeout: the child spawns a grandchild that records its pid; both must die, lease must be gone, name logged
out=$(python3 "$SR" --name slowstage --timeout 0.03 -- bash -c 'sleep 300 & echo $! >"$WORK/gc.pid"; wait' 2>&1); rc=$?
sleep 1; gc=$(cat "$WORK/gc.pid" 2>/dev/null)
[ "$rc" -eq 124 ] && grep -q 'stage-timeout: slowstage' <<<"$out"; ok $? "timeout: exit 124 and the stage name is logged"
[ -n "$gc" ] && ! kill -0 "$gc" 2>/dev/null; ok $? "timeout: the grandchild in the stage's process group is killed"
[ -z "$(ls "$PERUN_HEAVY_DIR" 2>/dev/null)" ]; ok $? "timeout: the heavy lease is released"

# 2. slot cap: a live foreign lease fills the single slot -> bounded wait, DEFER, command never runs
mkdir -p "$PERUN_HEAVY_DIR"; echo "$$ $(date +%s)" >"$PERUN_HEAVY_DIR/$$"
out=$(python3 "$SR" --name capped --wait 2 -- bash -c 'touch "$WORK/ran"' 2>&1); rc=$?
[ "$rc" -eq 75 ] && grep -q '^DEFER' <<<"$out" && [ ! -e "$WORK/ran" ]; ok $? "full slot: bounded wait then DEFER exit 75, stage not run"
rm -f "$PERUN_HEAVY_DIR/$$"
python3 "$SR" --name free --wait 2 -- bash -c 'exit 7' >/dev/null 2>&1; [ $? -eq 7 ]; ok $? "free slot: runs and passes through the command's exit code"
for c in 75 124; do python3 "$SR" --wait 2 -- bash -c "exit $c" >/dev/null 2>&1; [ $? -eq 1 ]; ok $? "CMD's own exit $c is reported as 1 (75/124 stay unambiguous)"; done

# 3. SIGKILLed stage_run: the child survives, the next stage_run reaps it and its lease
python3 "$SR" --name orphan -- bash -c 'echo $$ >"$WORK/orphan.pid"; exec sleep 300' >/dev/null 2>&1 & SRP=$!
for _ in $(seq 40); do [ -s "$WORK/orphan.pid" ] && [ "$(cat "$PERUN_HEAVY_DIR/$SRP" 2>/dev/null | wc -w)" -ge 7 ] && break; sleep 0.25; done  # child up and its group recorded in the lease
kill -9 $SRP; wait $SRP 2>/dev/null; op=$(cat "$WORK/orphan.pid")
kill -0 "$op" 2>/dev/null; ok $? "SIGKILL of stage_run leaves its child running (the premise)"
python3 "$SR" --name next --wait 2 -- true >/dev/null 2>&1; sleep 1
! kill -0 "$op" 2>/dev/null && [ -z "$(ls "$PERUN_HEAVY_DIR" 2>/dev/null)" ]; ok $? "next stage_run reaps the orphaned child and the dead lease"

# 4. pid reuse: a live pid whose recorded start time differs is a dead lease, so the single slot is free
sleep 30 & RP=$!
echo "$RP $(date +%s) heavy T0 0 -" >"$PERUN_HEAVY_DIR/$RP"
python3 "$SR" --name reuse --wait 2 -- true >/dev/null 2>&1; rc=$?
kill $RP 2>/dev/null
[ "$rc" -eq 0 ]; ok $? "lease with a mismatched pid start time (pid reuse) does not hold the slot"

echo "stage-run: $pass passed, $fail failed"; [ "$fail" -eq 0 ]
