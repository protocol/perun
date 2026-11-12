#!/usr/bin/env bash
# review_checks.sh supply-chain routes, hermetic (temp repo, stub binaries, fictional names, no network):
# dep_risk.py flags new or changed deps only (typosquat-near, git/URL spec, floating spec, install script) and leaves decoys alone
# (the real popular name, scoped names, caret ranges, a pinned dep, an unchanged git dep); codeql routes only when installed (NOT CHECKED
# otherwise, never clean), keeps rows on changed files only, and a failing analyze is "not run".
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/scrisk.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 PERUN_HEAVY_DIR="$T/heavy" CQ_LOG="$T/cq.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN=
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
cat >package.json <<'J'
{
  "name": "acme-app",
  "dependencies": {
    "legacy-git": "git+https://example.com/acme/legacy.git"
  }
}
J
echo 'pinned==1.0' >requirements.txt
printf '[project]\nname = "acme"\ndependencies = [\n  "reqeusts",\n  "pydantic==2.0",\n]\n' >pyproject.toml
G add . && G commit -q -m base && git branch base
cat >package.json <<'J'
{
  "name": "acme-app",
  "scripts": { "postinstall": "node setup.js", "prepare": "node build.js" },
  "dependencies": {
    "legacy-git": "git+https://example.com/acme/legacy.git",
    "react": "^18.2.0",
    "reactt": "1.0.0",
    "@acme/reactt": "1.0.0",
    "owner-lib": "acme/owner-lib#main",
    "floaty": "*",
    "lodash-es": "4.17.21",
    "colors": "1.4.0",
    "color": "4.2.3",
    "moments": "1.0.0",
    "sibling": "workspace:*",
    "aliased": "npm:left-pad@1.3.0"
  }
}
J
cat >requirements.txt <<'R'
pinned==1.0
reqeusts==2.0.0
python_dateutil==2.9.0
requests==2.31.0
looseness
-e git+https://example.com/acme/pkg.git#egg=pkg
--extra-index-url https://example.com/simple
boto==2.0.0
jinja2==3.1.0
psycopg==3.1.0
beautifulsoup==3.2.2
R
cat >pyproject.toml <<'P'
[project]
name = "acme"
dependencies = [
  "reqeusts",
  "reqeusts-extra",
  "pydantic==2.0",
]
P
printf 'from setuptools import setup\nsetup(cmdclass={"install": X})\n' >setup.py
printf 'x = 1\n' >app.py; printf 'let y = 1;\n' >other.js
G add . && G commit -q -m change
cat >"$T/bin/codeql" <<'S'
#!/usr/bin/env bash
echo "codeql $*" >>"$CQ_LOG"
case "$2" in
  create) exit 0 ;;
  analyze) [ "${CQ_MODE:-}" != crash ] || exit 9
    for a in "$@"; do case $a in --output=*) o=${a#--output=} ;; esac; done
    printf '%s\n' "$CQ_SARIF" >"$o" ;;
esac
S
chmod +x "$T/bin/codeql"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
res() { printf '{"ruleId":"py/sql-injection","message":{"text":"query built from user input"},"locations":[{"physicalLocation":{"artifactLocation":{"uri":"%s"},"region":{"startLine":3}}}]}' "$1"; }
export CQ_SARIF="{\"runs\":[{\"results\":[$(res app.py),$(res untouched.py)]}]}"
run() { local p=$1; shift; PATH="$p:$T/base:$T/sys" bash "$RC" --base "${BASE:-base}" 2>"$T/err" >"$T/out"; }
has() { jq -e --arg f "$1" --arg r "$2" --arg m "$3" 'any(.[]; .tool=="dep-risk" and .file==$f and .rule==$r and (.message|test($m)))' "$T/out" >/dev/null; }
run "$T/bin"
for c in 'package.json typosquat-near reactt' 'package.json vcs-or-url-dep owner-lib' 'package.json unpinned-dep floaty' 'package.json install-script postinstall' \
         'requirements.txt typosquat-near reqeusts' 'requirements.txt unpinned-dep looseness' 'requirements.txt vcs-or-url-dep acme/pkg' 'setup.py install-script cmdclass' 'package.json install-script prepare' 'package.json npm-alias left-pad' 'requirements.txt dependency-confusion extra-index-url'; do
  set -- $c; has "$1" "$2" "$3" && ok "positive: $1 $2" || bad "positive: $1 $2"
done
n=$(jq '[.[] | select(.tool=="dep-risk")] | length' "$T/out")
[ "$n" = 11 ] && ok "decoys quiet: exactly the 11 leads (real react, colors/color/moments, boto/jinja2 siblings, workspace:, unchanged pyproject squat, added unrelated pyproject line, @scope name, ^ range, pinned dep, python_dateutil, lodash-es, unchanged git dep)" || { bad "decoys: expected 11 dep-risk rows, got $n"; jq -c '.[]|select(.tool=="dep-risk")|[.file,.rule]' "$T/out"; }
grep -qE "analyzers ran:.*\bdep-risk\b" "$T/err" && ok "dep-risk listed as ran" || bad "dep-risk listed as ran"
# codeql: installed -> default queries, offline, rows only on changed files
jq -e 'any(.[]; .tool=="codeql" and .file=="app.py" and .rule=="py/sql-injection")' "$T/out" >/dev/null && ok "codeql row on a changed file" || bad "codeql row on a changed file"
jq -e 'any(.[]; .tool=="codeql" and .file=="untouched.py")|not' "$T/out" >/dev/null && ok "codeql row on an unchanged file dropped" || bad "unchanged-file row kept"
grep -q 'analyze .*--no-download' "$T/cq.log" && ! grep -q 'config auto' "$T/cq.log" && ok "analyze runs --no-download" || bad "analyze flags"
grep -q 'create .*--language=javascript-typescript' "$T/cq.log" && ok "js changes route their own language db" || bad "js language db"
# crash: not run, never clean
CQ_MODE=crash run "$T/bin"
grep -q 'not run: codeql (exit 9)' "$T/err" && ! grep -qE "analyzers ran:.*\bcodeql\b" "$T/err" && ok "analyze crash is not clean and not ran" || bad "analyze crash"
# missing binary: NOT CHECKED row, never clean
run ""
grep -q 'NOT CHECKED: codeql (install:' "$T/err" && jq -e 'any(.[]; .tool=="codeql" and .rule=="not-checked")' "$T/out" >/dev/null && ok "missing codeql: NOT CHECKED row" || bad "missing codeql"
# no py/js change: codeql and dep-risk stay out
: >"$T/cq.log"; echo hi >notes.txt; G add . && G commit -q -m docs && git branch docs
BASE=docs run "$T/bin"
[ ! -s "$T/cq.log" ] && ! grep -q 'codeql' "$T/err" && ! grep -q 'dep-risk' "$T/err" && ok "unrelated change routes neither" || bad "routed without a matching change"
grep -q 'dep_risk.py' "$ROOT/.claude/skills/deep-code-review/references/tool-hub.md" && ok "documented in tool-hub.md" || bad "documented in tool-hub.md"
exit $fail
