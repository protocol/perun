#!/usr/bin/env bash
# Host-safety tests. Inspect install output and generated settings only; only the temp dir is removed (on exit).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
TSV="$ROOT/.claude/skills/agentic-delivery/templates/host-safety.tsv"
W="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-hs.XXXXXX")"
trap '[ -n "$W" ] && rm -rf "$W"' EXIT
fail=0; n=0; p=0
ok() { n=$((n+1)); if [ "$1" -eq 0 ]; then p=$((p+1)); echo "PASS  $2"; else echo "FAIL  $2"; fail=1; fi; }

mkdir -p "$W/p" "$W/m"
bash "$ROOT/install.sh" --with-delivery --with-codex --with-extra-hosts "$W/p" >"$W/out" 2>&1
for h in "Claude Code" Cursor Codex "Gemini CLI" OpenCode "GitHub Copilot" Windsurf "Hermes Agent" Kiro Cline "Roo Code" "Factory Droid"; do
  grep -q "^safety: $h:.* https://" "$W/out"; ok $? "install warns for $h with a doc link"
done
bash "$ROOT/install.sh" --minimal "$W/m" >"$W/mout" 2>&1
grep -q '^safety: Claude Code' "$W/mout" && ! grep -q '^safety: Cursor' "$W/mout"; ok $? "minimal install warns only for installed hosts"
python3 "$SC/host_safety.py" --selftest >/dev/null; ok $? "host_safety --selftest"
python3 "$SC/operating_selfcheck.py" --selftest >/dev/null; ok $? "operating_selfcheck --selftest"
mkdir -p "$W/p/.claude"; echo '{}' >"$W/p/.claude/settings.local.json"   # install applies the sandbox when jq exists
python3 "$SC/operating_selfcheck.py" --project "$W/p" --settings "$W/none.json" >"$W/sc"
grep -q '^host-safety-claude: OFF' "$W/sc"; ok $? "selfcheck: claude sandbox OFF without settings"
grep -q '^host-safety-windsurf: NO_OS_SANDBOX' "$W/sc"; ok $? "selfcheck: windsurf has no OS sandbox"
grep -q '^host-safety-codex: COULD_NOT_CHECK' "$W/sc"; ok $? "selfcheck: codex switch is user-level"
echo '{"sandbox":{"enabled":true}}' >"$W/p/.claude/settings.local.json"
python3 "$SC/operating_selfcheck.py" --project "$W/p" --settings "$W/none.json" | grep -q '^host-safety-claude: ON'; ok $? "selfcheck: claude sandbox ON from project settings"
awk -F'\t' '!/^#/ && NF!=5{bad=1} END{exit bad}' "$TSV"; ok $? "tsv rows have 5 fields"
awk -F'\t' '!/^#/ && $5 !~ /^https:\/\//{bad=1} END{exit bad}' "$TSV"; ok $? "tsv rows carry https doc links"
for u in $(awk -F'\t' '!/^#/{print $5}' "$TSV" | grep -v containers.dev); do
  grep -qF "${u%/}" "$ROOT/docs/standards-index.md"; ok $? "doc link in standards-index: $u"
done
echo "Tests: $p/$n passed"; exit "$fail"
