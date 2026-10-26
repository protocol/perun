#!/usr/bin/env bash
# Tests for the review folds on stage_run / file_finding / train_land / pre-push-verify:
# (1) file_finding: an empty normalized title never matches (check skipped, not blocked) and open PRs are searched;
# (2) stage_run: nan/inf/negative timeout or wait exits 2 without running the command; --probe waits for a slot and gives it back;
# (3) train_land: the exclusive lease is heartbeat-renewed during a long stage, is not held through a slot wait, and ratchet
#     attribution runs under stage_run (a timed-out ratchet names no culprit);
# (4) stage_run handles SIGHUP and the death of its parent: the stage's group dies and the lease is released;
# (5) pre-push-verify prints a deferred / timed-out message (still rejecting the push) for stage_run rc 75 / 124.
# Private PERUN_* dirs and throwaway repos under $WORK; a stub `ps` (start time T<pid> while alive) as in test-stage-run.sh.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SD="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-lifecycle.XXXXXX")"
trap 'kill $(jobs -p) 2>/dev/null; [ -n "$WORK" ] && rm -rf "$WORK"' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null WORK SD
export PERUN_HEAVY_DIR="$WORK/hv/heavy" PERUN_POLICY="$WORK/policy.json" PERUN_FINDING_LOG="$WORK/force.log"
echo '{"tokens": 1, "stage_timeout_min": 1}' >"$WORK/policy.json"  # exactly one heavy slot
mkdir -p "$WORK/bin" "$PERUN_HEAVY_DIR"
printf '%s\n' '#!/bin/sh' '[ "$1 $2 $3" = "-o lstart= -p" ] && kill -0 "$4" 2>/dev/null && echo "T$4" && exit 0' 'exit 1' >"$WORK/bin/ps"
cat >"$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
echo "$*" >>"$WORK/gh.args"
if [ "$1 $2 $3 $4" = "pr list --state open" ] && [ -n "${GH_OPEN_PR:-}" ]; then
  echo '[{"number":5,"title":"Train holds heavy slot forever","state":"OPEN","url":"https://example.com/p/5"}]'
elif [ -n "${GH_OPEN_PR:-}" ] || [ -n "${GH_EMPTY:-}" ]; then echo '[]'
else echo '[{"number":9,"title":"'"${GH_TITLE:-Fix flaky browser gate retries}"'","state":"CLOSED","url":"https://example.com/i/9"}]'; fi
STUB
chmod +x "$WORK/bin/ps" "$WORK/bin/gh"; export PATH="$WORK/bin:$PATH"
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
gone() { for _ in $(seq 60); do kill -0 "$1" 2>/dev/null || return 0; sleep 0.25; done; return 1; }  # pid exits within 15s

# 1. file_finding
out=$(GH_TITLE='??' python3 "$SD/file_finding.py" '!!! ???'); rc=$?
[ "$rc" -eq 0 ] && grep -q '^OK' <<<"$out"; ok $? "empty normalized title: no dedup match (check skipped, push not blocked)"
: >"$WORK/gh.args"; out=$(GH_OPEN_PR=1 python3 "$SD/file_finding.py" "Train holds the heavy slot forever"); rc=$?
[ "$rc" -eq 1 ] && grep -q 'REFUSE: #5 \[OPEN\]' <<<"$out" && grep -q '^pr list --state open' "$WORK/gh.args"; ok $? "an open PR repeat is searched and refused"

# 2. stage_run bad numbers fail closed; --probe
bad=0
for a in "--timeout nan" "--timeout inf" "--timeout=-1" "--wait nan" "--wait=-5"; do
  rm -f "$WORK/ran"; python3 "$SD/stage_run.py" $a -- touch "$WORK/ran" >/dev/null 2>&1; [ $? -eq 2 ] && [ ! -e "$WORK/ran" ] || bad=1
done
PERUN_HEAVY_WAIT_SECS=inf python3 "$SD/stage_run.py" -- touch "$WORK/ran" >/dev/null 2>&1; [ $? -eq 2 ] && [ ! -e "$WORK/ran" ] || bad=1
PERUN_STAGE_TIMEOUT_MIN=nan python3 "$SD/stage_run.py" -- touch "$WORK/ran" >/dev/null 2>&1; [ $? -eq 2 ] && [ ! -e "$WORK/ran" ] || bad=1
[ "$bad" -eq 0 ]; ok $? "nan / inf / negative timeout or wait exits 2 and the command never runs"
python3 "$SD/stage_run.py" --probe --wait 0; [ $? -eq 0 ] && [ -z "$(ls "$PERUN_HEAVY_DIR")" ]; ok $? "--probe with a free slot exits 0 and leaves no lease"
sleep 30 & HOLD=$!; echo "$HOLD $(date +%s)" >"$PERUN_HEAVY_DIR/$HOLD"
python3 "$SD/stage_run.py" --probe --wait 0 2>/dev/null; rc=$?
[ "$rc" -eq 75 ]; ok $? "--probe with the slot full exits 75"
rm -f "$PERUN_HEAVY_DIR/$HOLD"; kill $HOLD 2>/dev/null

