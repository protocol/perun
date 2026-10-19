#!/usr/bin/env bash
# Cost statusLine wiring: the operating layer writes statusLine (never over a user's own, never into machine settings),
# the written command runs and prints the session line, and uninstall removes only what install added.
# Fixture repos under TMPDIR; nothing is deleted or killed.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
command -v jq >/dev/null 2>&1 || { echo "SKIP  jq missing"; exit 0; }
W="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-sl.XXXXXX")"
export DCR_NO_PROBE=1 CLAUDE_CONFIG_DIR="$W/home"  # an empty user-global dir: the owner's real settings never leak in
mkdir -p "$W/home"
fail=0; n=0
ok() { n=$((n+1)); if [ "$1" -eq 0 ]; then echo "PASS  $2"; else echo "FAIL  $2"; fail=1; fi; }
inst() { bash "$ROOT/install.sh" --with-delivery --apply-operating-layer "$@" >/dev/null 2>&1; }

mkdir -p "$W/fresh/.claude" "$W/local/.claude" "$W/proj/.claude" "$W/glob/.claude" "$W/bad/.claude"
echo '{}' >"$W/fresh/.claude/settings.local.json"
echo '{"statusLine":{"type":"command","command":"echo mine"}}' >"$W/local/.claude/settings.local.json"
echo '{"statusLine":{"type":"command","command":"echo proj"}}' >"$W/proj/.claude/settings.json"
echo '{}' >"$W/glob/.claude/settings.local.json"
echo '{}' >"$W/bad/.claude/settings.local.json"
inst "$W/fresh"; inst "$W/local"; inst "$W/proj"
F="$W/fresh/.claude/settings.local.json"

jq -e '.statusLine.type == "command" and (.statusLine.command | contains("cost_statusline.py"))' "$F" >/dev/null; ok $? "fresh install writes the cost statusLine"
jq -e '.statusLine.command == "echo mine"' "$W/local/.claude/settings.local.json" >/dev/null; ok $? "user statusLine in settings.local.json is never overridden"
jq -e 'has("statusLine") | not' "$W/proj/.claude/settings.local.json" >/dev/null; ok $? "project settings.json statusLine: nothing written to local (it would shadow it)"
echo '{"statusLine":{"type":"command","command":"echo home"}}' >"$W/home/settings.json"
inst "$W/glob"
jq -e 'has("statusLine") | not' "$W/glob/.claude/settings.local.json" >/dev/null; ok $? "user-global statusLine: nothing written to local"
printf '{"a":' >"$W/home/settings.json"
inst "$W/bad"
jq -e 'has("statusLine") | not' "$W/bad/.claude/settings.local.json" >/dev/null; ok $? "invalid user-global settings.json: statusLine not written (fail closed)"
rm -f "$W/home/settings.json"
[ ! -e "$W/home/settings.json" ] && [ ! -e "$W/home/settings.local.json" ]; ok $? "machine settings are never written"

out="$(echo '{"cost":{"total_cost_usd":0.5},"context_window":{"used_percentage":40},"prompt_cache":{"hit_ratio":0.9}}' \
  | CLAUDE_PROJECT_DIR="$W/fresh" sh -c "$(jq -r .statusLine.command "$F")")"
[ "$out" = "est \$0.50 | ctx 40% | cache 90%" ]; ok $? "the written command runs from the project dir and prints the line ($out)"
out="$(cd "$W/fresh" && echo '{"cost":{"total_cost_usd":0.5}}' | env -u CLAUDE_PROJECT_DIR sh -c "$(jq -r .statusLine.command "$F")")"
[ "$out" = "est \$0.50" ]; ok $? "without CLAUDE_PROJECT_DIR it falls back to the working directory"
git -C "$W/fresh" init -q 2>/dev/null; mkdir -p "$W/fresh/sub"
out="$(cd "$W/fresh/sub" && echo '{"cost":{"total_cost_usd":0.5}}' | env -u CLAUDE_PROJECT_DIR sh -c "$(jq -r .statusLine.command "$F")")"
[ "$out" = "est \$0.50" ]; ok $? "from a subdirectory it falls back to the git top level"
out="$(cd "$W" && echo '{}' | env -u CLAUDE_PROJECT_DIR sh -c "$(jq -r .statusLine.command "$F")")"; rc=$?
[ "$rc" -eq 0 ] && [ -z "$out" ]; ok $? "with no script reachable it prints nothing and exits 0"
mkdir -p "$W/off/.claude"; echo '{}' >"$W/off/.claude/settings.local.json"; inst --policy statusline=off "$W/off"
jq -e 'has("statusLine") | not' "$W/off/.claude/settings.local.json" >/dev/null; ok $? "policy statusline=off opts out"
python3 "$SC/perun_policy.py" check statusline maybe >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "policy rejects a bad statusline value"

before="$(cat "$F")"; inst "$W/fresh"
[ "$before" = "$(cat "$F")" ]; ok $? "re-install is idempotent"
jq -e '.statusline.command | contains("cost_statusline.py")' "$W/fresh/.claude/.perun-install.json" >/dev/null; ok $? "marker records the statusLine and keeps it across a re-install"
jq -e 'has("statusline") | not' "$W/local/.claude/.perun-install.json" >/dev/null; ok $? "marker does not claim a user's own statusLine"

python3 "$ROOT/scripts/perun_uninstall.py" "$W/fresh" --apply >/dev/null 2>&1
[ ! -f "$F" ] || jq -e 'has("statusLine") | not' "$F" >/dev/null; ok $? "uninstall removes the statusLine install added"
python3 "$ROOT/scripts/perun_uninstall.py" "$W/local" --apply >/dev/null 2>&1
jq -e '.statusLine.command == "echo mine"' "$W/local/.claude/settings.local.json" >/dev/null; ok $? "uninstall keeps the user's own statusLine"
python3 "$SC/cost_statusline.py" --selftest >/dev/null; ok $? "cost_statusline --selftest"
echo "Tests: $n/$n passed (fail=$fail)"; exit "$fail"
