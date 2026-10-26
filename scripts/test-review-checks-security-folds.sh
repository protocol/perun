#!/usr/bin/env bash
# Regression tests for review_checks.sh folds: malformed, empty or wrong-shape scanner JSON, scanner/linter crash
# codes and semgrep `errors` fail closed (a not-run line, never a silent clean); leading-dash filenames are never
# read as options; semgrep runs once for a normal changed-file set. REVIEW_CHECKS overrides the script under test
# (used to prove each check fails on the parent commit).
# shellcheck disable=SC2015,SC2119,SC2120
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-rcfolds.XXXXXX"); trap 'rm -rf "$T"' EXIT
export PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 # isolate from the real machine-wide lease dir
fail=0
ok() { printf 'ok   %s\n' "$1"; }
bad() { printf 'FAIL %s\n' "$1"; fail=1; }

mkdir "$T/stub" "$T/repo"
cat >"$T/stub/semgrep" <<'S'
#!/usr/bin/env bash
echo "semgrep $*" >>"$SG_LOG"
[ -z "${SG_EXIT:-}" ] || exit "$SG_EXIT"
if [ -n "${SG_OUT:-}" ]; then echo "$SG_OUT"; else echo '{"results":[]}'; fi
S
cat >"$T/stub/gitleaks" <<'S'
#!/usr/bin/env bash
echo "gitleaks $*" >>"$GL_LOG"
while [ $# -gt 0 ]; do [ "$1" = -r ] && rep=$2; shift; done
[ -z "${GL_EXIT:-}" ] || exit "$GL_EXIT"
if [ -n "${GL_FIRST_BAD:-}" ]; then # garbage on the first call only, nothing written afterwards
  [ -e "$GL_FIRST_BAD" ] && exit 0
  : >"$GL_FIRST_BAD"; printf 'not json' >"$rep"; exit 0
fi
printf '%s' "${GL_OUT-[]}" >"$rep"
S
cat >"$T/stub/osv-scanner" <<'S'
#!/usr/bin/env bash
echo "osv-scanner $*" >>"$OSV_LOG"
echo "${OSV_OUT-{\"results\":[]\}}"
exit "${OSV_EXIT:-0}"
S
for tool in shellcheck ruff node; do
  cat >"$T/stub/$tool" <<S
#!/usr/bin/env bash
echo "$tool \$*" >>"\$TOOL_LOG"
exit "\${EXIT_$tool:-0}"
S
done
chmod +x "$T/stub"/*

cd "$T/repo"
git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base
git branch base
printf 'a\n' >a.txt
printf 'b\n' >b.txt
printf '#!/bin/sh\necho hi\n' >./-v.sh
printf 'x = 1\n' >./-p.py
printf '1;\n' >./-n.js
printf '{}\n' >./-j.json
printf '{}\n' >package-lock.json
git add -- . && git -c user.email=t@example.com -c user.name=t commit -q -m files
export SG_LOG="$T/sg.log" GL_LOG="$T/gl.log" OSV_LOG="$T/osv.log" TOOL_LOG="$T/tool.log" REVIEW_SEMGREP_CONFIG="$T/rules.yml"
echo "rules: []" >"$REVIEW_SEMGREP_CONFIG"
: >"$SG_LOG"; : >"$GL_LOG"; : >"$OSV_LOG"; : >"$TOOL_LOG"
run() { PATH="$T/stub:$PATH" REVIEW_OSV=1 bash "$RC" --base base "$@" 2>"$T/err" >"$T/out"; }
errhas() { grep -qF -- "$1" "$T/err"; }
findings() { jq --arg t "$1" '[.[] | select(.tool==$t)] | length' "$T/out"; }

# Dash filenames: bash -n and jq would read them as options; every tool gets ./ or --.
run && ok "exit 0" || bad "exit 0"
jq -e 'any(.[]; .tool=="bash-n" or .tool=="jq")' "$T/out" >/dev/null && bad "dash file not read as option" || ok "dash file not read as option"
grep -q -- '-s ./-v.sh' "$GL_LOG" && ok "gitleaks gets ./ path" || bad "gitleaks gets ./ path"
grep -q -- '-L ./package-lock.json' "$OSV_LOG" && ok "osv-scanner gets ./ path" || bad "osv-scanner gets ./ path"
grep -q 'shellcheck .* ./-v.sh' "$TOOL_LOG" && grep -q 'ruff .* ./-p.py' "$TOOL_LOG" && grep -q 'node --check ./-n.js' "$TOOL_LOG" && ok "linters get ./ path" || bad "linters get ./ path"
# One semgrep call for the changed files, targets after --.
[ "$(wc -l <"$SG_LOG")" -eq 1 ] && grep -q -- ' -- .*a.txt' "$SG_LOG" && grep -q -- 'b.txt' "$SG_LOG" && ok "semgrep batched once" || bad "semgrep batched once"

# Malformed scanner output: not-run line, no findings, still exit 0.
SG_OUT='not json' GL_OUT='not json' OSV_OUT='not json' run && ok "bad json exit 0" || bad "bad json exit 0"
errhas 'not run: semgrep (unparseable output)' && errhas 'not run: gitleaks (unparseable report' && errhas 'not run: osv-scanner (unparseable output' && ok "bad json fails closed" || bad "bad json fails closed"
[ "$(findings semgrep)$(findings gitleaks)$(findings osv-scanner)" = 000 ] && ok "bad json no findings" || bad "bad json no findings"

# Wrong-shape JSON (valid JSON, missing results list) is not "clean".
SG_OUT='{"x":1}' OSV_OUT='{"results":null}' GL_OUT='{"x":1}' run
errhas 'not run: semgrep (unparseable output)' && errhas 'not run: osv-scanner (unparseable output' && errhas 'not run: gitleaks (unparseable report' && ok "wrong-shape json fails closed" || bad "wrong-shape json fails closed"

# gitleaks: an empty report for a clean file is [], not an error.
GL_OUT='' run
errhas 'gitleaks (unparseable' && bad "empty gitleaks report is clean" || ok "empty gitleaks report is clean"

# A bad report for one file must not leak into the next file's read.
GL_FIRST_BAD="$T/gl-first" run
[ "$(grep -c 'not run: gitleaks (unparseable report' "$T/err")" -eq 1 ] && ok "stale gitleaks report cleared" || bad "stale gitleaks report cleared"
rm -f "$T/gl-first"

# semgrep `errors` => partial-scan line, findings still reported.
SG_OUT='{"results":[{"check_id":"r","path":"a.txt","start":{"line":1},"extra":{"message":"m"}}],"errors":[{"message":"boom"}]}' run
errhas 'not run: semgrep (partial scan' && [ "$(findings semgrep)" = 1 ] && ok "semgrep errors surfaced" || bad "semgrep errors surfaced"

# Crash codes surfaced; osv exit 1 (vulnerabilities found) is not a crash.
SG_EXIT=3 run && ok "crash exit 0" || bad "crash exit 0"
errhas 'not run: semgrep (exit 3)' && ok "semgrep crash surfaced" || bad "semgrep crash surfaced"
GL_EXIT=2 run
errhas 'not run: gitleaks (exit 2)' && ok "gitleaks crash surfaced" || bad "gitleaks crash surfaced"
OSV_EXIT=127 run
errhas 'not run: osv-scanner (exit 127)' && ok "osv crash surfaced" || bad "osv crash surfaced"
OSV_EXIT=1 OSV_OUT='{"results":[{"source":{"path":"x"},"packages":[{"package":{"name":"p","version":"1"},"vulnerabilities":[{"id":"GHSA-x","summary":"s"}]}]}]}' run
errhas 'not run: osv-scanner' && bad "osv exit 1 is findings" || [ "$(findings osv-scanner)" = 1 ] && ok "osv exit 1 is findings" || bad "osv exit 1 is findings"
EXIT_shellcheck=2 EXIT_ruff=2 run
errhas 'not run: shellcheck (exit 2)' && errhas 'not run: ruff (exit 2)' && ok "linter crash surfaced" || bad "linter crash surfaced"
exit "$fail"
