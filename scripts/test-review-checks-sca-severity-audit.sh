#!/usr/bin/env bash
# review_checks.sh ecosystem-audit rows (npm, pnpm, pip-audit, cargo-audit, bundler-audit) lead with a severity tier
# (critical|high|medium|low) where the tool's JSON has a severity field, and "unrated" where it has none. Stub tools, no network.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC=${RC_UNDER_TEST:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-scaaudit.XXXXXX"); trap 'chmod -R u+w "$T"; rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
unset REVIEW_OSV_DB_DIR REVIEW_TRIVY_CACHE OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY
export CARGO_HOME="$T/ch" BUNDLER_AUDIT_DB="$T/db" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN=
mkdir -p "$T/bin" "$T/repo" "$T/ch/advisory-db" "$T/ch/advisory-dbs" "$T/db"; echo x >"$T/db/advisory"; echo x >"$T/ch/advisory-db/x"
stub() { printf '#!/usr/bin/env bash\n%s\n' "$2" >"$T/bin/$1"; chmod +x "$T/bin/$1"; }
stub osv-scanner 'echo "dial tcp: no such host" >&2; exit 127'
stub trivy 'echo "FATAL vulnerability DB not found" >&2; exit 1'
stub semgrep 'echo "{\"results\":[]}"'
stub npm 'echo "{\"vulnerabilities\":{\"lodash\":{\"name\":\"lodash\",\"severity\":\"moderate\"},\"nosev\":{\"name\":\"nosev\"}}}"; exit 1'
stub pnpm 'echo "{\"advisories\":{\"7\":{\"github_advisory_id\":\"GHSA-aaaa\",\"severity\":\"critical\",\"module_name\":\"left-pad\",\"title\":\"t\"}}}"; exit 1'
stub pip-audit 'echo "{\"dependencies\":[{\"name\":\"flask\",\"version\":\"1.0\",\"vulns\":[{\"id\":\"PYSEC-1\"}]}]}"; exit 1'
stub cargo 'exit 0'
stub cargo-audit 'echo "{\"vulnerabilities\":{\"found\":true,\"count\":1,\"list\":[{\"advisory\":{\"id\":\"RUSTSEC-2099-0001\",\"title\":\"Unsafe\"},\"package\":{\"name\":\"baz\",\"version\":\"0.1.0\"}}]}}"; exit 1'
stub bundle-audit 'echo "{\"version\":\"0.9.2\",\"created_at\":\"x\",\"results\":[{\"type\":\"unpatched_gem\",\"gem\":{\"name\":\"rack\",\"version\":\"2.0.0\"},\"advisory\":{\"id\":\"CVE-B1\",\"title\":\"Demo\",\"criticality\":\"high\"}},{\"type\":\"unpatched_gem\",\"gem\":{\"name\":\"rack\",\"version\":\"2.0.0\"},\"advisory\":{\"id\":\"CVE-B2\",\"title\":\"Demo\",\"criticality\":null}}]}"; exit 1'
cd "$T/repo"
git init -q . && g commit -q --allow-empty -m base && git branch base
mkdir web api rb
echo '{}' >web/package-lock.json; echo 'lockfileVersion: 6' >web/pnpm-lock.yaml; echo flask==1.0 >api/requirements.txt; echo '# lock' >Cargo.lock; echo x >rb/Gemfile.lock
g add . && g commit -q -m locks
: >"$T/notadir"; export PERUN_HEAVY_DIR="$T/notadir"
REVIEW_OSV=1 PATH="$T/bin:$PATH" bash "$RC" --base base 2>"$T/err" >"$T/out" || true
msg() { jq -r --arg r "$1" '[.[] | select(.rule==$r) | .message][0] // "MISSING"' "$T/out"; }
want() { case "$(msg "$2")" in "$3"*) chk 0 "$1" ;; *) chk 1 "$1 (got: $(msg "$2"))" ;; esac; }
want "npm: moderate -> medium" lodash "medium: lodash"
want "npm: no severity field -> unrated" nosev "unrated: nosev"
want "pnpm: critical" GHSA-aaaa "critical: left-pad"
want "pip-audit: no severity field -> unrated" PYSEC-1 "unrated: flask@1.0"
want "cargo-audit: no severity field -> unrated" RUSTSEC-2099-0001 "unrated: baz@0.1.0"
want "bundler-audit: criticality high" CVE-B1 "high: rack@2.0.0"
want "bundler-audit: null criticality -> unrated" CVE-B2 "unrated: rack@2.0.0"
echo "Tests: $pass/$total"; [ "$pass" = "$total" ]
