#!/usr/bin/env bash
# review_checks.sh dependency rows: the same advisory reported by osv-scanner (id + aliases) and trivy (id + VendorIDs)
# is one row (same file, same pkg@version, intersecting id sets); the highest severity wins, a tie goes to osv-scanner.
# Stub tools return fixed JSON for the fictional package acme-lib; nothing is installed or fetched.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC=${RC_UNDER_TEST:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh} # override: run the test against another copy of the script
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-aliasdedup.XXXXXX"); trap 'chmod -R u+w "$T"; rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin" "$T/repo"
unset REVIEW_OSV_DB_DIR REVIEW_TRIVY_CACHE OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY
stub() { printf '#!/usr/bin/env bash\n%s\n' "$2" >"$T/bin/$1"; chmod +x "$T/bin/$1"; }
# osv: acme-lib@1.0.0 holds GHSA-A (alias CVE-A, medium), GHSA-B (alias CVE-B, high), GHSA-D (alias CVE-D); acme-lib@2.0.0 holds GHSA-C (alias CVE-C)
stub osv-scanner "cat <<'J'
{\"results\":[{\"source\":{\"path\":\"package-lock.json\"},\"packages\":[
{\"package\":{\"name\":\"acme-lib\",\"version\":\"1.0.0\"},\"vulnerabilities\":[
{\"id\":\"GHSA-A\",\"aliases\":[\"CVE-A\"],\"summary\":\"sa\",\"database_specific\":{\"severity\":\"MODERATE\"}},
{\"id\":\"GHSA-B\",\"aliases\":[\"CVE-B\"],\"summary\":\"sb\",\"database_specific\":{\"severity\":\"HIGH\"}},
{\"id\":\"GHSA-D\",\"aliases\":[\"CVE-D\"],\"summary\":\"sd\",\"database_specific\":{\"severity\":\"HIGH\"}}]},
{\"package\":{\"name\":\"acme-lib\",\"version\":\"2.0.0\"},\"vulnerabilities\":[
{\"id\":\"GHSA-C\",\"aliases\":[\"CVE-C\"],\"summary\":\"sc\",\"database_specific\":{\"severity\":\"HIGH\"}}]}]}]}
J
exit 1"
# trivy: CVE-A high (aliases GHSA-A), CVE-B high (aliases GHSA-B), CVE-C on 3.0.0, CVE-E (disjoint from every osv id) on 1.0.0
stub trivy "cat <<'J'
{\"Results\":[{\"Target\":\"package-lock.json\",\"Vulnerabilities\":[
{\"VulnerabilityID\":\"CVE-A\",\"VendorIDs\":[\"GHSA-A\"],\"PkgName\":\"acme-lib\",\"InstalledVersion\":\"1.0.0\",\"Severity\":\"HIGH\",\"Title\":\"ta\"},
{\"VulnerabilityID\":\"CVE-B\",\"VendorIDs\":[\"GHSA-B\"],\"PkgName\":\"acme-lib\",\"InstalledVersion\":\"1.0.0\",\"Severity\":\"HIGH\",\"Title\":\"tb\"},
{\"VulnerabilityID\":\"CVE-C\",\"VendorIDs\":[\"GHSA-C\"],\"PkgName\":\"acme-lib\",\"InstalledVersion\":\"3.0.0\",\"Severity\":\"HIGH\",\"Title\":\"tc\"},
{\"VulnerabilityID\":\"CVE-E\",\"PkgName\":\"acme-lib\",\"InstalledVersion\":\"1.0.0\",\"Severity\":\"MEDIUM\",\"Title\":\"te\"}]}]}
J"
stub semgrep 'echo "{\"results\":[]}"'
cd "$T/repo"
git init -q . && g commit -q --allow-empty -m base && git branch base
echo '{}' >package-lock.json
g add . && g commit -q -m deps
: >"$T/notadir"; export PERUN_HEAVY_DIR="$T/notadir"
REVIEW_OSV=1 PATH="$T/bin:$PATH" bash "$RC" --base base 2>"$T/err" >"$T/out" || true
cnt() { jq -r --arg a "$1" --arg b "$2" '[.[] | select(.rule==$a or .rule==$b)] | length' "$T/out"; }
f() { jq -r --arg r "$1" "[.[] | select(.rule==\$r)] | $2" "$T/out"; }
[ "$(cnt GHSA-A CVE-A)" = 1 ] && r=0 || r=1; chk $r "alias match: GHSA-A and CVE-A are one row"
[ "$(f CVE-A '.[0].message')" = "high: acme-lib@1.0.0: ta [also reported by: osv-scanner GHSA-A]" ] && r=0 || r=1; chk $r "max severity kept: osv medium + trivy high -> trivy row, high, names osv"
[ "$(f GHSA-A 'length')" = 0 ] && r=0 || r=1; chk $r "the lower-severity osv row is dropped"
[ "$(f GHSA-B '.[0].message')" = "high: acme-lib@1.0.0: sb [also reported by: trivy CVE-B]" ] && r=0 || r=1; chk $r "severity tie: osv-scanner row kept, names trivy"
[ "$(f GHSA-B '.[0].also[0].tool')" = trivy ] && [ "$(f GHSA-B '.[0].tools|join(",")')" = "osv-scanner,trivy" ] && r=0 || r=1; chk $r "also and tools fields carry both scanners"
[ "$(cnt GHSA-C CVE-C)" = 2 ] && r=0 || r=1; chk $r "same ids, different version (2.0.0 vs 3.0.0): not merged"
[ "$(cnt GHSA-D CVE-E)" = 2 ] && r=0 || r=1; chk $r "disjoint id sets on the same pkg@version: not merged"
echo "Tests: $pass/$total"; [ "$pass" = "$total" ]
