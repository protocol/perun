#!/usr/bin/env bash
# Tests for the lane commit-hook wall-clock cap: .githooks/pre-commit re-runs itself under `stage_run.py --hook`, so a hung hook
# exits nonzero (124) with "COULD-NOT-CHECK: hook exceeded Ns; index.lock holder: ..." and never passes; a bystander process is
# never signalled; a fast hook still passes. Throwaway git repo and private PERUN_* dirs under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-hookcap.XXXXXX")"
trap 'kill $(jobs -p) 2>/dev/null; [ -n "$WORK" ] && rm -rf "$WORK"' EXIT
export PERUN_HEAVY_DIR="$WORK/heavy" PERUN_POLICY="$WORK/policy.json" GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
echo '{}' >"$WORK/policy.json"
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

R="$WORK/repo"; git init -q "$R"; mkdir -p "$R/.githooks" "$R/.claude/skills" "$R/scripts"
cp "$ROOT/.githooks/pre-commit" "$R/.githooks/pre-commit"
ln -s "$ROOT/.claude/skills/agentic-delivery" "$R/.claude/skills/agentic-delivery"
printf '#!/bin/sh\nexit 0\n' >"$R/scripts/ci-gates.sh"
cd "$R" || exit 2

bash .githooks/pre-commit >/dev/null 2>&1; ok $? "fast hook passes under the cap"

printf '#!/bin/sh\nsleep 30\n' >"$R/scripts/ci-gates.sh"
sleep 60 & BY=$!
out=$(PERUN_COMMIT_HOOK_MIN=0.03 bash .githooks/pre-commit 2>&1); rc=$?
[ "$rc" -ne 0 ] && grep -q '^COULD-NOT-CHECK: hook exceeded 1.8s; index.lock holder: ' <<<"$out"; ok $? "hung hook: nonzero and COULD-NOT-CHECK names the cap and the lock holder (rc=$rc)"
kill -0 "$BY" 2>/dev/null; ok $? "a bystander process is never killed"
[ ! -e "$PERUN_HEAVY_DIR" ]; ok $? "hook mode takes no heavy lease"

# the same through python directly, default cap text
out=$(python3 "$ROOT/.claude/skills/agentic-delivery/scripts/stage_run.py" --hook --timeout 0.02 -- sleep 30 2>&1); rc=$?
[ "$rc" -eq 124 ] && grep -q 'exceeded 1.2s' <<<"$out"; ok $? "stage_run --hook: exit 124 and the cap in seconds"

echo "commit-hook-cap: $pass passed, $fail failed"; [ "$fail" -eq 0 ]
