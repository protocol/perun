#!/usr/bin/env bash
# Tests for two shadow-first train throughput gates: claim liveness (_lock.sh PERUN_CLAIM_REAP) and base-red fail-fast
# (train_land.sh BASE_RED_FAILFAST). Plain bash; gh is a PATH stub; writes only under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train-live.XXXXXX")"
trap '[ -n "$WORK" ] && rm -r "$WORK" 2>/dev/null' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PERUN_HEAVY_DIR="$WORK/hv/heavy" WORK SC
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

# --- (1) claim liveness ---
. "$SC/_lock.sh"; L="$WORK/c.lock"; (:) & DEAD=$!; wait $DEAD
plant() { mkdir "$L"; echo "$DEAD" >"$L/pid"; echo "$(date +%s)${1:+ $1}" >"$L/ts"; }
clearl() { rm -f "$L/pid" "$L/ts"; rmdir "$L" 2>/dev/null; }
lock_take "$L" 0 && [ "$(cut -d" " -f2 "$L/ts")" = "$(hostname -s)" ]; ok $? "claim: a take records the host next to the pid"
lock_drop "$L"; [ ! -e "$L" ]; ok $? "claim: drop removes the host record too"
plant "$(hostname -s)"
out=$(lock_take "$L" 0 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q 'SHADOW claim-reap: would reap' <<<"$out" && grep -q STALE-LOCK <<<"$out" && [ -d "$L" ]
ok $? "claim: default shadow logs the would-reap decision and leaves the dead claim untouched"
out=$(PERUN_CLAIM_REAP=enforce lock_take "$L" 0 2>&1); rc=$?
[ $rc -eq 0 ] && grep -q 'claim-reap: reaped' <<<"$out" && [ "$(cat "$L/pid")" = $$ ] && ! ls "$L".reap.* >/dev/null 2>&1
ok $? "claim: enforce reaps a dead-PID same-host claim, then takes it"
lock_drop "$L"
plant "other-host.example"
out=$(PERUN_CLAIM_REAP=enforce lock_take "$L" 0 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q STALE-LOCK <<<"$out" && [ "$(cat "$L/pid")" = "$DEAD" ]; ok $? "claim: a dead pid recorded by another host is never reaped"
clearl; plant
out=$(PERUN_CLAIM_REAP=enforce lock_take "$L" 0 2>&1); rc=$?
[ $rc -eq 1 ] && [ "$(cat "$L/pid")" = "$DEAD" ]; ok $? "claim: a claim with no host record is never reaped"
clearl; mkdir "$L"; echo $$ >"$L/pid"; echo "$(date +%s) $(hostname -s)" >"$L/ts"
PERUN_CLAIM_REAP=enforce lock_take "$L" 0 2>/dev/null; [ $? -eq 1 ] && [ "$(cat "$L/pid")" = $$ ]; ok $? "claim: a live same-host claim is never reaped"
clearl
# live pid owned by another user: kill -0 says EPERM, only ps sees it (ps is stubbed so this holds where ps is sandboxed)
ps() { [ "$2" = 1 ]; }
mkdir "$L"; echo 1 >"$L/pid"; echo "$(date +%s) $(hostname -s)" >"$L/ts"
out=$(PERUN_CLAIM_REAP=enforce lock_take "$L" 0 2>&1); rc=$?
[ $rc -eq 1 ] && [ "$(cat "$L/pid")" = 1 ] && ! grep -q 'claim-reap: reaped' <<<"$out"; ok $? "claim: a live pid owned by another user (kill -0 EPERM, ps sees it) is never reaped"
clearl; unset -f ps
# mid-reap race: the holder changes between the pid check and the rename. One rename to a tomb, no restore over the new dir.
plant "$(hostname -s)"
mv() { echo 4242 >"$L/pid"; command mv "$@"; mkdir "$L"; echo $$ >"$L/pid"; }  # holder swaps just before the rename; a third locker takes the freed name right after
out=$(PERUN_CLAIM_REAP=enforce lock_take "$L" 0 2>&1); rc=$?; unset -f mv
[ $rc -eq 1 ] && [ "$(cat "$L/pid")" = $$ ] && grep -q 'LOST RACE' <<<"$out" && grep -q 'not restored' <<<"$out"
ok $? "claim: reap is one rename to a tomb; a new holder's dir is never overwritten or restored over"
rm -f "$L/pid"; rmdir "$L"; for t in "$L".reap.*; do [ -d "$t" ] && { rm -f "$t/pid" "$t/ts"; rmdir "$t"; }; done
# two or more concurrent reapers on one dead claim: exactly one wins and keeps it (winners stay alive), no live holder is displaced
plant "$(hostname -s)"; rm -f "$WORK"/won.*
for i in 1 2 3 4 5 6; do
  bash -c '. "$1"; PERUN_CLAIM_REAP=enforce lock_take "$2" 0 2>/dev/null && { echo $$ >"$3/won.$$"; sleep 2; }' _ "$SC/_lock.sh" "$L" "$WORK" &
done
wait
nw=$(ls "$WORK"/won.* 2>/dev/null | wc -l | tr -d ' ')
[ "$nw" -eq 1 ] && [ "$(cat "$L/pid")" = "$(cat "$WORK"/won.*)" ] && ! ls -d "$L".reap* >/dev/null 2>&1
ok $? "claim: concurrent reapers - exactly one claim survives, the live winner is never displaced, guard and tombs are gone"
rm -f "$L/pid" "$L/ts"; rmdir "$L"; rm -f "$WORK"/won.*
# a reap guard is never broken, whatever its age or recorded owner (any break races another reaper re-creating it):
# reap skipped, claim untouched, the log line names the guard and the hand-clear command
G="$L.reap"
stale() {  # $1 = guard pid record ("" = half-written), $2 = host; guard mtime is years old
  plant "$(hostname -s)"; mkdir "$G"; [ -n "$1" ] && { echo "$1" >"$G/pid"; echo "946684800 $2" >"$G/ts"; }; touch -t 200001010000 "$G"
  out=$(PERUN_CLAIM_REAP=enforce lock_take "$L" 0 2>&1); rc=$?
  [ $rc -eq 1 ] && [ -d "$G" ] && [ "$(cat "$L/pid")" = "$DEAD" ] && grep -q 'reap skipped: guard held' <<<"$out" && grep -q "rmdir '$G'" <<<"$out"
  r=$?; rm -f "$G/pid" "$G/ts"; rmdir "$G"; clearl; return $r
}
stale "$DEAD" "$(hostname -s)"; ok $? "claim: a stale (old, dead-pid) reap guard is never broken; reap skipped, claim untouched, hand-clear logged"
stale "$DEAD" otherhost; ok $? "claim: a guard recorded by another host is never broken"
stale ""; ok $? "claim: a half-written guard is never broken"
lock_drop "$L"
mkdir "$L"; echo "$DEAD" >"$L/pid"; out=$(lock_drop "$L" 2>&1); rc=$?
[ $rc -eq 1 ] && grep -q 'not held by this shell' <<<"$out" && [ -d "$L" ]; ok $? "claim: lock_drop of a claim it does not own fails loudly and leaves it"
rm -f "$L/pid"; rmdir "$L"; out=$(lock_drop "$L" 2>&1); [ $? -eq 0 ] && [ -z "$out" ]; ok $? "claim: lock_drop of an absent claim is a silent no-op"

# --- (2) base-red fail-fast, end to end through train_land.sh ---
R="$WORK/clone"; g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
git init -q --bare "$WORK/origin.git" -b main; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g commit -q --allow-empty -m base; g push -q origin HEAD:main; B=$(g rev-parse HEAD)
for n in 1 2; do g checkout -q -b "pr$n" "$B"; echo "$n" >"$R/f$n"; g add "f$n"; g commit -q -m "pr $n"; g push -q origin "pr$n:refs/pull/$n/head"; done
g checkout -q --detach "$B"; for n in 1 2; do g merge -q --no-ff -m "merge-train: #$n" "pr$n"; done; U=$(g rev-parse HEAD)
export B U H1=$(g rev-parse pr1) H2=$(g rev-parse pr2)
mkdir -p "$WORK/bin"; cat >"$WORK/bin/gh" <<'STUB'
#!/usr/bin/env bash
case "$1 $2" in
  "pr view") case "$5" in headRefOid) v=H$3; echo "${!v}" ;; baseRefName) echo main ;; isDraft) echo false ;;
                mergeable) echo MERGEABLE ;; headRefName) echo br$3 ;; esac ;;
  "pr diff") echo changelog.d/x.md ;;
  "pr merge") echo "merged $3" >>"$WORK/merged.log" ;;
