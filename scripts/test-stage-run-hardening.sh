#!/usr/bin/env bash
# Tests for the stage_run / file_finding / pre-commit hardening folds: (1) an unsignalable process group (PermissionError) skips the
# kill with a warning, keeps the lease and never makes the stage run unleased; (2) leases carry the host and a lease from another host is
# ignored; (3) a malformed PERUN_HEAVY_WAIT_SECS exits 2 without running the stage; (4) file_finding ignores empty and 1-2 character
# keywords, matches keywords as whole words and uses normalized-title equality for a title with fewer than 2 qualifying words;
# (5) the pre-commit hook warns on stderr when the wall-clock cap cannot be applied.
# Private PERUN_* dirs and a throwaway repo under $WORK; a stub `ps` (start time T<pid> while alive) as in test-stage-run.sh.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SD="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-hardening.XXXXXX")"
trap 'kill $(jobs -p) 2>/dev/null; [ -n "$WORK" ] && rm -rf "$WORK"' EXIT
export WORK PERUN_HEAVY_DIR="$WORK/heavy" PERUN_POLICY="$WORK/policy.json" PERUN_FINDING_LOG="$WORK/force.log"
echo '{"tokens": 1, "stage_timeout_min": 1}' >"$WORK/policy.json"  # exactly one heavy slot
mkdir -p "$WORK/bin" "$PERUN_HEAVY_DIR"
printf '%s\n' '#!/bin/sh' '[ "$1 $2 $3" = "-o lstart= -p" ] && kill -0 "$4" 2>/dev/null && echo "T$4" && exit 0' 'exit 1' >"$WORK/bin/ps"
cat >"$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
t="${GH_TITLE:-Fix flaky browser gate retries}"
case "$1" in issue|pr) echo "[{\"number\":9,\"title\":\"$t\",\"state\":\"CLOSED\",\"url\":\"https://example.com/i/9\"}]" ;; esac
STUB
chmod +x "$WORK/bin/ps" "$WORK/bin/gh"; export PATH="$WORK/bin:$PATH"
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
HOST=$(python3 -c "import sys; sys.path.insert(0, '$SD'); import perun_policy as p; print(p.HOST)")

# 1. PermissionError from killpg: no exception, kill skipped, lease kept, the stage still runs through the lease path (not unleased)
sleep 60 & VICTIM=$!
echo "999999 $(date +%s) heavy T999999 $VICTIM T$VICTIM $HOST" >"$PERUN_HEAVY_DIR/999999"
out=$(python3 - 2>&1 <<PY
import os, sys
sys.path.insert(0, "$SD")
import stage_run
def deny(*a): raise PermissionError(1, "Operation not permitted")
os.killpg = deny
rc = stage_run.main(["--name", "perm", "--wait", "2", "--", "bash", "-c", "touch $WORK/ran-perm"])
print("RC", rc)
PY
)
grep -q '^RC 0' <<<"$out" && [ -e "$WORK/ran-perm" ] && ! grep -q 'running without it' <<<"$out"; ok $? "PermissionError in reap: stage runs, still leased (not unleased)"
grep -q 'cannot signal process group' <<<"$out" && [ -e "$PERUN_HEAVY_DIR/999999" ] && kill -0 "$VICTIM" 2>/dev/null; ok $? "PermissionError: kill skipped with a warning, dead lease kept, group untouched"
kill "$VICTIM" 2>/dev/null; rm -f "$PERUN_HEAVY_DIR/999999"

python3 - <<PY
import os, sys
sys.path.insert(0, "$SD")
import stage_run
n = []
def zombies(pgid, sig):  # signal accepted, then macOS answers EPERM for a group of only zombies
    n.append(sig)
    if len(n) > 1: raise PermissionError(1, "EPERM")
os.killpg = zombies
assert stage_run.kill_group(4242) is True
PY
ok $? "EPERM after the group was signalled (zombie-only group) counts as killed, not as unsignalable"

