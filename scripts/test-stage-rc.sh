#!/usr/bin/env bash
# Tests that a stage_run DEFER (rc 75) or timeout (rc 124) is infrastructure, never a RED verdict:
#  - train_flake.sh --one maps both to 125 (not 1 "failed"), while a real failing re-run stays 1;
#  - train_land.sh ends exit 3 "stage did not complete" and does NOT run the ratchet culprit hunt.
# Private PERUN_HEAVY_DIR / PERUN_POLICY and a throwaway git origin under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-stage-rc.XXXXXX")"
trap 'kill $(jobs -p) 2>/dev/null; [ -n "$WORK" ] && rm -rf "$WORK"' EXIT
export WORK PERUN_HEAVY_DIR="$WORK/heavy" PERUN_POLICY="$WORK/policy.json" GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
echo '{"tokens": 1}' >"$WORK/policy.json"  # one heavy slot
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
fill() { mkdir -p "$PERUN_HEAVY_DIR"; echo "$1 $(date +%s) heavy" >"$PERUN_HEAVY_DIR/$1"; }

# train_flake --one
RERUN_CMD='exit 1' bash "$SC/train_flake.sh" --one t1 >/dev/null 2>&1; [ $? -eq 1 ]; ok $? "train_flake: a failing re-run stays 1"
RERUN_CMD='sleep 60' PERUN_STAGE_TIMEOUT_MIN=0.02 bash "$SC/train_flake.sh" --one t1 >/dev/null 2>&1; [ $? -eq 125 ]; ok $? "train_flake: a timed-out re-run is 125 (infra), not a failure"
sleep 60 & S=$!; fill $S
RERUN_CMD='exit 1' PERUN_HEAVY_WAIT_SECS=1 bash "$SC/train_flake.sh" --one t1 >/dev/null 2>&1; [ $? -eq 125 ]; ok $? "train_flake: a deferred re-run is 125 (infra), not a failure"
rm -f "$PERUN_HEAVY_DIR/$S"

# train_land: origin with base + 2 PR branches
git init -q --bare "$WORK/origin.git" -b main
R="$WORK/clone"; git clone -q "$WORK/origin.git" "$R" 2>/dev/null
g() { git -C "$R" -c user.email=t@example.com -c user.name=T "$@"; }
g commit -q --allow-empty -m base; g push -q origin HEAD:main
mkdir -p "$WORK/bin"; printf '#!/bin/sh\necho main\n' >"$WORK/bin/gh"; chmod +x "$WORK/bin/gh"; export PATH="$WORK/bin:$PATH"
run_train() { (cd "$R" && env VERIFY_CMD="$1" RATCHET_CMD='touch "$WORK/ratchet.ran"' TRAIN_UNION=always UNION_DIRS="$R" LOG_DIR="$WORK" WAIT_SECS=0 "${@:2}" \
  bash "$SC/train_land.sh" t1 1 2 2>&1); }
out=$(run_train 'sleep 60' TRAIN_STAGE_TIMEOUT_MIN=0.02); rc=$?
[ "$rc" -eq 3 ] && grep -q 'stage did not complete (train-verify rc=124: timed out' <<<"$out" && [ ! -e "$WORK/ratchet.ran" ]; ok $? "train_land: verify timeout is exit 3 'stage did not complete', no ratchet hunt"
fill $S
out=$(run_train 'echo never' TRAIN_SLOT_WAIT_SECS=1); rc=$?
[ "$rc" -eq 3 ] && grep -q 'train-verify rc=75: no heavy slot' <<<"$out" && [ ! -e "$WORK/ratchet.ran" ]; ok $? "train_land: verify DEFER is exit 3 'no heavy slot', no ratchet hunt"

echo "stage-rc: $pass passed, $fail failed"; [ "$fail" -eq 0 ]
