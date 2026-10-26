#!/usr/bin/env bash
# Tests for sandbox fallbacks (stub tools, no network): osv-scanner CLI crash -> OSV API via curl, semgrep HOME in a
# temp dir, trivy misconfig-bundle failure -> secret-only. Each degraded run must say so; --allow-skip semantics stay.
# shellcheck disable=SC2015,SC2016
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$ROOT/.claude/skills/deep-code-review/scripts"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-sbfb.XXXXXX"); trap 'rm -rf "$T"' EXIT
export PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 LOG="$T/log"; : >"$LOG"
fail=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }
mkdir "$T/stub" "$T/repo"
cat >"$T/stub/osv-scanner" <<'X'
#!/usr/bin/env bash
echo "tls: failed to verify certificate: x509: OSStatus -26276" >&2; exit 127
X
cat >"$T/stub/curl" <<'X'
#!/usr/bin/env bash
echo "curl $*" >>"$LOG"
case "$*" in
  *querybatch*) echo '{"results":[{"vulns":[{"id":"GHSA-x"}]},{}]}' ;;
  *vulns/GHSA-x*) echo '{"id":"GHSA-x","database_specific":{"severity":"HIGH"},"affected":[{"ranges":[{"events":[{"fixed":"2.0.0"}]}]}]}' ;;
  *) exit 6 ;;
