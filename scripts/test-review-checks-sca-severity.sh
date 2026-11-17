#!/usr/bin/env bash
# review_checks.sh dependency-CVE rows: osv-scanner, trivy and grype rows lead the message with the tool's own severity
# (critical|high|medium|low), or "unrated" when the tool gives none. Stub tools return fixed JSON; nothing is installed or fetched.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC=${RC_UNDER_TEST:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh} # override: run the test against another copy of the script
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-scasev.XXXXXX"); trap 'chmod -R u+w "$T"; rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin" "$T/repo"
unset REVIEW_OSV_DB_DIR REVIEW_TRIVY_CACHE OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY
stub() { printf '#!/usr/bin/env bash\n%s\n' "$2" >"$T/bin/$1"; chmod +x "$T/bin/$1"; }
# osv: database_specific.severity (MODERATE), group CVSS score (9.8 -> critical), neither (unrated)
stub osv-scanner "cat <<'J'
{\"results\":[{\"source\":{\"path\":\"package-lock.json\"},\"packages\":[{\"package\":{\"name\":\"a\",\"version\":\"1\"},
\"vulnerabilities\":[{\"id\":\"GHSA-1\",\"summary\":\"s1\",\"database_specific\":{\"severity\":\"MODERATE\"}},{\"id\":\"CVE-2\",\"summary\":\"s2\"},{\"id\":\"CVE-3\",\"summary\":\"s3\"},
{\"id\":\"B90\",\"summary\":\"b\"},{\"id\":\"B89\",\"summary\":\"b\"},{\"id\":\"B70\",\"summary\":\"b\"},{\"id\":\"B40\",\"summary\":\"b\"},{\"id\":\"B39\",\"summary\":\"b\"},{\"id\":\"B01\",\"summary\":\"b\"},{\"id\":\"B00\",\"summary\":\"b\"},
{\"id\":\"UNK\",\"summary\":\"u\",\"database_specific\":{\"severity\":\"UNKNOWN\"}},{\"id\":\"UNK0\",\"summary\":\"u\",\"database_specific\":{\"severity\":\"UNKNOWN\"}}],
\"groups\":[{\"ids\":[\"CVE-2\"],\"max_severity\":\"9.8\"},{\"ids\":[\"B90\"],\"max_severity\":\"9.0\"},{\"ids\":[\"B89\"],\"max_severity\":\"8.9\"},{\"ids\":[\"B70\"],\"max_severity\":\"7.0\"},{\"ids\":[\"B40\"],\"max_severity\":\"4.0\"},{\"ids\":[\"B39\"],\"max_severity\":\"3.9\"},{\"ids\":[\"B01\"],\"max_severity\":\"0.1\"},{\"ids\":[\"B00\"],\"max_severity\":\"0.0\"},{\"ids\":[\"UNK\"],\"max_severity\":\"7.5\"}]}]}]}
J
exit 1"
stub trivy "cat <<'J'
{\"Results\":[{\"Target\":\"package-lock.json\",\"Vulnerabilities\":[{\"VulnerabilityID\":\"CVE-T1\",\"PkgName\":\"b\",\"InstalledVersion\":\"2\",\"Severity\":\"HIGH\",\"Title\":\"t1\"},{\"VulnerabilityID\":\"CVE-T2\",\"PkgName\":\"c\",\"InstalledVersion\":\"3\",\"Severity\":\"UNKNOWN\",\"Title\":\"t2\"}]}]}
J"
stub grype "echo '{\"matches\":[{\"vulnerability\":{\"id\":\"CVE-G1\",\"severity\":\"Critical\",\"description\":\"d1\"},\"artifact\":{\"name\":\"p\",\"version\":\"1\"}},{\"vulnerability\":{\"id\":\"CVE-G2\",\"description\":\"d2\"},\"artifact\":{\"name\":\"q\",\"version\":\"1\"}}]}'"
stub semgrep 'echo "{\"results\":[]}"'
cd "$T/repo"
git init -q . && g commit -q --allow-empty -m base && git branch base
echo '{}' >package-lock.json; echo '{"bomFormat":"CycloneDX"}' >sbom.json
g add . && g commit -q -m deps
: >"$T/notadir"; export PERUN_HEAVY_DIR="$T/notadir"
REVIEW_OSV=1 PATH="$T/bin:$PATH" bash "$RC" --base base 2>"$T/err" >"$T/out" || true
msg() { jq -r --arg t "$1" --arg r "$2" '.[] | select(.tool==$t and .rule==$r) | .message' "$T/out"; }
want() { [ "$(msg "$2" "$3")" = "$4" ]; chk $? "$1"; }
want "osv: database_specific severity MODERATE -> medium" osv-scanner GHSA-1 "medium: a@1: s1"
want "osv: group CVSS 9.8 -> critical" osv-scanner CVE-2 "critical: a@1: s2"
want "osv: no severity -> unrated" osv-scanner CVE-3 "unrated: a@1: s3"
want "osv: CVSS 9.0 -> critical" osv-scanner B90 "critical: a@1: b"
want "osv: CVSS 8.9 -> high" osv-scanner B89 "high: a@1: b"
want "osv: CVSS 7.0 -> high" osv-scanner B70 "high: a@1: b"
want "osv: CVSS 4.0 -> medium" osv-scanner B40 "medium: a@1: b"
want "osv: CVSS 3.9 -> low" osv-scanner B39 "low: a@1: b"
want "osv: CVSS 0.1 -> low" osv-scanner B01 "low: a@1: b"
want "osv: CVSS 0.0 -> unrated" osv-scanner B00 "unrated: a@1: b"
want "osv: db UNKNOWN falls through to the group CVSS (7.5 -> high)" osv-scanner UNK "high: a@1: u"
want "osv: db UNKNOWN and no CVSS -> unrated" osv-scanner UNK0 "unrated: a@1: u"
want "trivy: Severity HIGH -> high" trivy CVE-T1 "high: b@2: t1"
want "trivy: UNKNOWN -> unrated" trivy CVE-T2 "unrated: c@3: t2"
want "grype: Critical -> critical" grype CVE-G1 "critical: p@1: d1"
want "grype: absent -> unrated" grype CVE-G2 "unrated: q@1: d2"
echo "Tests: $pass/$total"; [ "$pass" = "$total" ]
