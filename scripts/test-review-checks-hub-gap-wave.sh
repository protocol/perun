#!/usr/bin/env bash
# review_checks.sh hub routing for kube-score (Kubernetes manifests) and tflint (Terraform, one file at a time) with stub binaries on a hermetic PATH
# (no real tool, no network): findings land as rows, a missing tool is "NOT CHECKED", a crash, empty output, a tflint errors list or wrong-shape JSON is
# "not run" (never clean).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubgap.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
mkdir -p sub templates; printf 'apiVersion: apps/v1\nkind: Deployment\n' >deploy.yaml; printf 'name: ci\non: push\n' >plain.yaml
printf 'apiVersion: v1\nkind: Service\n' >templates/svc.yaml; printf 'resource "x" "y" {}\n' >main.tf; printf 'resource "x" "z" {}\n' >sub/b.tf
G add . && G commit -q -m files
cat >"$T/stub" <<'S'
#!/usr/bin/env bash
n=${0##*/}; v=J_${n//-/_}
echo "$n $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
o=${!v}
if [ "$n" = tflint ]; then # real tflint reports range.filename as chdir joined with the filter (cmd/inspect.go: filterFiles = Join(Chdir, file)), so derive it from the args
  for a in "$@"; do case $a in --chdir=*) cd_=${a#--chdir=} ;; --filter=*) fl=${a#--filter=} ;; esac; done
  cd_=${cd_#./}; [ "$cd_" != . ] || cd_=; o=${o//@F@/${cd_:+$cd_/}$fl}
fi
printf '%s\n' "$o"
[ "$n" != kube-score ] || exit "${KS_RC:-1}"
exit "${TF_RC:-2}"
S
cp "$T/stub" "$T/bin/kube-score"; cp "$T/stub" "$T/bin/tflint"; chmod +x "$T/bin/kube-score" "$T/bin/tflint"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
export J_kube_score='[{"object_name":"v1/Deployment/web","type_meta":{},"object_meta":{},"file_name":"./deploy.yaml","file_row":1,"checks":[{"check":{"name":"Container Image Tag","id":"container-image-tag"},"grade":1,"skipped":false,"comments":[{"path":"web","summary":"Image with latest tag","description":"SECRETDESC"}]},{"check":{"name":"Pod Probes","id":"pod-probes"},"grade":5,"skipped":false,"comments":[]},{"check":{"name":"Stable API","id":"stable-api"},"grade":10,"skipped":false,"comments":[]},{"check":{"name":"Skipped","id":"skipped-check"},"grade":1,"skipped":true,"comments":[]}]}]'
export J_tflint='{"issues":[{"rule":{"name":"terraform_unused_declarations","severity":"warning","link":"x"},"message":"variable v is declared but not used","range":{"filename":"@F@","start":{"line":3,"column":1},"end":{"line":3,"column":9}},"callers":[],"fixable":false,"fixed":false}],"errors":[]}'
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
nck() { jq -e --arg t "$1" 'any(.[]; .tool==$t and .rule=="not-checked" and .file=="")' "$T/out" >/dev/null; }
: >"$HUB_LOG"; run
row kube-score deploy.yaml container-image-tag && ok "kube-score: critical row on deploy.yaml" || bad "kube-score critical row"
row kube-score deploy.yaml pod-probes && ok "kube-score: warning grade with no comment still gets a row" || bad "kube-score warning row"
jq -e 'any(.[]; .rule=="stable-api" or .rule=="skipped-check")|not' "$T/out" >/dev/null && ok "kube-score: OK grade and skipped check dropped" || bad "kube-score noise"
! grep -q SECRETDESC "$T/out" && ok "kube-score: description never read" || bad "kube-score description leak"
grep -qx 'kube-score score -o json ./deploy.yaml' "$HUB_LOG" && ok "kube-score: k8s manifest only (no plain yaml, no Helm template)" || bad "kube-score args: $(grep ^kube-score "$HUB_LOG")"
grep -qx 'tflint --format=json --no-color --call-module-type=none --chdir=. --filter=main.tf' "$HUB_LOG" && grep -qx 'tflint --format=json --no-color --call-module-type=none --chdir=./sub --filter=b.tf' "$HUB_LOG" && ok "tflint: one call per .tf, chdir + filter, no module download" || bad "tflint args: $(grep ^tflint "$HUB_LOG")"
! grep -q 'init' "$HUB_LOG" && ok "tflint: never --init" || bad "tflint init"
row tflint main.tf terraform_unused_declarations && row tflint sub/b.tf terraform_unused_declarations && ok "tflint: row per changed file, a sub/ file keeps its directory" || bad "tflint rows: $(jq -c '[.[]|select(.tool=="tflint")|.file]' "$T/out")"
grep -qE "analyzers ran:.*\bkube-score\b" "$T/err" && grep -qE "analyzers ran:.*\btflint\b" "$T/err" && ok "both listed as ran" || bad "ran list"
# exit codes: kube-score 0 (clean grades) and tflint 0 (no issues) are fine; kube-score 1 or tflint 2 are results (above); tflint 1 is an error
export TF_RC=1; : >"$HUB_LOG"; run
grep -q 'not run: tflint' "$T/err" && ok "tflint exit 1: not run" || bad "tflint exit 1"
export TF_RC=2
# wrong-shape, empty and errors-list outputs are never clean
O_ks=$J_kube_score; O_tf=$J_tflint
export J_kube_score='[]' J_tflint='{"issues":[],"errors":[{"message":"boom"}]}'; run
grep -q 'not run: kube-score' "$T/err" && ok "kube-score: empty list is not run" || bad "kube-score empty"
grep -q 'not run: tflint' "$T/err" && ! grep -qE "analyzers ran:.*\btflint\b" "$T/err" && ok "tflint: errors list is not run, not ran" || bad "tflint errors"
export J_kube_score='null' J_tflint='{"x":1}'; run
grep -q 'not run: kube-score' "$T/err" && grep -q 'not run: tflint' "$T/err" && ok "null / wrong-shape JSON: not run" || bad "wrong shape"
# empty stdout is never clean, whatever the exit code (a tool that died quietly)
for rc in 0 2 1; do KS_RC=$rc TF_RC=$rc J_kube_score= J_tflint= run
  grep -q 'not run: kube-score' "$T/err" && grep -q 'not run: tflint' "$T/err" && ! grep -qE "analyzers ran:.*\b(kube-score|tflint)\b" "$T/err" && ok "empty stdout, exit $rc: not run" || bad "empty stdout exit $rc"; done
export KS_RC=1 TF_RC=2
# a manifest with no checks (CRD or ConfigMap only) marshals checks as null: ran, no row, next object still scored
export J_kube_score='[{"object_name":"c","file_name":"./deploy.yaml","file_row":1,"checks":null},'"${O_ks#[}"; run
grep -qE "analyzers ran:.*\bkube-score\b" "$T/err" && ! grep -q 'not run: kube-score' "$T/err" && row kube-score deploy.yaml container-image-tag && ok "kube-score: checks null accepted, other objects still scored" || bad "checks null"
export J_kube_score='[{"object_name":"c","file_name":"./deploy.yaml","file_row":1,"checks":null}]'; run
grep -qE "analyzers ran:.*\bkube-score\b" "$T/err" && jq -e 'any(.[]; .tool=="kube-score")|not' "$T/out" >/dev/null && ok "kube-score: only checks null is clean, ran" || bad "checks null only"
export J_kube_score=$O_ks J_tflint=$O_tf
HUB_MODE=crash run
grep -q 'not run: kube-score' "$T/err" && grep -q 'not run: tflint' "$T/err" && ! grep -qE "analyzers ran:.*\b(kube-score|tflint)\b" "$T/err" && ok "crash: not run, never clean" || bad "crash"
# clean runs
export J_kube_score='[{"object_name":"o","file_name":"./deploy.yaml","file_row":1,"checks":[{"check":{"name":"n","id":"i"},"grade":10,"skipped":false,"comments":[]}]}]' J_tflint='{"issues":[],"errors":[]}' KS_RC=0 TF_RC=0; run
grep -qE "analyzers ran:.*\bkube-score\b" "$T/err" && grep -qE "analyzers ran:.*\btflint\b" "$T/err" && jq -e 'any(.[]; .tool=="kube-score" or .tool=="tflint")|not' "$T/out" >/dev/null && ok "clean: both ran, zero rows" || bad "clean run"
# missing tools
rm "$T/bin/kube-score" "$T/bin/tflint"; run
nck kube-score && nck tflint && grep -q 'NOT CHECKED: kube-score (install: brew install kube-score)' "$T/err" && grep -q 'NOT CHECKED: tflint (install: brew install tflint)' "$T/err" && ok "missing tools: NOT CHECKED with install hints" || bad "missing tools"
[ "$fail" = 0 ] && echo "PASS" || { echo "FAILED"; exit 1; }
