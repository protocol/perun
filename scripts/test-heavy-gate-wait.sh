#!/usr/bin/env bash
# Tests for heavy_gate.py waiting inside the hook: a transient HOLD (heavy leases full) that clears within
# PERUN_HEAVY_HOOK_WAIT_SECS lets the command through with no deny; a HOLD that persists is denied after the bounded wait;
# 0 keeps the old immediate deny; the wait is clamped to the hook timeout minus 2s (an old install's 5s hook waits at most 3s). Private PERUN_HEAVY_DIR; writes only under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HG="$ROOT/.claude/skills/agentic-delivery/scripts/heavy_gate.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-hg-wait.XXXXXX")"
sleep 120 & S1=$!; sleep 120 & S2=$!
trap 'kill $S1 $S2 2>/dev/null; [ -n "$WORK" ] && rm -rf "$WORK"' EXIT
export PERUN_HEAVY_DIR="$WORK/heavy" PERUN_GATE_LOAD1=0 PERUN_GATE_CORES=1 PERUN_GATE_FREE_RAM_PCT=60 PERUN_POLICY="$WORK/none.json" PERUN_HEAVY_HOOK_TIMEOUT=70
echo '{}' >"$WORK/none.json"
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }
fill() { mkdir -p "$PERUN_HEAVY_DIR"; for p in $S1 $S2; do echo "$p $(date +%s) heavy" >"$PERUN_HEAVY_DIR/$p"; done; }
run() { echo '{"tool_input":{"command":"pytest tests"},"cwd":"/x"}' | env "$@" python3 "$HG"; }

fill; out=$(run PERUN_HEAVY_HOOK_WAIT_SECS=0); grep -q '"deny".*heavy-lease-full' <<<"$out"; ok $? "wait 0: immediate deny (old behaviour)"
fill; (sleep 2; rm -f "$PERUN_HEAVY_DIR"/*) & out=$(run PERUN_HEAVY_HOOK_WAIT_SECS=15); wait $!
[ -z "$out" ]; ok $? "transient HOLD clears inside the wait: no deny"
fill; t0=$SECONDS; out=$(run PERUN_HEAVY_HOOK_WAIT_SECS=3); dt=$((SECONDS - t0))
grep -q '"deny".*heavy-lease-full' <<<"$out" && [ "$dt" -ge 2 ] && [ "$dt" -le 6 ]; ok $? "persistent HOLD: denied after the bounded wait (${dt}s)"
fill; t0=$SECONDS; out=$(run PERUN_HEAVY_HOOK_TIMEOUT=5 PERUN_HEAVY_HOOK_WAIT_SECS=60); dt=$((SECONDS - t0))
grep -q '"deny".*heavy-lease-full' <<<"$out" && [ "$dt" -ge 2 ] && [ "$dt" -le 5 ]; ok $? "old 5s hook timeout: wait 60 is clamped to 3s so the host never kills the hook (${dt}s)"
fill; t0=$SECONDS; out=$(run -u PERUN_HEAVY_HOOK_TIMEOUT PERUN_HEAVY_HOOK_WAIT_SECS=60); dt=$((SECONDS - t0))
[ "$dt" -le 5 ]; ok $? "no HOOK_TIMEOUT env (old install): same 3s clamp (${dt}s)"
jq -e '[.hooks.PreToolUse[].hooks[] | select(.command | contains("heavy_gate.py"))] | length == 1 and .[0].timeout >= 70 and (.[0].command | contains("PERUN_HEAVY_HOOK_TIMEOUT=70"))' \
  "$ROOT/.claude/skills/agentic-delivery/templates/operating-layer.settings.json" >/dev/null; ok $? "template: heavy_gate hook timeout >= 70 and tells the script so"
# Upgrade: an install from before this change has the 5s heavy_gate hook; --apply-operating-layer must REPLACE it, not add a second one beside it.
mkdir -p "$WORK/proj/.claude" "$WORK/home"
cat >"$WORK/proj/.claude/settings.local.json" <<'OLD'
{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","timeout":5,"command":"python3 \"$CLAUDE_PROJECT_DIR/.claude/skills/agentic-delivery/scripts/heavy_gate.py\" || true"}]}]}}
OLD
DCR_NO_PROBE=1 CLAUDE_CONFIG_DIR="$WORK/home" bash "$ROOT/install.sh" --with-delivery --apply-operating-layer "$WORK/proj" >/dev/null 2>&1
jq -e '[.hooks.PreToolUse[].hooks[] | select(.command | contains("heavy_gate.py"))] | length == 1 and .[0].timeout == 70' \
  "$WORK/proj/.claude/settings.local.json" >/dev/null; ok $? "installer: an old 5s heavy_gate hook is replaced by the 70s one (exactly one entry)"

echo "heavy-gate-wait: $pass passed, $fail failed"; [ "$fail" -eq 0 ]