esac
STUB
chmod +x "$WORK/bin/gh"; export PATH="$WORK/bin:$PATH"
echo 'echo "GREEN base=$B union=$U"' >"$WORK/verify.sh"
echo 'echo "FAIL $FAILID"; echo "FAILURES 1"; exit 1' >"$WORK/browser.sh"
echo 'echo "$TEST" >>"$WORK/reruns.log"; exit 1' >"$WORK/rerun.sh"
echo base1 >"$WORK/b1"; FLAKE_INVOCATION=x bash "$SC/train_flake.sh" --record "$WORK/b1" >"$WORK/baseline"; export FLAKE_INVOCATION=x
echo "$B" >"$WORK/baseline.base"  # the red set is stamped with the base sha it was measured on
cd "$R" || exit 2
run() { : >"$WORK/reruns.log"; : >"$WORK/merged.log"
  env FAILID="$1" "${@:2}" VERIFY_CMD="bash $WORK/verify.sh" UNION_DIRS="$R" LOG_DIR="$WORK" BROWSER_CMD="bash $WORK/browser.sh" \
    RERUN_CMD="bash $WORK/rerun.sh" BASELINE_FAILS="$WORK/baseline" bash "$SC/train_land.sh" tt 1 2 2>&1; }
out=$(run base1); rc=$?
grep -q 'SHADOW base-red-failfast: would end BASE RED now (1 failing ids' <<<"$out" && ! grep -q '^BASE RED: all' <<<"$out" && [ ! -s "$WORK/merged.log" ]
ok $? "base-red: default shadow logs the decision and does not end the train early"
out=$(run base1 BASE_RED_FAILFAST=enforce); rc=$?
[ $rc -eq 1 ] && grep -q 'BASE RED: all 1 failing ids are in the measured red set' <<<"$out" && [ ! -s "$WORK/reruns.log" ] && [ ! -s "$WORK/merged.log" ] && ! grep -q 'DROP\|CANT' <<<"$out"
ok $? "base-red: enforce ends as base-red at once (exit 1, no solo re-run, no bisect, nothing landed)"
[ -z "$(echo '{"tool_input":{"command":"pytest tests"}}' | PERUN_GATE_LOAD1=0 PERUN_GATE_CORES=8 PERUN_GATE_FREE_RAM_PCT=80 python3 "$SC/heavy_gate.py")" ]
ok $? "base-red: the heavy slot is free again after the fail-fast exit"
out=$(run newfail BASE_RED_FAILFAST=enforce); rc=$?
! grep -q 'BASE RED: all\|SHADOW base-red-failfast' <<<"$out"; ok $? "base-red: a failing id outside the base red set never fail-fasts"
echo "$H1" >"$WORK/baseline.base"  # stale: measured on some other sha
out=$(run base1 BASE_RED_FAILFAST=enforce); rc=$?
grep -q 'base-red-failfast refused: red set stamp' <<<"$out" && ! grep -q '^BASE RED: all' <<<"$out" && ! grep -q 'SHADOW base-red-failfast' <<<"$out"
ok $? "base-red: a red set stamped with another sha is refused (no base-red verdict)"
rm -f "$WORK/baseline.base"
out=$(run base1 BASE_RED_FAILFAST=enforce); ! grep -q '^BASE RED: all' <<<"$out" && grep -q "stamp 'none'" <<<"$out"; ok $? "base-red: an unstamped red set is refused"
echo "$B" >"$WORK/baseline.base"
g checkout -q --detach "$B"; git -C "$R" -c user.email=t@example.com -c user.name=T commit -q --allow-empty -m moved; git -C "$R" push -q origin HEAD:main
out=$(run base1 BASE_RED_FAILFAST=enforce); ! grep -q '^BASE RED: all' <<<"$out" && grep -q 'refused' <<<"$out"; ok $? "base-red: a base that moved on since the gate base is refused"
out=$(run base1 BASE_RED_FAILFAST=off); ! grep -q 'SHADOW base-red-failfast' <<<"$out"; ok $? "base-red: off is silent"

echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
