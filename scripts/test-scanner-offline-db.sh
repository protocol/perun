#!/usr/bin/env bash
# Offline vuln-DB paths (REVIEW_OSV_DB_DIR, REVIEW_TRIVY_CACHE), semgrep XDG cache, --repo (no cd chains), dev-only severity cap,
# actionlint without a cd chain, and preflight require_files. Stub tools, no network.
# shellcheck disable=SC2015,SC2016
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$ROOT/.claude/skills/deep-code-review/scripts"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-offdb.XXXXXX"); trap 'rm -rf "$T"' EXIT
export PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 LOG="$T/log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= # a provisioned host cache or ~/.local/bin must not change the cold defaults asserted here
: >"$LOG"
unset OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY # hermetic: an exported seeded DB dir would turn osv on without REVIEW_OSV
unset TRIVY_DISABLE_TELEMETRY # hermetic: the telemetry opt-out asserted below must come from review_checks.sh
fail=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }
has() { grep -qF -- "$2" "$1"; } # has FILE TEXT
mkdir "$T/stub" "$T/repo" "$T/db"
cat >"$T/stub/osv-scanner" <<'X'
#!/usr/bin/env bash
echo "osv $* DIR=${OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY:-}" >>"$LOG"
echo '{"results":[{"packages":[{"package":{"name":"devpkg","version":"1.0.0","ecosystem":"npm"},"groups":[],"vulnerabilities":[{"id":"GHSA-d","database_specific":{"severity":"CRITICAL"}}]},{"package":{"name":"prodpkg","version":"1.0.0"},"groups":[],"vulnerabilities":[]}]}]}'
X
cat >"$T/stub/trivy" <<'X'
#!/usr/bin/env bash
echo "trivy TELEM=${TRIVY_DISABLE_TELEMETRY:-} $*" >>"$LOG"; echo "${TRIVY_MSG:-FATAL failed to initialize DB: vulnerability DB not found}" >&2; exit 1
X
cat >"$T/stub/semgrep" <<'X'
#!/usr/bin/env bash
echo "semgrep XDG=$XDG_CACHE_HOME HOME=$HOME" >>"$LOG"; echo '{"results":[]}'
X
cat >"$T/stub/actionlint" <<'X'
#!/usr/bin/env bash
echo "actionlint $*" >>"$LOG"
X
cp "$T/stub/actionlint" "$T/stub/zizmor"
chmod +x "$T/stub"/*
export PATH="$T/stub:$PATH"

cd "$T/repo"
git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base && git branch base
printf '{"packages":{"node_modules/devpkg":{"version":"1.0.0","dev":true},"node_modules/prodpkg":{"version":"1.0.0"}}}' >package-lock.json
echo 'rules: []' >.semgrep.yml
git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files
WARM="OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=$T/db osv-scanner --offline-vulnerabilities --download-offline-databases ."

# 1. empty pre-seeded DB dir: not checked, exact one-line warm command, scanner never run
bash "$S/review_checks.sh" --base base >"$T/out" 2>"$T/err"
has "$T/err" "osv-scanner (REVIEW_OSV not set" && ok "osv still opt-in without DB dir" || bad "osv opt-in"
REVIEW_OSV_DB_DIR="$T/db" bash "$S/review_checks.sh" --base base >"$T/out" 2>"$T/err"
has "$T/err" "NOT CHECKED: no pre-seeded DB" && has "$T/err" "warm it once: $WARM" && ! grep -q '^osv ' "$LOG" && ok "empty DB dir -> NOT CHECKED + warm command" || { bad "empty DB dir"; cat "$T/err"; }
# 2. seeded DB dir: offline run, no REVIEW_OSV needed
echo x >"$T/db/seed"
REVIEW_OSV_DB_DIR="$T/db" bash "$S/review_checks.sh" --base base >"$T/out" 2>"$T/err"
has "$T/err" "NOT CHECKED: no pre-seeded DB" && ok "non-DB file is not a seeded DB" || bad "any-file seeded"
mkdir -p "$T/db/osv-scanner/npm"; : >"$T/db/osv-scanner/npm/all.zip"; : >"$LOG"
REVIEW_OSV_DB_DIR="$T/db" bash "$S/review_checks.sh" --base base >"$T/out" 2>"$T/err"
grep -q "^osv --offline-vulnerabilities --format json -L ./package-lock.json DIR=$T/db" "$LOG" && ok "seeded DB -> osv-scanner --offline-vulnerabilities with cache dir env" || { bad "seeded DB"; cat "$LOG"; }
# 3. trivy: DB failure stays not-run (never clean), prints the warm command; REVIEW_TRIVY_CACHE -> --cache-dir
: >"$LOG"
REVIEW_TRIVY_CACHE="$T/tc" bash "$S/review_checks.sh" --base base >"$T/out" 2>"$T/err"
grep -q "^trivy .*--cache-dir $T/tc" "$LOG" && has "$T/err" "trivy: NOT CHECKED, warm the DB once: trivy --cache-dir $T/tc image --download-db-only" && ok "trivy cache dir + warm hint" || { bad "trivy hint"; cat "$T/err"; }
has "$T/err" "not run: trivy (exit 1)" && ok "trivy DB failure still not-run" || bad "trivy not-run"
# 3b. a vuln-DB download failure must not fall back to secret-only (fail-open)
: >"$LOG"
TRIVY_MSG="FATAL failed to download vulnerability DB: dial tcp: lookup ghcr.io: no such host" bash "$S/review_checks.sh" --base base >"$T/out" 2>"$T/err"
! has "$T/err" "secret-only" && ! grep -q 'scanners secret' "$LOG" && has "$T/err" "trivy: NOT CHECKED" && ok "DB download failure is not secret-only" || { bad "DB failure fell back"; cat "$T/err"; }
: >"$LOG"
TRIVY_MSG="FATAL failed to download misconfig bundle: dial tcp: no such host" bash "$S/review_checks.sh" --base base >"$T/out" 2>"$T/err"
has "$T/err" "secret-only" && ok "bundle failure still secret-only" || { bad "bundle fallback"; cat "$T/err"; }
# trivy 0.76.1 phones home (check.trivy.dev) even with --offline-scan: both calls, the secret-only rerun too, start with the env opt-out
grep -q '^trivy TELEM=true .*--scanners vuln,misconfig' "$LOG" && grep -q '^trivy TELEM=true .*--scanners secret' "$LOG" && ! grep -q '^trivy TELEM= ' "$LOG" && ok "trivy telemetry off on the scan and the secret-only rerun" || { bad "trivy telemetry env"; cat "$LOG"; }
# 4. semgrep: XDG cache is the temp dir too
grep -Eq "^semgrep XDG=.*review-sg\." "$LOG" && ok "semgrep XDG_CACHE_HOME is a temp dir" || bad "semgrep XDG"
# 5. --repo replaces cd && chains
cd "$T"
bash "$S/review_checks.sh" --repo "$T/repo" --base base >"$T/out" 2>"$T/err" && has "$T/err" "analyzers ran:" && ok "--repo runs from another cwd" || bad "--repo"
bash "$S/review_checks.sh" --repo "$T/none" >/dev/null 2>&1 && bad "--repo bad dir" || ok "--repo rejects a non-directory"
! grep -nE '(cd [^;&]*&& *(gitleaks|osv-scanner|trivy|semgrep|actionlint))' "$S/review_checks.sh" "$S/supply_chain_check.sh" >/dev/null && ok "no cd-chained tool invocations in the hub" || bad "cd chain present"
# 6. supply_chain_check: dev-only cap. Same critical advisory on a dev-only package fails --fail-on high only when prod-reachable.
cd "$T/repo"
rc=0; o=$(REVIEW_OSV_DB_DIR="$T/db" bash "$S/supply_chain_check.sh" --online --allow-skip --fail-on high "$T/repo" 2>&1) || rc=$?
[ "$rc" = 0 ] && printf '%s' "$o" | grep -q 'critical=1' && printf '%s' "$o" | grep -q 'devpkg@1.0.0 GHSA-d fixed in: none (reach: dev-only)' && ok "dev-only critical skips the gate, noted" || { bad "dev-only cap (rc=$rc)"; printf '%s\n' "$o"; }
printf '{"packages":{"node_modules/devpkg":{"version":"1.0.0"}}}' >package-lock.json
rc=0; o=$(REVIEW_OSV_DB_DIR="$T/db" bash "$S/supply_chain_check.sh" --online --allow-skip --fail-on high "$T/repo" 2>&1) || rc=$?
[ "$rc" = 1 ] && printf '%s' "$o" | grep -q 'critical=1' && ! printf '%s' "$o" | grep -q 'dev-only' && ok "prod-reachable critical is not capped" || { bad "prod critical (rc=$rc)"; printf '%s\n' "$o"; }
# 6b. same name@version both dev (nested) and prod: not downgraded
printf '{"packages":{"node_modules/devpkg":{"version":"1.0.0"},"node_modules/x/node_modules/devpkg":{"version":"1.0.0","dev":true}}}' >package-lock.json
rc=0; o=$(REVIEW_OSV_DB_DIR="$T/db" bash "$S/supply_chain_check.sh" --online --allow-skip --fail-on high "$T/repo" 2>&1) || rc=$?
[ "$rc" = 1 ] && printf '%s' "$o" | grep -q 'critical=1' && ! printf '%s' "$o" | grep -q 'dev-only' && ok "prod+dev same package is not downgraded" || { bad "prod+dev (rc=$rc)"; printf '%s\n' "$o"; }
# 7. supply_chain_check: empty DB dir keeps the failure (no API fallback) and says how to warm
: >"$LOG"
rm -r "$T/db/seed" "$T/db/osv-scanner"
rc=0; o=$(REVIEW_OSV_DB_DIR="$T/db" bash "$S/supply_chain_check.sh" --online --allow-skip "$T/repo" 2>&1) || rc=$?
[ "$rc" != 0 ] && printf '%s' "$o" | grep -qF "FAIL osv-scanner: NOT CHECKED, no pre-seeded DB; warm it once: $WARM" && ! grep -q '^osv ' "$LOG" && ok "supply_chain_check warm hint" || { bad "sc warm hint"; printf '%s\n' "$o"; }
# 8. actionlint runs as a bare command on the workflow files
mkdir -p "$T/wfp/.github/workflows"; : >"$T/wfp/.github/workflows/ci.yml"; : >"$LOG"
bash "$S/supply_chain_check.sh" --allow-skip "$T/wfp" >/dev/null 2>&1 || true
grep -q "^actionlint .*ci.yml" "$LOG" && ok "actionlint runs on workflow files" || { bad "actionlint"; cat "$LOG"; }
mkdir -p "$T/nowf/.github/workflows"; : >"$LOG"
o=$(bash "$S/supply_chain_check.sh" --allow-skip "$T/nowf" 2>&1) || true
! grep -q '^actionlint .*\.yml' "$LOG" && ! printf '%s' "$o" | grep -q 'ok actionlint' && printf '%s' "$o" | grep -q 'no workflow files' && ok "empty workflows dir: skip, not ok" || { bad "actionlint 0 files"; printf '%s\n' "$o"; }
# 9. preflight require_files: warn only
printf '{"gates":[{"name":"g","command":"true","cheap":true}],"require_files":[".env.production"]}' >"$T/pf.json"
rc=0; o=$(python3 -I "$ROOT/.claude/skills/agentic-delivery/scripts/preflight.py" "$T/pf.json" --cache "$T/times.json" 2>&1 >/dev/null) || rc=$?
printf '%s' "$o" | grep -q 'required file missing: .env.production' && [ "$rc" = 0 ] && ok "preflight warns on missing env template, exit unaffected" || { bad "preflight require_files (rc=$rc)"; printf '%s\n' "$o"; }
exit $fail