# 4. SIGHUP and parent death
rm -f "$WORK/hup.pid"; python3 "$SD/stage_run.py" --name hup -- bash -c 'echo $$ >"$WORK/hup.pid"; exec sleep 300' & SR=$!
for _ in $(seq 40); do [ -s "$WORK/hup.pid" ] && [ "$(wc -w <"$PERUN_HEAVY_DIR/$SR" 2>/dev/null)" -ge 7 ] && break; sleep 0.25; done
kill -HUP $SR; wait $SR; rc=$?
[ "$rc" -eq 129 ] && gone "$(cat "$WORK/hup.pid")" && [ ! -e "$PERUN_HEAVY_DIR/$SR" ]; ok $? "SIGHUP: stage group killed, lease released, exit 129"
sleep 30 & HOLD=$!; echo "$HOLD $(date +%s)" >"$PERUN_HEAVY_DIR/$HOLD"   # slot full: stage_run sits in its slot wait
python3 "$SD/stage_run.py" --name waiting --wait 60 -- true 2>/dev/null & SR=$!; sleep 1.5; kill -TERM $SR; wait $SR; rc=$?
[ "$rc" -eq 143 ] && [ ! -e "$PERUN_HEAVY_DIR/$SR" ]; ok $? "SIGTERM during the slot wait exits 143 and leaves no lease"
rm -f "$PERUN_HEAVY_DIR/$HOLD"; kill $HOLD 2>/dev/null
rm -f "$WORK/orph.pid"
sh -c 'python3 "$SD/stage_run.py" --name orph -- bash -c '"'"'echo $$ >"$WORK/orph.pid"; exec sleep 300'"'"' & sleep 1.5' >/dev/null 2>&1
for _ in $(seq 40); do [ -s "$WORK/orph.pid" ] && break; sleep 0.25; done
gone "$(cat "$WORK/orph.pid" 2>/dev/null || echo 0)" && [ -z "$(ls "$PERUN_HEAVY_DIR")" ]; ok $? "parent death: the stage's group is killed and the lease released"

# 3. train_land (stub gh, local bare origin as in test-train-lease.sh)
R="$WORK/clone"; g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare "$WORK/origin.git" -b main; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)
for n in 1 3; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; g push -q origin "pr$n:refs/pull/$n/head"; done
g checkout -q --detach "$B"; for n in 1 3; do g merge -q --no-ff -m "merge-train: #$n" "pr$n"; done; U=$(g rev-parse HEAD); g checkout -q --detach "$B"
export B U H1=$(g rev-parse pr1) H3=$(g rev-parse pr3)
cat >"$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
case "$1 $2" in
  "pr view") case "$5" in headRefOid) v=H$3; echo "${!v}" ;; baseRefName) echo main ;; isDraft) echo false ;;
                mergeable) echo MERGEABLE ;; headRefName) echo br$3 ;; esac ;;
  "pr diff") echo changelog.d/x.md ;;
  "pr merge") echo "merged $3" >>"$WORK/merged.log" ;;