esac
X
cat >"$T/stub/semgrep" <<'X'
#!/usr/bin/env bash
echo "semgrep HOME=$HOME SEMGREP_USER_HOME=$SEMGREP_USER_HOME" >>"$LOG"; echo '{"results":[]}'
X
cat >"$T/stub/trivy" <<'X'
#!/usr/bin/env bash
echo "trivy $*" >>"$LOG"
[ -n "${TRIVY_CRASH:-}" ] && { echo "panic: nil pointer" >&2; exit 2; }
case "$*" in *misconfig*) echo "FATAL check bundle: dial check.trivy.dev blocked" >&2; exit 1 ;; esac
echo '{"Results":[{"Target":"app.txt","Secrets":[{"RuleID":"aws-key","Title":"AWS key","StartLine":3,"Match":"LEAKVALUE"}]}]}'
X
chmod +x "$T/stub"/*
export PATH="$T/stub:$PATH"

# 1. osv API fallback (supply_chain_check.sh)
mkdir "$T/proj"
printf '{"packages":{"":{},"node_modules/left-pad":{"version":"1.0.0"},"node_modules/ok":{"version":"1.1.0"}}}' >"$T/proj/package-lock.json"
rc=0; o=$(bash "$S/supply_chain_check.sh" --online --allow-skip "$T/proj" 2>&1) || rc=$?
[ "$rc" = 1 ] && printf '%s' "$o" | grep -q 'osv: api-fallback' && printf '%s' "$o" | grep -q 'high=1' && printf '%s' "$o" | grep -q 'left-pad@1.0.0 GHSA-x fixed in: 2.0.0' && grep -q 'api.osv.dev/v1/querybatch' "$LOG" && ok "osv api-fallback finds + fails at threshold" || { bad "osv api-fallback (rc=$rc)"; printf '%s\n' "$o"; }
rc=0; o=$(bash "$S/supply_chain_check.sh" --online --allow-skip "$T/repo" 2>&1) || rc=$?
[ "$rc" = 1 ] && printf '%s' "$o" | grep -q 'FAIL osv-scanner: exit 127' && ok "osv fallback with no lockfiles keeps CLI failure" || { bad "osv no lockfiles (rc=$rc)"; printf '%s\n' "$o"; }

# 1b. partial coverage: unread lockfile -> message, FAIL; --allow-skip keeps rc 0 (no advisories here -> use clean proj)
mkdir "$T/proj2" "$T/proj2/vendor"; printf '{"packages":{"node_modules/a":{"version":"1.0.0"},"node_modules/ok":{"version":"1.1.0"}}}' >"$T/proj2/package-lock.json"
: >"$T/proj2/Cargo.lock"; : >"$T/proj2/vendor/go.sum"
rc=0; o=$(bash "$S/supply_chain_check.sh" --online --fail-on critical "$T/proj2" 2>&1) || rc=$?
[ "$rc" = 1 ] && printf '%s' "$o" | grep -q 'partial coverage: .*Cargo.lock not checked' && ! printf '%s' "$o" | grep -q 'go.sum' && ok "partial coverage fails; vendor pruned" || { bad "partial coverage (rc=$rc)"; printf '%s\n' "$o"; }
rc=0; o=$(bash "$S/supply_chain_check.sh" --online --allow-skip --fail-on critical "$T/proj2" 2>&1) || rc=$?
[ "$rc" = 0 ] && printf '%s' "$o" | grep -q 'partial coverage' && ok "partial coverage allowed with --allow-skip" || { bad "partial allow-skip (rc=$rc)"; printf '%s\n' "$o"; }
# 1c. result-count mismatch fails closed (stub returns 2 results; 3 packages queried) -> CLI failure kept
mkdir "$T/proj3"; printf '{"packages":{"node_modules/a":{"version":"1.0.0"},"node_modules/b":{"version":"1.0.0"},"node_modules/c":{"version":"1.0.0"}}}' >"$T/proj3/package-lock.json"
rc=0; o=$(bash "$S/supply_chain_check.sh" --online --allow-skip "$T/proj3" 2>&1) || rc=$?
[ "$rc" = 1 ] && printf '%s' "$o" | grep -q 'FAIL osv-scanner: exit 127' && ! printf '%s' "$o" | grep -q 'api-fallback' && ok "osv result-count mismatch fails closed" || { bad "osv count mismatch (rc=$rc)"; printf '%s\n' "$o"; }

# 2+3. review_checks.sh: semgrep temp HOME, trivy secret-only
cd "$T/repo"
git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base && git branch base
printf 'x\n' >app.txt; echo 'rules: []' >.semgrep.yml
git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files
: >"$LOG"
bash "$S/review_checks.sh" --base base >"$T/out" 2>"$T/err"
grep -Eq '^semgrep HOME=.*review-sg\..+ SEMGREP_USER_HOME=.*review-sg\.' "$LOG" && [ "$HOME" != "$(sed -n 's/^semgrep HOME=\([^ ]*\) .*/\1/p' "$LOG")" ] && ok "semgrep HOME is a temp dir" || bad "semgrep HOME"
grep -q 'trivy: secret-only (misconfig bundle unreachable)' "$T/err" && ok "trivy says secret-only" || bad "trivy message"
grep -q 'analyzers ran:.*trivy(secret-only)' "$T/err" && ok "trivy degraded recorded in summary" || bad "trivy summary"
[ "$(grep -- '--scanners vuln,misconfig' "$LOG" | grep -c -- '--skip-check-update')" = 0 ] && ok "primary trivy scan lacks --skip-check-update" || bad "primary trivy flags"
grep -q -- '--scanners secret' "$LOG" && grep -q -- '--skip-version-check' "$LOG" && grep -q -- '--skip-check-update' "$LOG" && ok "trivy fallback flags" || bad "trivy flags"
# non-network trivy crash: no secret-only retry
: >"$LOG"; TRIVY_CRASH=1 bash "$S/review_checks.sh" --base base >"$T/out2" 2>"$T/err2"
! grep -q -- '--scanners secret' "$LOG" && ! grep -q 'secret-only' "$T/err2" && grep -q 'not run: trivy (exit 2)' "$T/err2" && ok "no secret-only retry on non-network failure" || bad "trivy crash retry"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert any(r["tool"]=="trivy" and r["rule"]=="aws-key" and r["line"]==3 for r in d); assert "LEAKVALUE" not in open(sys.argv[1]).read()' "$T/out" && ok "secret row kept, Match never printed" || bad "secret row"
[ "$fail" = 0 ]
