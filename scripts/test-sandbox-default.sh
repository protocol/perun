#!/usr/bin/env bash
# Sandbox-by-default tests. Inspect generated settings JSON only; only the temp dir under TMPDIR is removed (on exit).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
command -v jq >/dev/null 2>&1 || { echo "SKIP  jq missing"; exit 0; }
W="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-sb.XXXXXX")"
trap '[ -n "$W" ] && rm -rf "$W"' EXIT
export DCR_NO_PROBE=1  # no network probe on test installs; the probe has its own tests
fail=0; n=0
ok() { n=$((n+1)); if [ "$1" -eq 0 ]; then echo "PASS  $2"; else echo "FAIL  $2"; fail=1; fi; }

mkdir -p "$W/a/.claude" "$W/b/.claude"
echo '{"permissions":{"deny":["Bash(curl *)"]}}' >"$W/a/.claude/settings.local.json"
echo '{}' >"$W/b/.claude/settings.local.json"
bash "$ROOT/install.sh" --with-delivery --apply-operating-layer "$W/a" >"$W/a.out" 2>&1
bash "$ROOT/install.sh" --with-delivery --apply-operating-layer --no-sandbox "$W/b" >"$W/b.out" 2>&1
A="$W/a/.claude/settings.local.json"; B="$W/b/.claude/settings.local.json"
jq -e '.hooks.SubagentStop | length > 0' "$A" "$B" >/dev/null; ok $? "apply and --no-sandbox both still merge hooks"

jq -e '.sandbox.enabled == true and .sandbox.allowUnsandboxedCommands == false and .sandbox.autoAllowBashIfSandboxed == true' "$A" >/dev/null; ok $? "apply: sandbox on, unsandboxed retry off, sandboxed commands auto-allowed"
jq -e '.sandbox.excludedCommands == ["gh *"] and (.permissions.allow | index("Bash(gh pr view *)")) and (.permissions.allow | index("Bash(gh *)") | not) and .sandbox.network.allowLocalBinding == true
  and (.sandbox.network.allowedDomains | contains(["github.com","*.github.com","*.githubusercontent.com","registry.npmjs.org","*.npmjs.org","pypi.org","files.pythonhosted.org"]))
  and (.sandbox.filesystem.allowWrite | contains(["~/.cache","~/.npm"]))' "$A" >/dev/null; ok $? "apply: autonomy-ready keys present"
jq -e '.permissions.deny | contains(["Bash(rm -rf *)","Bash(rm -fr *)","Bash(rm -r *)","Bash(rm -R *)","Bash(sudo *)"])' "$A" >/dev/null; ok $? "apply: rm/sudo deny rules present"
jq -e '.permissions.deny | index("Bash(curl *)")' "$A" >/dev/null; ok $? "apply: existing deny rule kept"
jq -e '(.permissions.allow | contains(["Edit(/**)","Bash(python3 -m pytest *)","Bash(git add *)","Bash(git commit *)"])) and (.permissions.deny | contains(["Edit(/.claude/settings.local.json)","Bash(git commit --no-verify *)","Bash(git push --force *)"]))' "$A" >/dev/null; ok $? "apply: autonomy allow rules present; no-verify, force-push and own-settings edits denied"
bash "$ROOT/install.sh" --with-delivery --apply-operating-layer "$W/a" >/dev/null 2>&1
[ "$(jq '.permissions.deny | length' "$A")" = 16 ]; ok $? "apply: idempotent deny list (16 entries)"
for c in "gh alias *" "gh extension *" "gh repo delete *" "gh release delete *"; do
  jq -e --arg r "Bash($c)" '.permissions.deny | index($r)' "$A" >/dev/null; ok $? "apply: destructive gh denied: $c"
done
mkdir -p "$W/d/.claude"
echo '{"sandbox":{"enabled":false,"excludedCommands":["docker compose *"],"network":{"allowedDomains":["example.com"]}},"permissions":{"allow":["Bash(make *)"]}}' >"$W/d/.claude/settings.local.json"
bash "$ROOT/install.sh" --with-delivery --apply-operating-layer "$W/d" >/dev/null 2>&1
D="$W/d/.claude/settings.local.json"
jq -e '.sandbox.enabled == false and .sandbox.excludedCommands == ["docker compose *","gh *"] and .sandbox.network.allowedDomains[0] == "example.com"
  and (.sandbox.network.allowedDomains | index("pypi.org")) and .sandbox.network.allowLocalBinding == true and .permissions.allow[0] == "Bash(make *)" and (.permissions.allow | index("Bash(gh run list *)"))' "$D" >/dev/null
ok $? "merge: existing values win, nested keys kept, lists unioned"
grep -q "sandbox.enabled=true" "$W/a.out"; ok $? "apply: What changed lists sandbox"
jq -e 'has("sandbox") or has("permissions") | not' "$B" >/dev/null; ok $? "--no-sandbox: no sandbox or deny keys"
grep -q "NO sandbox" "$W/b.out"; ok $? "--no-sandbox: risk warning printed"
python3 "$SC/operating_selfcheck.py" --settings "$A" | grep -q "^sandbox-on: PRESENT"; ok $? "selfcheck: sandbox on is PRESENT"
python3 "$SC/operating_selfcheck.py" --settings "$B" | grep -q "^sandbox-on: MISSING RED"; ok $? "selfcheck: sandbox off is MISSING RED"
grep -q "host-safety.md#common-sandbox-errors" "$W/a.out"; ok $? "install: notice points at Common sandbox errors"
grep -q "^## Common sandbox errors" "$ROOT/docs/host-safety.md"; ok $? "docs: Common sandbox errors section exists"
python3 "$SC/operating_selfcheck.py" --settings "$A" | grep -q "^WARN"; [ $? -ne 0 ]; ok $? "selfcheck: no WARN, template excludes gh"
jq 'del(.sandbox.excludedCommands)' "$A" >"$W/c.json"
python3 "$SC/operating_selfcheck.py" --settings "$W/c.json" | grep -q "^WARN: sandbox on and gh not excluded"; ok $? "selfcheck: WARN when gh not excluded"
grep -q "^## Autonomy-ready defaults" "$ROOT/docs/host-safety.md"; ok $? "docs: Autonomy-ready defaults section exists"
python3 "$SC/operating_selfcheck.py" --selftest >/dev/null; ok $? "selfcheck --selftest"
echo "Tests: $n/$n passed (fail=$fail)"; exit "$fail"
