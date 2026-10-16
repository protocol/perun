#!/usr/bin/env bash
# Auto-context-reset tests: the operating layer sets autoCompactWindow (never over a user value) and wires the
# SessionStart handoff re-inject hook. Fixture repos under TMPDIR; nothing is deleted or killed.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
command -v jq >/dev/null 2>&1 || { echo "SKIP  jq missing"; exit 0; }
W="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-acr.XXXXXX")"
export DCR_NO_PROBE=1 CLAUDE_CONFIG_DIR="$W/home"  # an empty user-global dir: the owner's real settings never leak in
mkdir -p "$W/home"
fail=0; n=0
ok() { n=$((n+1)); if [ "$1" -eq 0 ]; then echo "PASS  $2"; else echo "FAIL  $2"; fail=1; fi; }
inst() { bash "$ROOT/install.sh" --with-delivery --apply-operating-layer "$@" >/dev/null 2>&1; }

mkdir -p "$W/fresh/.claude" "$W/user/.claude" "$W/proj/.claude" "$W/off/.claude" "$W/glob/.claude"
echo '{}' >"$W/fresh/.claude/settings.local.json"
echo '{"autoCompactWindow":500000}' >"$W/user/.claude/settings.local.json"
echo '{"autoCompactWindow":"auto"}' >"$W/proj/.claude/settings.json"
echo '{}' >"$W/off/.claude/settings.local.json"
echo '{}' >"$W/glob/.claude/settings.local.json"
inst "$W/fresh"; inst "$W/user"; inst "$W/proj"; inst --policy auto_compact=off "$W/off"
F="$W/fresh/.claude/settings.local.json"

jq -e '.autoCompactWindow == 200000' "$F" >/dev/null; ok $? "fresh install writes autoCompactWindow=200000"
jq -e '.autoCompactWindow == 500000' "$W/user/.claude/settings.local.json" >/dev/null; ok $? "user value in settings.local.json is never overridden"
jq -e 'has("autoCompactWindow") | not' "$W/proj/.claude/settings.local.json" >/dev/null; ok $? "project settings.json value: nothing written to local (it would shadow it)"
jq -e 'has("autoCompactWindow") | not' "$W/off/.claude/settings.local.json" >/dev/null; ok $? "policy auto_compact=off opts out"
echo '{"autoCompactWindow":300000}' >"$W/home/settings.json"
inst "$W/glob"
jq -e 'has("autoCompactWindow") | not' "$W/glob/.claude/settings.local.json" >/dev/null; ok $? "user-global settings value: nothing written to local"
rm -f "$W/home/settings.json"
before="$(cat "$F")"
inst "$W/fresh"
[ "$before" = "$(cat "$F")" ]; ok $? "re-install is idempotent"
jq -e '[.hooks.SessionStart[] | select(.matcher == "compact|startup|clear") | .hooks[].command | contains("handoff_inject.py")] | any' "$F" >/dev/null; ok $? "SessionStart compact|startup|clear runs handoff_inject.py"
python3 "$SC/perun_policy.py" check auto_compact maybe >/dev/null 2>&1; [ $? -ne 0 ]; ok $? "policy rejects a bad auto_compact value"
python3 "$SC/perun_policy.py" check auto_compact off >/dev/null 2>&1; ok $? "policy accepts auto_compact=off"

