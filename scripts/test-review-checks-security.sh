#!/usr/bin/env bash
# Tests for the optional gitleaks / osv-scanner / semgrep scanners in review_checks.sh, using stub binaries on
# PATH that emit fixture JSON (no real tool needed): findings land in the shared JSON shape, the gitleaks secret
# never reaches stdout, osv runs only for lockfiles, semgrep needs a local config and never gets `auto`.
# shellcheck disable=SC2015,SC2119,SC2120
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-rcsec.XXXXXX"); trap 'rm -rf "$T"' EXIT
export PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 # isolate from the real machine-wide lease dir
fail=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }

mkdir "$T/stub" "$T/repo"
# gitleaks stub: writes the report to the path after -r, with a plaintext Secret the script must not echo.
cat >"$T/stub/gitleaks" <<'S'
#!/usr/bin/env bash
while [ $# -gt 0 ]; do [ "$1" = -r ] && rep=$2; [ "$1" = -s ] && src=$2; shift; done
case "$src" in *leak.txt) printf '[{"RuleID":"generic-api-key","Description":"Generic API Key","StartLine":3,"File":"%s","Secret":"SUPERSECRETVALUE","Match":"key=SUPERSECRETVALUE"}]' "$src" >"$rep" ;; *) echo '[]' >"$rep" ;; esac
S
cat >"$T/stub/osv-scanner" <<'S'
#!/usr/bin/env bash
echo "osv-scanner $*" >>"$OSV_LOG"
echo 'Scanning...'
echo '{"results":[{"source":{"path":"x"},"packages":[{"package":{"name":"left-pad","version":"1.0.0"},"vulnerabilities":[{"id":"GHSA-test-0001","summary":"bad pad"}]}]}]}'
S
cat >"$T/stub/semgrep" <<'S'
#!/usr/bin/env bash
echo "semgrep $*" >>"$SG_LOG"
echo '{"results":[{"check_id":"local.rule","path":"leak.txt","start":{"line":2},"extra":{"message":"no eval"}}]}'
S
chmod +x "$T/stub"/*

cd "$T/repo"
git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base
git branch base
printf 'a\nb\nkey=SUPERSECRETVALUE\n' >leak.txt
printf 'clean\n' >clean.txt
printf '{}\n' >package-lock.json
printf 'flask==1.0\n' >requirements-dev.txt
git add . && git -c user.email=t@example.com -c user.name=t commit -q -m files
export OSV_LOG="$T/osv.log" SG_LOG="$T/sg.log"
: >"$OSV_LOG"; : >"$SG_LOG"
echo "rules: []" >"$T/semgrep.yml"

run() { PATH="$T/stub:$PATH" bash "$RC" --base base "$@" 2>"$T/err" >"$T/out"; }
has() { jq -e --arg f "$1" --arg t "$2" --arg r "$3" 'any(.[]; .file==$f and .tool==$t and .rule==$r)' "$T/out" >/dev/null; }

REVIEW_OSV=1 run
has leak.txt gitleaks generic-api-key && ok "gitleaks finding" || bad "gitleaks finding"
jq -e 'any(.[]; .tool=="gitleaks" and .file=="clean.txt")' "$T/out" >/dev/null && bad "gitleaks clean file silent" || ok "gitleaks clean file silent"
grep -q SUPERSECRETVALUE "$T/out" "$T/err" && bad "secret never printed" || ok "secret never printed"
jq -e 'all(.[]; has("file") and has("line") and has("rule") and has("message") and has("tool") and has("text"))' "$T/out" >/dev/null && ok "schema keys" || bad "schema keys"
has package-lock.json osv-scanner GHSA-test-0001 && has requirements-dev.txt osv-scanner GHSA-test-0001 && ok "osv lockfiles" || bad "osv lockfiles"
[ "$(wc -l <"$OSV_LOG")" -eq 2 ] && ! grep -q 'leak.txt\|clean.txt' "$OSV_LOG" && ok "osv only on lockfiles" || bad "osv only on lockfiles"
grep -q 'not run: semgrep (no local rules' "$T/err" && [ ! -s "$SG_LOG" ] && ok "semgrep needs config" || bad "semgrep needs config"
: >"$OSV_LOG"; run
grep -q 'not run: osv-scanner (REVIEW_OSV not set' "$T/err" && [ ! -s "$OSV_LOG" ] && ok "osv needs REVIEW_OSV" || bad "osv needs REVIEW_OSV"

REVIEW_SEMGREP_CONFIG=auto run
grep -q 'must be an existing local path' "$T/err" && [ ! -s "$SG_LOG" ] && ok "semgrep auto refused" || bad "semgrep auto refused"
REVIEW_SEMGREP_CONFIG="$T/semgrep.yml" run
has leak.txt semgrep local.rule && ok "semgrep finding" || bad "semgrep finding"
grep -q -- "--config $T/semgrep.yml" "$SG_LOG" && grep -q -- '--metrics=off' "$SG_LOG" && ! grep -q 'auto' "$SG_LOG" && ok "semgrep local config, metrics off" || bad "semgrep args"

# No installed scanners => not-run lines, exit 0.
mkdir "$T/bin"
for c in git python3 bash sed grep head tail mktemp rm cat dirname perl env; do ln -s "$(command -v "$c")" "$T/bin/" 2>/dev/null || true; done
REVIEW_OSV=1 PATH="$T/bin" bash "$RC" --base base >"$T/out2" 2>"$T/err2" && ok "missing scanners exit 0" || bad "missing scanners exit 0"
grep -q 'not run: gitleaks (not installed)' "$T/err2" && grep -q 'not run: osv-scanner (not installed)' "$T/err2" && ok "scanner not-run lines" || bad "scanner not-run lines"
exit "$fail"
