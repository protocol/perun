#!/usr/bin/env bash
# review_checks.sh --list-tools is a literal grep of the script's own source; org_audit_driver.py names every tool it prints as "timed out" when progress is unreadable.
# Drift guard: a real --full run on a small fixture records start/done lines in its progress file; every tool in that file must be in --list-tools,
# so a tool added to the script without reaching the list fails here. Installed tools vary, so the check is subset, not equality. Hermetic: no network
# (the registry/advisory lookups just report NOT CHECKED).
# Coverage is only the tools this fixture starts (py/sh/json/yml files); a tool for another language is not exercised here.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-listtools.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
# a shim rm that saves the run's progress file before the script's EXIT trap deletes its temp dir
mkdir "$T/bin"
cat >"$T/bin/rm" <<'SHIM'
#!/bin/sh
for a in "$@"; do [ -f "$a/progress" ] && cp "$a/progress" "$SAVE_PROGRESS"; done
exec /bin/rm "$@"
SHIM
chmod +x "$T/bin/rm"
mkdir "$T/r"; cd "$T/r"; g init -q .; g commit -q --allow-empty -m base; git branch -f base
printf 'import os\nos.system("ls")\n' >a.py; printf '#!/bin/sh\necho $1\n' >b.sh; printf '{"a": 1}\n' >c.json; printf 'on: push\n' >d.yml
g add -A; g commit -q -m change
mkdir "$T/tmp"
SAVE_PROGRESS="$T/progress" TMPDIR="$T/tmp" PATH="$T/bin:$PATH" bash "$RC" --full --base base >/dev/null 2>&1 || true
bash "$RC" --list-tools >"$T/list"
r=0; [ -s "$T/progress" ] && [ -s "$T/list" ] || r=1; chk $r "a real --full run wrote progress and --list-tools printed names"
awk '$1=="start"{print $2}' "$T/progress" | sort -u >"$T/ran"
r=0; [ "$(wc -l <"$T/ran")" -ge 3 ] || r=1; chk $r "the fixture run started at least 3 tools ($(tr '\n' ' ' <"$T/ran"))"
r=0; missing=$(comm -23 "$T/ran" "$T/list" | tr '\n' ' '); [ -z "$missing" ] || { echo "not in --list-tools: $missing"; r=1; }; chk $r "every tool a real run started is in --list-tools"
r=0; ! grep -qxE 'exit|tests' "$T/list" || r=1; chk $r "--list-tools names no shell keyword"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
