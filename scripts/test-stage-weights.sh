#!/usr/bin/env bash
# Tests for static per-stage weights (PERUN_STAGE_WEIGHTS): a weight-2 stage waits while a weight-1 lease is live on a 2-slot host,
# runs once that lease is released (a finished stage frees its weight for the waiting stage), and runs alone even if heavier than the cap.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SD="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-stage-weights.XXXXXX")"
trap '[ -n "$WORK" ] && rm -rf "$WORK"' EXIT
export WORK PERUN_HEAVY_DIR="$WORK/heavy" PERUN_POLICY="$WORK/policy.json" PERUN_STAGE_WEIGHTS="big=2,huge=9,small=0.5"
echo '{"tokens": 1}' >"$PERUN_POLICY"
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
python3 - "$SD" <<'PY'
import sys, os, tempfile, pathlib
sys.path.insert(0, sys.argv[1]); import perun_policy as pp
d = pathlib.Path(tempfile.mkdtemp(dir=os.environ["WORK"]))
a = lambda pid, k, s=2: pp.heavy_acquire(d, s, pid, k)
assert a(os.getpid(), "heavy"), "first"                      # load 1 of 2
assert not a(os.getpid() + 1000000, "heavy@2"), "weight 2 must wait for room"   # 1 + 2 > 2
assert not a(os.getpid() + 1000001, "heavy@0.5"), "small stage queues behind the waiting weight-2"
pp.heavy_release(d, os.getpid())
assert a(os.getpid() + 1000001, "heavy@2"), "waiting stage runs once room frees"
pp.heavy_release(d, os.getpid() + 1000001)
# alone: heavier than the cap still runs when nothing else holds a slot
e = pathlib.Path(tempfile.mkdtemp(dir=os.environ["WORK"]))
assert pp.heavy_acquire(e, 2, os.getpid(), "heavy@9"), "alone"
for k in ("heavy@0", "heavy@0.00"):
    try: pp.heavy_acquire(e, 2, os.getpid() + 7, k); raise SystemExit("zero weight accepted")
    except ValueError: pass
assert pp.lane_weight("heavy@0", 0, None) == 1.0 and pp.lane_weight("heavy@x", 0, None) == 1.0
f = pathlib.Path(tempfile.mkdtemp(dir=os.environ["WORK"]))   # starvation: a waiting weight-2 stage blocks new light stages
assert pp.heavy_acquire(f, 2, os.getpid(), "heavy")
assert not pp.heavy_acquire(f, 2, os.getpid() + 1000010, "heavy@2")
assert not pp.heavy_acquire(f, 2, os.getpid() + 1000011, "light"), "light must queue behind the waiting heavy"
pp.heavy_release(f, os.getpid())
assert pp.heavy_acquire(f, 2, os.getpid() + 1000010, "heavy@2"), "heavy runs once room frees"
print("api ok")
PY
ok $? "heavy_acquire honours weights: waits for room, fits small, runs alone"
python3 "$SD/stage_run.py" --name huge --wait 3 -- true >/dev/null 2>&1; ok $? "stage_run with weight above cap runs alone"
python3 "$SD/stage_run.py" --name small --wait 3 -- bash -c 'cat "$PERUN_HEAVY_DIR"/* | grep -q "heavy@0.5"' >/dev/null 2>&1; ok $? "lease records the stage weight"
[ -z "$(ls "$PERUN_HEAVY_DIR" 2>/dev/null)" ]; ok $? "weight released when the stage finishes"
echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
