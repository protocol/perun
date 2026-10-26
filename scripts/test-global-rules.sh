#!/usr/bin/env bash
# Tests for the mandatory owner rules: reply_cap.py and decision_gate.py selftests, the handback_cap.py narration nudge,
# the operating-layer wiring, and `install.sh --global-rules` merging into a throwaway HOME (idempotent, user hooks kept).
# Offline. Prints PASS/FAIL per case and a final "Tests: P/N"; exits non-zero on any failure.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
TPL="$ROOT/.claude/skills/agentic-delivery/templates"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-global-rules.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }

python3 "$SC/reply_cap.py" --selftest >/dev/null 2>&1; ok $? "reply_cap --selftest"
python3 "$SC/decision_gate.py" --selftest >/dev/null 2>&1; ok $? "decision_gate --selftest"
python3 "$SC/handback_cap.py" --selftest 2>/dev/null | grep -q '^PASS  narration-nudge-fires-over-limit'; ok $? "handback_cap narration nudge case passes"

op="$TPL/operating-layer.settings.json"
jq -e '[.hooks.Stop[].hooks[].command] | any(contains("reply_cap.py"))' "$op" >/dev/null; ok $? "operating layer: reply_cap on Stop"
jq -e '[.hooks.UserPromptSubmit[].hooks[].command] | any(contains("reply_cap.py"))' "$op" >/dev/null; ok $? "operating layer: reply_cap on UserPromptSubmit"
jq -e '.hooks.PreToolUse[] | select(.matcher == "AskUserQuestion|ExitPlanMode") | .hooks[].command | contains("decision_gate.py")' "$op" >/dev/null; ok $? "operating layer: decision_gate gates AskUserQuestion|ExitPlanMode"
jq -e '[.hooks.Stop[].hooks[].command] | any(contains("decision_gate.py"))' "$op" >/dev/null; ok $? "operating layer: decision_gate on Stop"
jq -e '[.hooks.PreToolUse[].hooks[].command | select(contains("decision_gate.py") or contains("reply_cap.py"))] | all(contains("|| true") | not)' "$op" >/dev/null; ok $? "operating layer: blocking hooks are not masked by || true"

H="$WORK/home"; mkdir -p "$H/.claude"
printf '%s\n' '{"model":"sonnet","hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo mine"}]}]}}' > "$H/.claude/settings.json"
HOME="$H" bash "$ROOT/install.sh" --global-rules >/dev/null 2>&1; ok $? "install --global-rules exits 0"
S="$H/.claude/settings.json"
jq -e '.model == "sonnet" and ([.hooks.Stop[].hooks[].command] | any(. == "echo mine"))' "$S" >/dev/null; ok $? "existing settings and user hooks kept"
jq -e '[.hooks.Stop[].hooks[].command] | any(contains("reply_cap.py"))' "$S" >/dev/null; ok $? "Stop reply_cap merged"
jq -e '[.hooks.UserPromptSubmit[].hooks[].command] | any(contains("reply_cap.py"))' "$S" >/dev/null; ok $? "UserPromptSubmit reply_cap merged"
jq -e '[.hooks.Stop[].hooks[].command] | any(contains("decision_gate.py"))' "$S" >/dev/null; ok $? "Stop decision_gate merged"
jq -e '.hooks.PreToolUse[0].matcher == "AskUserQuestion|ExitPlanMode"' "$S" >/dev/null; ok $? "PreToolUse decision_gate merged"
jq -e '(.hooks.SubagentStart | length) == 1 and (.hooks.SubagentStop | length) == 1' "$S" >/dev/null; ok $? "subagent hooks merged"
for f in reply_cap decision_gate handback_cap subagent_start_inject; do [ -f "$H/.claude/perun-rules/$f.py" ] || { ok 1 "copied $f.py"; continue; }; done
[ -f "$H/.claude/perun-rules/reply_cap.py" ] && [ -f "$H/.claude/perun-rules/decision_gate.py" ]; ok $? "scripts copied to ~/.claude/perun-rules"
before="$(jq -S . "$S")"; nbak="$(ls "$H/.claude" | grep -c 'settings.json.bak')"
HOME="$H" bash "$ROOT/install.sh" --global-rules >/dev/null 2>&1
[ "$(jq -S . "$S")" = "$before" ] && [ "$(ls "$H/.claude" | grep -c 'settings.json.bak')" = "$nbak" ]; ok $? "second run: settings unchanged, no extra backup"
printf '%s\n' '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"python3 /x/reply_cap.py"}]}]}}' > "$S"
HOME="$H" bash "$ROOT/install.sh" --global-rules >/dev/null 2>&1
jq -e '[.hooks.Stop[].hooks[].command | select(contains("reply_cap.py"))] | length == 1' "$S" >/dev/null; ok $? "an existing reply_cap hook is not duplicated"
printf 'not json' > "$S"
HOME="$H" bash "$ROOT/install.sh" --global-rules >/dev/null 2>&1; rc=$?
[ "$rc" -ne 0 ] && [ "$(cat "$S")" = "not json" ]; ok $? "unparseable settings: fails, file untouched"

echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