# 2. host in the lease: written by stage_run, foreign-host lease ignored, own-host lease counted
python3 "$SD/stage_run.py" --wait 2 -- bash -c 'cat "$PERUN_HEAVY_DIR"/*' >"$WORK/lease.txt" 2>&1
grep -q " $HOST\$" "$WORK/lease.txt"; r=$?; [ $r -eq 0 ] || { echo "lease.txt (host $HOST):"; cat "$WORK/lease.txt"; }; ok $r "lease carries this host's name"
sleep 60 & HP=$!
echo "$HP $(date +%s) heavy - 0 - otherhost.invalid" >"$PERUN_HEAVY_DIR/$HP"
python3 "$SD/stage_run.py" --wait 2 -- true >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ]; ok $? "a live-pid lease from another host does not hold the slot"
echo "$HP $(date +%s) heavy - 0 - $HOST" >"$PERUN_HEAVY_DIR/$HP"
python3 "$SD/stage_run.py" --wait 2 -- true >/dev/null 2>&1; rc=$?
[ "$rc" -eq 75 ]; ok $? "the same lease from this host fills the slot (DEFER 75)"
kill "$HP" 2>/dev/null; rm -f "$PERUN_HEAVY_DIR/$HP"

# 3. malformed PERUN_HEAVY_WAIT_SECS fails closed with exit 2, stage not run
PERUN_HEAVY_WAIT_SECS=soon python3 "$SD/stage_run.py" -- bash -c "touch $WORK/ran-bad" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 2 ] && [ ! -e "$WORK/ran-bad" ]; ok $? "bad PERUN_HEAVY_WAIT_SECS: exit 2, stage not run"

# 3b. load-scaled timeout: max(1, load1/cores) capped at 3; hook never stretched
out=$(python3 - 2>&1 <<PY
import sys
sys.path.insert(0, "$SD")
import host_probe, stage_run as s
assert s.load_scale(2, 8) == 1 and s.load_scale(None, 8) == 1 and s.load_scale(4, 0) == 1, "idle or unknown = 1"
assert s.load_scale(16, 8) == 2 and s.load_scale(80, 8) == 3, "scales, capped at 3"
host_probe.read_load1_and_cores = lambda: (16.0, 8)
print("RC", s.main(["--name", "busy", "--timeout", "0.5", "--wait", "2", "--", "true"]))
print("RC", s.main(["--name", "hookbusy", "--hook", "--timeout", "0.5", "--", "true"]))
PY
)
grep -q 'timeout stretched to 1m' <<<"$out" && ! grep -q 'hookbusy' <<<"$out" && [ "$(grep -c '^RC 0' <<<"$out")" -eq 2 ]; ok $? "timeout is stretched by load (2x here), capped at 3x, and --hook is not stretched"

# 4. file_finding keyword and title rules
FF="$SD/file_finding.py"
out=$(python3 "$FF" "Docs link checker misses anchors" ""); rc=$?
[ "$rc" -eq 0 ]; ok $? "an empty keyword matches nothing (was: matched every candidate)"
out=$(python3 "$FF" "Docs link checker misses anchors" ga); rc=$?
[ "$rc" -eq 0 ]; ok $? "a 2-character keyword is ignored"
out=$(python3 "$FF" "Docs link checker misses anchors" gat); rc=$?
[ "$rc" -eq 0 ]; ok $? "a keyword matches whole words only (gat is not inside gate)"
out=$(python3 "$FF" "Docs link checker misses anchors" retries); rc=$?
[ "$rc" -eq 1 ]; ok $? "a whole-word keyword still matches"
out=$(GH_TITLE="Heavy slot is stuck" python3 "$FF" "Heavy"); rc=$?
[ "$rc" -eq 0 ]; ok $? "a one-word title does not match on overlap"
out=$(GH_TITLE="heavy!" python3 "$FF" "Heavy"); rc=$?
[ "$rc" -eq 1 ] && grep -q 'REFUSE: #9' <<<"$out"; ok $? "a one-word title matches an equal normalized title"

# 5. pre-commit warns when the cap cannot be applied (no stage_run.py in the repo)
R="$WORK/repo"; git init -q "$R"; mkdir -p "$R/.githooks" "$R/scripts"
cp "$ROOT/.githooks/pre-commit" "$R/.githooks/pre-commit"; printf '#!/bin/sh\nexit 0\n' >"$R/scripts/ci-gates.sh"
err=$(cd "$R" && bash .githooks/pre-commit 2>&1 >/dev/null); rc=$?
[ "$rc" -eq 0 ] && grep -q 'WARN: wall-clock cap skipped' <<<"$err"; ok $? "missing stage_run.py: hook warns on stderr and still runs"

echo "stage-run-hardening: $pass passed, $fail failed"; [ "$fail" -eq 0 ]
