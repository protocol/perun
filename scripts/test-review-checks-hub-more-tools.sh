#!/usr/bin/env bash
# review_checks.sh hub routing for ruff-security (ruff check --select S), syft, kube-linter and brakeman, with stub binaries on a hermetic PATH
# (no real tool, no network): findings land as rows, syft only counts packages (stderr, SBOM kept in TMPDIR, no row), a missing tool is "NOT CHECKED"
# with a not-checked row, a crash or wrong-shape JSON is "not run" (never clean), kube-linter only sees real Kubernetes manifests, brakeman only runs
# when the root Gemfile names rails, and cargo-audit is deliberately not routed (osv-scanner covers Cargo.lock; see tool-hub.md).
# REVIEW_CHECKS=<path> runs another copy of the script (used to prove the cases fail before the change).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubmore.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
G commit -q --allow-empty -m base && git branch base
mkdir -p app/models; printf 'password = "x"\n' >app.py
printf 'apiVersion: apps/v1\nkind: Deployment\n' >deploy.yaml; printf 'name: ci\non: push\n' >plain.yaml
mkdir -p chart/templates; printf 'apiVersion: apps/v1\nkind: Deployment\n' >chart/templates/d.yaml; printf 'apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n' >kustomization.yaml
printf "source 'https://rubygems.org'\ngem 'rails'\n" >Gemfile; printf 'class U; end\n' >app/models/u.rb
printf '{}\n' >package-lock.json; printf '# lock\n' >Cargo.lock
G add . && G commit -q -m files
for t in ruff syft kube-linter brakeman; do
  cat >"$T/bin/$t" <<'S'
#!/usr/bin/env bash
n=${0##*/}; v=J_${n//-/_}
echo "$n $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
if [ "$n" = syft ]; then for a; do case $a in syft-json=*) printf '%s' "${!v}" >"${a#syft-json=}" ;; esac; done; else printf '%s\n' "${!v}"; fi
[ "$n" != kube-linter ] || exit "${KL_RC:-1}"
S
  chmod +x "$T/bin/$t"