esac
STUB
run() { (cd "$R" && env UNION_DIRS="$R" LOG_DIR="$WORK" BROWSER_CMD=skip GH="$WORK/bin/gh" "$@" bash "$SD/train_land.sh" tl 1 3 2>&1); }
reset() { : >"$WORK/merged.log"; rm -f "$PERUN_HEAVY_DIR"/* "$WORK/hv/heavy.exclusive" "$WORK/mt.start" "$WORK/mt.end"; }

# heartbeat: the exclusive lease file is touched while a (long) verify stage runs
cat >"$WORK/verify-long.sh" <<'V'
python3 -c "import os,sys; print(os.stat(sys.argv[1]).st_mtime)" "$WORK/hv/heavy.exclusive" >"$WORK/mt.start"
sleep 3
python3 -c "import os,sys; print(os.stat(sys.argv[1]).st_mtime)" "$WORK/hv/heavy.exclusive" >"$WORK/mt.end"
echo "GREEN base=$B union=$U"
V
reset; out=$(run VERIFY_CMD="bash $WORK/verify-long.sh" PERUN_LEASE_HEARTBEAT_SECS=1); rc=$?
[ "$rc" -eq 0 ] && python3 -c "import sys; sys.exit(0 if float(open('$WORK/mt.end').read()) > float(open('$WORK/mt.start').read()) else 1)"; ok $? "heartbeat renews the exclusive lease during a long stage"

# slot wait: with the slot full the exclusive lease is dropped while waiting, retaken, and the train still lands
echo 'echo "GREEN base=$B union=$U"' >"$WORK/verify.sh"
reset; sleep 4 & HOLD=$!; echo "$HOLD $(date +%s)" >"$PERUN_HEAVY_DIR/$HOLD"
( for _ in $(seq 100); do [ -e "$WORK/hv/heavy.exclusive" ] && break; sleep 0.1; done
  for _ in $(seq 200); do [ -e "$WORK/hv/heavy.exclusive" ] || { echo free >"$WORK/seen-free"; break; }; sleep 0.1; done ) & SAMP=$!
rm -f "$WORK/seen-free"; out=$(run VERIFY_CMD="bash $WORK/verify.sh" TRAIN_SLOT_WAIT_SECS=30); rc=$?; wait $SAMP 2>/dev/null
[ "$rc" -eq 0 ] && [ -e "$WORK/seen-free" ] && [ "$(sort "$WORK/merged.log" | tr '\n' ' ')" = "merged 1 merged 3 " ]; ok $? "slot wait: exclusive lease not held while waiting, retaken, train lands"
kill $HOLD 2>/dev/null

# ratchet attribution runs under stage_run with a timeout: a timed-out ratchet names no culprit, a failing one does
echo 'echo "RED union failed"; exit 1' >"$WORK/verify-red.sh"
reset; out=$(run VERIFY_CMD="bash $WORK/verify-red.sh" RATCHET_CMD="sleep 30" TRAIN_RATCHET_TIMEOUT_MIN=0.03); rc=$?
[ "$rc" -eq 3 ] && grep -q 'could not check: ratchet for #1 did not complete (stage rc=124' <<<"$out" && ! grep -q '^CULPRIT' <<<"$out"; ok $? "ratchet re-run times out: could not check, no culprit"
reset; out=$(run VERIFY_CMD="bash $WORK/verify-red.sh" RATCHET_CMD="false"); rc=$?
[ "$rc" -eq 3 ] && grep -q '^CULPRIT #1 ' <<<"$out"; ok $? "ratchet failing alone still names the culprit"

# 5. pre-push-verify: rc 75 / 124 from stage_run print their own message and still reject the push
P="$WORK/pp"; git clone -q --no-hardlinks "$ROOT" "$P" 2>/dev/null
cp "$ROOT/.claude/skills/deep-code-review/templates/pre-push-verify.sh" "$P/.claude/skills/deep-code-review/templates/"
printf '%s\n' '#!/usr/bin/env python3' 'import os, sys' 'sys.exit(int(os.environ["FAKE_RC"]))' >"$P/.claude/skills/agentic-delivery/scripts/stage_run.py"
gp() { git -C "$P" -c user.email=t@example.com -c user.name=T "$@"; }
gp add -A; gp commit -q --allow-empty -m base; gp update-ref refs/remotes/origin/main HEAD
pp() { (cd "$P" && printf 'refs/heads/b %s refs/heads/b 0000000000000000000000000000000000000000\n' "$(git rev-parse HEAD)" |
  FAKE_RC="$1" DCR_PREPUSH_CMD=true DCR_PREPUSH_DEFAULT_BRANCH=main PERUN_GATE_CACHE=0 bash .claude/skills/deep-code-review/templates/pre-push-verify.sh origin) >"$WORK/pp.log" 2>&1; }
pp 75; rc=$?; [ "$rc" -ne 0 ] && grep -q 'deferred: heavy slot busy' "$WORK/pp.log" && ! grep -q 'FAIL -- rejecting push' "$WORK/pp.log"; ok $? "stage_run 75: deferred message, push still rejected"
pp 124; rc=$?; [ "$rc" -ne 0 ] && grep -q 'timed out after' "$WORK/pp.log" && ! grep -q 'FAIL -- rejecting push' "$WORK/pp.log"; ok $? "stage_run 124: timed-out message, push still rejected"
pp 1; rc=$?; [ "$rc" -ne 0 ] && grep -q 'FAIL -- rejecting push' "$WORK/pp.log"; ok $? "stage_run 1: ordinary failure message"
pp 0; ok $? "stage_run 0: push passes"

echo "Tests: $pass/$((pass + fail))"
[ "$fail" -eq 0 ]
