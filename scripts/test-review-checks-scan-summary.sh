#!/usr/bin/env bash
# Tests for review_checks.sh: stderr ran/skipped summary, default local semgrep rules, trivy offline, gitleaks --history.
# shellcheck disable=SC2015
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-rcsum.XXXXXX"); trap 'rm -rf "$T"' EXIT
fail=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }

mkdir "$T/stub" "$T/repo" "$T/cache"
cat >"$T/stub/gitleaks" <<'S'
#!/usr/bin/env bash
echo "gitleaks $*" >>"$GL_LOG"
while [ $# -gt 0 ]; do [ "$1" = -r ] && rep=$2; shift; done
echo '[{"RuleID":"hist-rule","Description":"old secret","StartLine":1,"File":"old.txt","Secret":"HISTVALUE"},{"RuleID":"hist-vendored","Description":"x","StartLine":1,"File":"node_modules/z.txt","Secret":"HISTVALUE"}]' >"$rep"
S
cat >"$T/stub/trivy" <<'S'
#!/usr/bin/env bash
echo "trivy $*" >>"$TV_LOG"
echo '{"Results":[{"Target":"app.txt","Vulnerabilities":[{"VulnerabilityID":"CVE-0000-0001","PkgName":"foo","InstalledVersion":"1.0","Title":"bad foo"}]},{"Target":"other.txt","Vulnerabilities":[{"VulnerabilityID":"CVE-0000-0002","PkgName":"bar","InstalledVersion":"1","Title":"unchanged file"}]}]}'
S
cat >"$T/stub/semgrep" <<'S'
#!/usr/bin/env bash
echo "semgrep $*" >>"$SG_LOG"
echo '{"results":[]}'
S
chmod +x "$T/stub"/*
export GL_LOG="$T/gl.log" TV_LOG="$T/tv.log" SG_LOG="$T/sg.log"; : >"$GL_LOG"; : >"$TV_LOG"; : >"$SG_LOG"

cd "$T/repo"
git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base
git branch base
printf 'x\n' >app.txt
git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files
export PERUN_HEAVY_DIR="$T/heavy0" # never touch the real lease dir
export DCR_CACHE_ROOT="$T/cache" # empty: a warm semgrep snapshot on the host would swap `--config p/default` for the local file
unset REVIEW_SEMGREP_REGISTRY # a host that sets it to 0 would drop the `--config p/default` this test expects
run() { PATH="$T/stub:$PATH" bash "$RC" --base base "$@" 2>"$T/err" >"$T/out"; }

run
jq -e 'any(.[]; .tool=="trivy" and .file=="app.txt" and .rule=="CVE-0000-0001") and all(.[]; .file!="other.txt")' "$T/out" >/dev/null && ok "trivy finding only for changed files" || bad "trivy changed files"
grep -q -- '--offline-scan' "$TV_LOG" && grep -q -- '--skip-db-update' "$TV_LOG" && ok "trivy offline" || bad "trivy offline"
grep -Eq 'review_checks: [0-9]+ findings; [0-9]+ files excluded; analyzers ran: .*trivy' "$T/err" && ok "stderr summary" || bad "stderr summary"
grep -q 'skipped (not installed):' "$T/err" && ok "summary skipped list" || bad "summary skipped list"
jq -e 'type=="array"' "$T/out" >/dev/null && ok "stdout stays JSON" || bad "stdout JSON"
grep -q -- '--log-opts' "$GL_LOG" && bad "history off by default" || ok "history off by default"
grep -q -- 'templates/semgrep-taint' "$SG_LOG" && grep -q -- '--config p/default' "$SG_LOG" && ! grep -q auto "$SG_LOG" && ok "semgrep bundled rules + p/default without repo rules" || bad "semgrep bundled default"

echo "rules: []" >.semgrep.yml
git add . && git -c user.email=t@example.com -c user.name=t commit -q -m rules
run
grep -q -- '--config .semgrep.yml' "$SG_LOG" && ! grep -q auto "$SG_LOG" && ok "semgrep default local rules" || bad "semgrep default rules"

run --history
grep -q -- '--log-opts base\.\.HEAD' "$GL_LOG" && ok "gitleaks history from base only" || bad "history from base only"
jq -e 'any(.[]; .tool=="gitleaks-history" and .rule=="hist-rule")' "$T/out" >/dev/null && ok "history finding" || bad "history finding"
grep -q HISTVALUE "$T/out" "$T/err" && bad "history secret never printed" || ok "history secret never printed"
: >"$GL_LOG"; run --full-history
grep -q -- 'detect.* -r ' "$GL_LOG" && ! grep -q -- '--log-opts' "$GL_LOG" && ok "full history has no base bound" || bad "full history"

# Default excludes: vendored, build and worktree dirs are never handed to any scanner.
mkdir -p node_modules/p .claude/worktrees/w vendor
printf 'x\n' >node_modules/p/a.txt; printf 'x\n' >.claude/worktrees/w/b.txt; printf 'x\n' >vendor/c.txt; printf 'x\n' >real.txt
git add -f . && git -c user.email=t@example.com -c user.name=t commit -q -m vendored
: >"$GL_LOG"; : >"$SG_LOG"; run
grep -q 'real.txt' "$GL_LOG" && ! grep -Eq 'node_modules|worktrees|vendor' "$GL_LOG" "$SG_LOG" && ok "default excludes" || bad "default excludes"
grep -q -- '--skip-dirs node_modules,.claude/worktrees,vendor' "$TV_LOG" && ok "trivy skip-dirs" || bad "trivy skip-dirs"

# Heavy lease: with one slot (tokens=off) taken by a live holder, REVIEW_LEASE_FULL=skip skips heavy scanners (default: degraded, see test-review-checks-lease-degraded.sh).
export PERUN_HEAVY_DIR="$T/heavy" PERUN_POLICY="$T/policy.json" REVIEW_LEASE_WAIT=0
mkdir "$T/heavy"; echo '{"tokens":"off"}' >"$T/policy.json"
sleep 30 & holder=$!
echo "$holder $(date +%s)" >"$T/heavy/$holder"
: >"$GL_LOG"; REVIEW_LEASE_FULL=skip run
kill "$holder" 2>/dev/null || true; wait "$holder" 2>/dev/null || true
grep -q 'not run: gitleaks (heavy lease full)' "$T/err" && [ ! -s "$GL_LOG" ] && ok "heavy lease full skips scanners" || bad "heavy lease full"
: >"$GL_LOG"; run --history
jq -e 'any(.[]; .tool=="gitleaks-history" and .rule=="hist-rule") and all(.[]; .tool!="gitleaks-history" or .rule!="hist-vendored")' "$T/out" >/dev/null && ok "history rows under excluded paths dropped" || bad "history excluded rows"
grep -Eq '[1-9][0-9]* files excluded' "$T/err" && ok "summary counts excluded files" || bad "excluded count"

# A broken perun_policy.py (rc 2) is reported once and fails open: the scanner still runs.
unset REVIEW_LEASE_WAIT; echo '{bad' >"$T/policy.json"
: >"$GL_LOG"; run
grep -q 'not run: lease (policy rc=2)' "$T/err" && [ -s "$GL_LOG" ] && ok "policy error reported, fails open" || bad "policy error"

# Option injection: a --base starting with '-' is refused before git sees it.
bash "$RC" --base --output=x 2>"$T/err" >/dev/null && bad "dash base refused" || { grep -q "must not start with '-'" "$T/err" && ok "dash base refused" || bad "dash base refused"; }
exit "$fail"
