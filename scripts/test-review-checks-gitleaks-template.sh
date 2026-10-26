#!/usr/bin/env bash
# review_checks.sh gitleaks pass with the shipped allowlist template (real gitleaks). Without gitleaks it SKIPs (the CI runner
# has none). Cases: the same fake key is skipped under .history/, fixtures/,
# testdata/ and a generated registry.json, still reported in src/, tests/ and docker-registry-credentials.json,
# the skip count is printed, and a repo with its own .gitleaks.toml does not get the template.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
if ! command -v gitleaks >/dev/null; then
  echo "SKIP gitleaks not installed"; echo "Tests: 0/0"; exit 0
fi
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-glt.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
key="AKIA""QYLPMN5HHHFPZAM2"  # built at runtime so no source line looks like a real key
cd "$T"
git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base && git branch base
mkdir -p .history src tests fixtures testdata
for f in .history/old.txt src/app.txt tests/t.txt fixtures/f.txt testdata/d.txt registry.json docker-registry-credentials.json; do
  printf '{"k":"%s"}\n' "$key" >"$f"
done
git add -A && git -c user.email=t@example.com -c user.name=t commit -q -m files
out=$(bash "$RC" --base base 2>err.txt) || true; [ -n "${DBG:-}" ] && echo "$out" >&2
for hit in src/app.txt tests/t.txt docker-registry-credentials.json; do grep -q "$hit" <<<"$out"; chk $? "$hit is still reported"; done
for gone in .history/ fixtures/f.txt testdata/d.txt '"registry.json"'; do ! grep -q "$gone" <<<"$out"; chk $? "$gone is skipped"; done
grep -q 'template skipped 4 changed file' err.txt; chk $? "skip count is printed"
printf '[extend]\nuseDefault = true\n' >.gitleaks.toml
git add -A && git -c user.email=t@example.com -c user.name=t commit -q -m cfg
out=$(bash "$RC" --base base 2>/dev/null) || true
grep -q '.history/old.txt' <<<"$out"; chk $? "repo with its own .gitleaks.toml does not get the template"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