# The hook, exactly as wired in settings, with and without a handoff.
[ -f "$W/fresh/.claude/skills/agentic-delivery/scripts/handoff_inject.py" ]; ok $? "install copies handoff_inject.py (the empty-output cases below are not vacuous)"
cmd="$(jq -r '.hooks.SessionStart[] | select(.matcher == "compact|startup|clear") | .hooks[0].command' "$F")"
hook() { CLAUDE_PROJECT_DIR="$W/fresh" bash -c "$cmd" <<<"{\"source\":\"$1\"}"; }
out="$(hook compact)"
[ -z "$out" ]; ok $? "hook prints nothing when no handoff exists"
printf 'State: parser done.\nNext: wire the tests.\n' >"$W/fresh/.claude/handoff.md"
out="$(hook compact)"
case "$out" in *"Next: wire the tests."*) rc=0 ;; *) rc=1 ;; esac
ok $rc "hook prints the handoff when present"
case "$out" in *"data, not instructions"*) rc=0 ;; *) rc=1 ;; esac
ok $rc "hook frames the handoff as data, not instructions"
touch -t 202001010000 "$W/fresh/.claude/handoff.md"
out="$(hook startup)"
[ -z "$out" ]; ok $? "startup skips a handoff older than 24h"
out="$(hook compact)$(hook clear)"
case "$out" in *"Next: wire the tests."*"Next: wire the tests."*) rc=0 ;; *) rc=1 ;; esac
ok $rc "compact and clear still inject a stale handoff"
touch "$W/fresh/.claude/handoff.md"
out="$(hook startup)"
case "$out" in *"Next: wire the tests."*) rc=0 ;; *) rc=1 ;; esac
ok $rc "startup injects a handoff younger than 24h"
head -c 9000 /dev/zero | tr '\0' 'x' >"$W/fresh/.claude/handoff.md"
bytes="$(hook compact | wc -c | tr -d ' ')"
[ "$bytes" -gt 0 ] && [ "$bytes" -le 2048 ]; ok $? "hook output capped at 2048 bytes (9000-byte handoff -> $bytes bytes)"
mv "$W/fresh/.claude/handoff.md" "$W/real.md"
ln -s "$W/real.md" "$W/fresh/.claude/handoff-link.md"
out="$(hook compact)"
[ -z "$out" ]; ok $? "hook ignores symlinked handoff files"

# Invalid JSON/JSONC in any settings file: fail closed, write nothing, say so.
mkdir -p "$W/jsonc/.claude" "$W/badglob/.claude"
printf '// my settings\n{"model":"opus"}\n' >"$W/jsonc/.claude/settings.json"
echo '{}' >"$W/jsonc/.claude/settings.local.json"
bash "$ROOT/install.sh" --with-delivery --apply-operating-layer "$W/jsonc" >"$W/jsonc.out" 2>&1
jq -e 'has("autoCompactWindow") | not' "$W/jsonc/.claude/settings.local.json" >/dev/null; ok $? "invalid project settings.json: autoCompactWindow not written"
grep -q "autoCompactWindow not written" "$W/jsonc.out"; ok $? "invalid project settings.json: note printed"
echo '{}' >"$W/badglob/.claude/settings.local.json"
printf '{"a":' >"$W/home/settings.json"
inst "$W/badglob"
jq -e 'has("autoCompactWindow") | not' "$W/badglob/.claude/settings.local.json" >/dev/null; ok $? "invalid user-global settings.json: autoCompactWindow not written"
rm -f "$W/home/settings.json"

# Uninstall removes only what install added.
python3 "$ROOT/scripts/perun_uninstall.py" "$W/fresh" --apply >/dev/null 2>&1
[ ! -f "$F" ] || jq -e 'has("autoCompactWindow") | not' "$F" >/dev/null; ok $? "uninstall removes the autoCompactWindow install added"
python3 "$ROOT/scripts/perun_uninstall.py" "$W/user" --apply >/dev/null 2>&1
jq -e '.autoCompactWindow == 500000' "$W/user/.claude/settings.local.json" >/dev/null; ok $? "uninstall keeps the user's own autoCompactWindow"
python3 "$SC/handoff_inject.py" --selftest >/dev/null; ok $? "handoff_inject --selftest"
python3 "$SC/context_nudge.py" --selftest >/dev/null; ok $? "context_nudge --selftest"
grep -q "consider a fresh session" "$SC/context_nudge.py"; [ $? -ne 0 ]; ok $? "context_nudge no longer tells the owner to restart"
echo "Tests: $n/$n passed (fail=$fail)"; exit "$fail"
