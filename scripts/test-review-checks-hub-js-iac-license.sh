#!/usr/bin/env bash
# review_checks.sh hub routing for eslint-security (project-local eslint only), kics (IaC) and licensee (license inventory), with stub binaries on a
# hermetic PATH (no real tool, no network): findings land as rows, licensee only names the license (stderr, no row, never ran/wired), a missing tool is
# "NOT CHECKED", a crash or wrong-shape JSON is "not run" (never clean), eslint never runs without its own config and local binary or when the diff changes its config.
# REVIEW_CHECKS=<path> runs another copy of the script (used to prove the cases fail before the change).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubjil.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'module.exports = [];\n' >eslint.config.js; printf '{}\n' >package.json
G add . && G commit -q -m base && git branch base
printf 'eval(x);\n' >app.js; printf 'FROM scratch\n' >Dockerfile; printf 'resource "x" "y" {}\n' >main.tf
printf 'apiVersion: apps/v1\nkind: Deployment\n' >deploy.yaml; printf 'name: ci\non: push\n' >plain.yaml; printf 'MIT License\n' >LICENSE
printf 'a' >'we,ird.tf'
G add . && G commit -q -m files
mkdir -p node_modules/.bin
cat >"$T/stub" <<'S'
#!/usr/bin/env bash
n=${0##*/}; v=J_${n//-/_}
echo "$n $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
if [ "$n" = kics ]; then while [ $# -gt 0 ]; do [ "$1" != -o ] || printf '%s' "$J_kics" >"$2/results.json"; shift; done; exit "${KICS_RC:-50}"; fi
printf '%s\n' "${!v}"
[ "$n" != eslint ] || exit "${ES_RC:-1}"
S
cp "$T/stub" "$T/bin/kics"; cp "$T/stub" "$T/bin/licensee"; cp "$T/stub" node_modules/.bin/eslint; chmod +x "$T/bin/kics" "$T/bin/licensee" node_modules/.bin/eslint
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
P="$(pwd -P)"
export J_eslint="[{\"filePath\":\"$P/app.js\",\"messages\":[{\"ruleId\":\"no-eval\",\"line\":1,\"message\":\"eval can be harmful.\"},{\"ruleId\":\"semi\",\"line\":1,\"message\":\"style\"},{\"ruleId\":null,\"line\":1,\"message\":\"File ignored\"}]}]"
export J_kics='{"queries":[{"query_name":"Run Using Sudo","severity":"HIGH","files":[{"file_name":"Dockerfile","line":1,"search_key":"FROM={{scratch}}.RUN","actual_value":"SECRET"}]}]}'
export J_licensee='{"licenses":[{"spdx_id":"MIT"}],"matched_files":[]}'
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
nck() { jq -e --arg t "$1" 'any(.[]; .tool==$t and .rule=="not-checked" and .file=="")' "$T/out" >/dev/null; }
: >"$HUB_LOG"; run
row eslint-security app.js no-eval && ok "eslint-security: no-eval row" || bad "eslint row"
jq -e 'any(.[]; .tool=="eslint-security" and .rule=="semi")|not' "$T/out" >/dev/null && ok "eslint-security: style rule dropped" || bad "eslint style row"
grep -q '^eslint -f json ./app.js$' "$HUB_LOG" && ok "eslint-security: local binary, -f json, changed JS only" || bad "eslint args"
row kics Dockerfile "Run Using Sudo" && ok "kics: row on the Dockerfile" || bad "kics row"
! grep -q SECRET "$T/out" && ok "kics: actual_value never read" || bad "kics value leak"
grep -qE '^kics scan -p ./Dockerfile,./deploy.yaml,./main.tf --no-progress --disable-secrets --report-formats json -o .*/kics$' "$HUB_LOG" && ok "kics: Dockerfile, k8s yaml, .tf; no plain yaml or comma name; offline flags" || bad "kics args: $(grep ^kics "$HUB_LOG")"
grep -q '^licensee detect --json ./LICENSE$' "$HUB_LOG" && grep -q 'license inventory (not a scan): licensee detected MIT in LICENSE' "$T/err" && ok "licensee: names MIT on stderr" || bad "licensee line: $(grep -i licensee "$T/err" "$HUB_LOG" | head -4)"
jq -e 'any(.[]; .tool=="licensee")|not' "$T/out" >/dev/null && ! grep -qE "analyzers ran:.*\blicensee\b|wired.*licensee" "$T/err" && ok "licensee: no row, never ran/wired" || bad "licensee row/ran"
grep -qE "analyzers ran:.*\bkics\b.*" "$T/err" && grep -qE "analyzers ran:.*\beslint-security\b" "$T/err" && ok "kics and eslint-security listed as ran" || bad "ran list"
# missing tools (eslint local binary removed)
mv node_modules/.bin/eslint "$T/eslint.keep"; PATH="$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"
for t in eslint-security kics licensee; do grep -qE "^NOT CHECKED: $t \(install: .+\)" "$T/err" && nck "$t" && ok "$t missing: NOT CHECKED + row" || bad "$t missing"; done
mv "$T/eslint.keep" node_modules/.bin/eslint
# crash and wrong shape fail closed
for t in kics licensee; do HUB_MODE=crash run; grep -q "not run: $t (exit 9)" "$T/err" && nck "$t" && ok "$t crash: not run, not clean" || bad "$t crash"; done
HUB_MODE=crash run; grep -q "not run: eslint-security (exit 9)" "$T/err" && ok "eslint-security crash: not run" || bad "eslint crash"
ES_RC=2 run; grep -q "not run: eslint-security (exit 2)" "$T/err" && ! row eslint-security app.js no-eval && ok "eslint exit 2: not run" || bad "eslint exit 2"
J_eslint='{"x":1}' run; grep -q 'not run: eslint-security (unparseable' "$T/err" && ok "eslint wrong shape: not run" || bad "eslint shape"
J_eslint='[{"filePath":"a.js","messages":[{"fatal":true,"ruleId":null,"message":"Parsing error"}]}]' run; grep -q 'not run: eslint-security (unparseable' "$T/err" && ok "eslint fatal parse error: not run" || bad "eslint fatal"
J_kics='{"x":1}' run; grep -q 'not run: kics (unparseable' "$T/err" && ok "kics wrong shape: not run" || bad "kics shape"
KICS_RC=126 run; grep -q 'not run: kics (exit 126)' "$T/err" && ok "kics engine error 126: not run" || bad "kics 126"
J_licensee='nope' run; grep -q 'not run: licensee (unparseable' "$T/err" && ok "licensee wrong shape: not run" || bad "licensee shape"
J_kics='{"queries":null}' KICS_RC=0 run; ! grep -q 'not run: kics' "$T/err" && ! row kics Dockerfile "Run Using Sudo" && ok "kics clean (queries null, exit 0): no rows" || bad "kics clean"
# eslint gating: no config at all is not routed; a diff that changes the config (code) does not run it
G rm -q eslint.config.js; G commit -q -m noconf; : >"$HUB_LOG"; run
! grep -q '^eslint ' "$HUB_LOG" && ! grep -q 'NOT CHECKED: eslint-security' "$T/err" && ok "no eslint config: not routed" || bad "no config gating"
G checkout -q HEAD~1 -- eslint.config.js; printf '{"a":1}\n' >package.json; G add -A; G commit -q -m pkg; : >"$HUB_LOG"; run
! grep -q '^eslint ' "$HUB_LOG" && grep -q 'NOT CHECKED: eslint-security (eslint config or package.json changed' "$T/err" && nck eslint-security && ok "package.json changed in the diff: eslint not run" || bad "config-changed guard"
[ "$fail" = 0 ] && echo "PASS" || { echo "FAILED"; exit 1; }
