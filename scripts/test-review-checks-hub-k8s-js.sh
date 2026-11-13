#!/usr/bin/env bash
# review_checks.sh hub routing for kubescape (plain Kubernetes manifests, local artifacts only) and retire (vulnerable vendored JS, local jsrepo only)
# with stub binaries on a hermetic PATH (no real tool, no network): rows keep findings, a missing tool or missing local data is "NOT CHECKED",
# and a crash, empty or whitespace output, an exit that disagrees with the report, or wrong-shape output is "not run", never clean.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubk8s.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home"
export KUBESCAPE_ARTIFACTS="$T/art" REVIEW_RETIRE_JSREPO="$T/jsrepository.json"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/art" "$T/home" && : >"$REVIEW_RETIRE_JSREPO" && : >"$T/art/nsa.json" && : >"$T/art/cis-v1.23-t1.0.1.json" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
mkdir -p k8s lib chart/templates
printf 'apiVersion: v1\nkind: Pod\nmetadata:\n  name: a\n' >k8s/d.yaml; printf 'a: 1\n' >k8s/plain.yaml; printf 'apiVersion: v1\nkind: Pod\n' >k8s/e.yaml; printf 'apiVersion: v1\nkind: Pod\n' >'k8s/my app.yaml'
printf 'var a=1;\n' >lib/v.min.js; G add . && G commit -q -m code
# stubs write their JSON to the file named after --output / --outputpath, like the real tools
cat >"$T/bin/kubescape" <<'S'
#!/usr/bin/env bash
echo "kubescape $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
t=${4#./}; o=; while [ $# -gt 0 ]; do [ "$1" != --output ] || o=$2; shift; done
case $o in *.json) ;; *) o=$o.json ;; esac  # real kubescape appends .json to an --output path that lacks it
printf '%s' "${J_ks//@F@/$t}" >"$o"
S
cat >"$T/bin/retire" <<'S'
#!/usr/bin/env bash
echo "retire $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
o=; while [ $# -gt 0 ]; do [ "$1" != --outputpath ] || o=$2; shift; done
printf '%s' "$J_re" >"$o"
exit "${RE_RC:-13}"
S
chmod +x "$T/bin/kubescape" "$T/bin/retire"; mkdir "$T/keep"; cp "$T/bin/kubescape" "$T/bin/retire" "$T/keep/"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
KS='{"resources":[{"resourceID":"r1","source":{"relativePath":"@F@"}}],"results":[{"resourceID":"r1","controls":[{"controlID":"C-0017","name":"Immutable container filesystem","status":{"status":"failed"}},{"controlID":"C-0013","name":"Non-root containers","status":{"status":"passed"}},{"controlID":"C-0055","name":"Linux hardening","status":{"status":"skipped"}}]}]}'
RE='{"version":"5.0.0","start":"x","data":[{"file":"lib/v.min.js","results":[{"component":"jquery","version":"1.6.1","vulnerabilities":[{"severity":"medium","identifiers":{"CVE":["CVE-2099-0001"],"summary":"xss in example"}}]},{"component":"other","version":"1","vulnerabilities":[]}]},{"file":"lib/other.js","results":[{"component":"x","version":"1","vulnerabilities":[{"severity":"low","identifiers":{"summary":"s"}}]}]}],"messages":[],"errors":[]}'
export J_ks=$KS J_re=$RE
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
: >"$HUB_LOG"; run
row kubescape k8s/d.yaml C-0017 && row kubescape k8s/e.yaml C-0017 && row kubescape "k8s/my app.yaml" C-0017 && [ "$(grep -c '^kubescape scan' "$HUB_LOG")" = 3 ] && grep -q -- 'framework nsa,cis-v1.23-t1.0.1 ./k8s/my app.yaml --format' "$HUB_LOG" && ! row kubescape k8s/d.yaml C-0013 && ! row kubescape k8s/d.yaml C-0055 && ran kubescape && ok "kubescape: one run per file (3 files, one with a space), failed control is a row, passed and skipped are not" || bad "ks rows: $(jq -c '[.[]|select(.tool=="kubescape")|.rule]' "$T/out")"
grep -q -- 'kubescape scan framework nsa,cis-v1.23-t1.0.1 ./k8s/d.yaml --format' "$HUB_LOG" && ! grep -q 'k8s/plain.yaml' "$HUB_LOG" && grep -q -- '--keep-local' "$HUB_LOG" && grep -q -- "--use-artifacts-from $T/art" "$HUB_LOG" && ok "kubescape argv: only the manifest, local artifacts, no backend report" || bad "ks argv: $(grep kubescape "$HUB_LOG")"
row retire lib/v.min.js CVE-2099-0001 && ! row retire lib/other.js retire-js && ran retire && ok "retire: CVE row on the changed file, unchanged file dropped" || bad "re rows: $(jq -c '[.[]|select(.tool=="retire")|.rule]' "$T/out")"
grep -q -- 'retire --path . --ignore node_modules --outputformat json' "$HUB_LOG" && grep -q -- "--jsrepo $T/jsrepository.json" "$HUB_LOG" && ok "retire argv: local jsrepo, node_modules ignored" || bad "re argv"
# never clean: empty, whitespace, wrong shape, errors, exit mismatch, crash
J_ks= J_re= run
notrun kubescape && notrun retire && ok "empty output: not run" || bad "empty"
J_ks=$' \n' J_re=$' \n' run
notrun kubescape && notrun retire && ok "whitespace-only output: not run" || bad "whitespace"
J_ks='{"x":1}' J_re='{"x":1}' run
notrun kubescape && notrun retire && ok "wrong-shape JSON: not run" || bad "wrong shape"
J_re='{"data":[],"errors":["boom"]}' run
notrun retire && ok "retire: non-empty errors: not run" || bad "re errors"
RE_RC=13 J_re='{"data":[],"errors":[]}' run
notrun retire && ok "retire: exit 13 with no row: not run" || bad "re exit13 empty"
RE_RC=0 J_re='{"data":[],"errors":[]}' run
ran retire && ! grep -q 'not run: retire' "$T/err" && ok "retire: exit 0 and no vulnerable library: clean, ran" || bad "re clean"
HUB_MODE=crash run
notrun kubescape && notrun retire && ok "crash: not run" || bad "crash"
# kubescape path mapping: relative to the scan root, absolute under the repo, "-" and an unrelated path
J_ks=${KS//@F@/d.yaml} run
row kubescape k8s/d.yaml C-0017 && ok "kubescape: a path relative to the scan root maps back to the scanned file" || bad "ks rel root"
J_ks=${KS//@F@/$(pwd -P)/@F@} run
row kubescape k8s/d.yaml C-0017 && ok "kubescape: an absolute path under the repo maps back" || bad "ks abs"
J_ks=${KS//\"relativePath\":\"@F@\"/\"x\":1} run
notrun kubescape && ok "kubescape: a resource with no source path ('-'): not run" || bad "ks dash"
J_ks=${KS//@F@/elsewhere.yaml} run
notrun kubescape && ok "kubescape: a path that does not map to the scanned file: not run" || bad "ks unmapped"
# retire: string-form CVE, rows only in unchanged files, unattributable paths
RE_RC=13 J_re='{"data":[{"file":"lib/v.min.js","results":[{"component":"c","version":"1","vulnerabilities":[{"severity":"high","identifiers":{"CVE":"CVE-2099-0002","summary":"s"}}]}]}],"errors":[]}' run
row retire lib/v.min.js CVE-2099-0002 && ok "retire: a bare-string CVE is the rule" || bad "re string cve"
RE_RC=13 J_re='{"data":[{"file":"lib/other.js","results":[{"component":"c","version":"1","vulnerabilities":[{"severity":"high","identifiers":{"summary":"s"}}]}]}],"errors":[]}' run
ran retire && ! row retire lib/other.js retire-js && ok "retire: exit 13 with rows only in unchanged files: ran, no row kept" || bad "re unchanged only"
for bp in "$(pwd -P)/lib/v.min.js" "-" "../lib/v.min.js"; do
  RE_RC=13 J_re='{"data":[{"file":"'$bp'","results":[{"component":"c","version":"1","vulnerabilities":[{"severity":"high","identifiers":{"summary":"s"}}]}]}],"errors":[]}' run
  notrun retire && ok "retire: row path '$bp' is absolute, - or outside the repo: not run" || bad "re path $bp"
done
# gates
rm "$T/art/nsa.json"; rm "$REVIEW_RETIRE_JSREPO"; run
grep -q 'NOT CHECKED: kubescape (no local nsa.json' "$T/err" && grep -q 'NOT CHECKED: retire (REVIEW_RETIRE_JSREPO names no local jsrepository.json' "$T/err" && ! ran kubescape && ! ran retire && ok "no local artifacts or jsrepo: NOT CHECKED, never fetched" || bad "no local data: $(grep -iE "kubescape|retire" "$T/err")"
mkdir -p "$T/art"; : >"$T/art/nsa.json"; : >"$REVIEW_RETIRE_JSREPO"; rm "$T/bin/kubescape" "$T/bin/retire"; run
grep -q 'NOT CHECKED: kubescape (install: brew install kubescape)' "$T/err" && grep -q 'NOT CHECKED: retire (install: npm install -g retire)' "$T/err" && jq -e 'any(.[]; .tool=="kubescape" and .rule=="not-checked")' "$T/out" >/dev/null && ok "missing tools: NOT CHECKED with install hint" || bad "missing tools"
cp "$T/keep/kubescape" "$T/keep/retire" "$T/bin/"
# Helm template change: named, never routed; no .js change: retire not routed
git reset -q --hard base; printf 'apiVersion: v1\nkind: Pod\n' >chart/templates/p.yaml; printf 'x\n' >b.txt; G add . && G commit -q -m helm; : >"$HUB_LOG"; run
grep -q 'NOT CHECKED: kubescape (Helm chart templates are not rendered' "$T/err" && ! grep -q 'kubescape scan' "$HUB_LOG" && ! grep -q 'retire' "$HUB_LOG" && ok "Helm template: NOT CHECKED, not scanned; no .js change: retire not routed" || bad "helm"
[ "$fail" = 0 ]