done
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b" # only the system binaries review_checks.sh needs, never the host PATH
done
export J_ruff="[{\"code\":\"S105\",\"message\":\"Possible hardcoded password\",\"filename\":\"$(pwd -P)/app.py\",\"location\":{\"row\":1,\"column\":1}}]"
export J_syft='{"artifacts":[{"name":"a"},{"name":"b"}]}'
export J_kube_linter='{"Reports":[{"Check":"latest-tag","Diagnostic":{"Message":"container uses the latest tag"},"Object":{"Metadata":{"FilePath":"./deploy.yaml"}}}],"Summary":{}}'
export J_brakeman='{"warnings":[{"check_name":"SQL","warning_type":"SQL Injection","message":"Possible SQL injection","file":"app/models/u.rb","line":4,"confidence":"High"}],"errors":[]}'
run() { local p=$1; shift; PATH="$p:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
nck() { jq -e --arg t "$1" 'any(.[]; .tool==$t and .rule=="not-checked" and .file=="")' "$T/out" >/dev/null; }
: >"$HUB_LOG"; run "$T/bin"
row ruff-security app.py S105 && ok "ruff-security: S105 row on app.py" || bad "ruff-security row"
grep -q 'ruff check --select S --output-format json' "$HUB_LOG" && ok "ruff-security: runs --select S as JSON" || bad "ruff args"
row kube-linter deploy.yaml latest-tag && ok "kube-linter: row on the manifest" || bad "kube-linter row"
grep -q 'kube-linter lint --format json ./deploy.yaml$' "$HUB_LOG" && ok "kube-linter: only the manifest, not plain.yaml, a Helm template or kustomization.yaml" || bad "kube-linter args"
row brakeman app/models/u.rb SQL && ok "brakeman: row on the changed file" || bad "brakeman row"
grep -q '^brakeman -q --no-pager -f json' "$HUB_LOG" && ok "brakeman: -q --no-pager -f json" || bad "brakeman args"
sbom=$(sed -nE 's/.*SBOM inventory \(not a vulnerability scan\): syft listed 2 packages in .* \(SBOM: (.*)\)$/\1/p' "$T/err" | head -n1)
[ -n "$sbom" ] && [ -s "$sbom" ] && ok "syft: counts 2 packages, SBOM kept" || bad "syft count or SBOM"
jq -e 'any(.[]; .tool=="syft")|not' "$T/out" >/dev/null && ok "syft: no finding row" || bad "syft row"
grep -q '^syft .* -o syft-json=' "$HUB_LOG" && ok "syft: -o syft-json=FILE" || bad "syft args"
grep -qE "analyzers ran:.*\bkube-linter\b" "$T/err" && ok "kube-linter listed as ran" || bad "kube-linter ran"
# missing tools
run ""
for t in ruff-security syft kube-linter brakeman; do
  grep -qE "^NOT CHECKED: $t \(install: .+\)" "$T/err" && nck "$t" && ok "$t missing: NOT CHECKED + row" || bad "$t missing"
done
# crash and wrong shape fail closed
for t in ruff-security kube-linter brakeman syft; do
  b=$t; [ "$t" != ruff-security ] || b=ruff; mkdir -p "$T/c"; rm -f "$T/c/"*; ln -s "$T/bin/$b" "$T/c/$b"
  HUB_MODE=crash run "$T/c"
  grep -q "not run: $t (exit 9)" "$T/err" && nck "$t" && ok "$t crash: not run, not clean" || bad "$t crash"
done
J_kube_linter='{"x":1}' run "$T/c"; J_brakeman='{"x":1}' run "$T/c"
J_brakeman='{"warnings":[],"errors":[{"error":"parse"}]}' run "$T/bin"
grep -q 'not run: brakeman (unparseable' "$T/err" && ok "brakeman scan errors: not run" || bad "brakeman errors"
J_kube_linter='{"x":1}' run "$T/bin"
grep -q 'not run: kube-linter (unparseable' "$T/err" && ok "kube-linter wrong shape: not run" || bad "kube-linter shape"
J_ruff='{"x":1}' run "$T/bin"
grep -q 'not run: ruff-security (unparseable' "$T/err" && ok "ruff-security wrong shape: not run" || bad "ruff shape"
grep -qE "analyzers ran:.*\bsyft\b" "$T/err" || grep -qE "wired.*syft|not run:.*syft" "$T/err" && bad "syft counted as ran/wired/not run on success" || ok "syft success: an inventory line, never ran/wired"
# kube-linter: only exit 0 and 1 are results; exit 2 is a crash, not a clean run
KL_RC=2 run "$T/bin"
grep -q 'not run: kube-linter (exit 2)' "$T/err" && nck kube-linter && ! row kube-linter deploy.yaml latest-tag && ok "kube-linter exit 2: not run" || bad "kube-linter exit 2"
# syft crash: not run, never listed as ran, and no SBOM left behind
rm -f "$T/tmp"/review_sbom.*
HUB_MODE=crash run "$T/c"
grep -q 'not run: syft (exit 9)' "$T/err" && ! grep -qE "analyzers ran:.*\bsyft\b" "$T/err" && [ -z "$(ls "$T/tmp" | grep review_sbom || true)" ] && ok "syft crash: not ran, SBOM file removed" || bad "syft crash cleanup"
# gating: no k8s manifest, no rails -> neither tool is routed (no NOT CHECKED either)
G rm -q deploy.yaml; printf "source 'https://rubygems.org'\ngem 'sinatra'\n" >Gemfile; G add -A; G commit -q -m nok8s
: >"$HUB_LOG"; run ""
! grep -qE 'NOT CHECKED: (kube-linter|brakeman)' "$T/err" && ok "no manifest / no rails: not routed" || bad "gating"
# cargo-audit: not routed, and the doc says why
! grep -q cargo-audit "$RC" && grep -q 'cargo-audit' "$ROOT/.claude/skills/deep-code-review/references/tool-hub.md" && ok "cargo-audit skipped and explained" || bad "cargo-audit"
H=$ROOT/.claude/skills/deep-code-review/references/tool-hub.md
for t in ruff-security syft kube-linter brakeman; do grep -q "^| \`$t\` |" "$H" && ok "$t documented" || bad "$t documented"; done
exit $fail
