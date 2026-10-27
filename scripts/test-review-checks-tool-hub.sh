#!/usr/bin/env bash
# review_checks.sh tool hub: per routed tool (zizmor bandit gosec grype checkov hadolint) a shim covers
# found+finding, found+clean, missing -> "NOT CHECKED: <tool> (install: ...)", wrong-shape JSON -> not run (never clean).
# snyk-agent-scan is unverified: always NOT CHECKED. Also: every registry tool is documented in references/tool-hub.md.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hub.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
TOOLS="zizmor bandit gosec grype checkov hadolint"
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log"
mkdir -p "$T/repo" "$T/s-none" && cd "$T/repo"
gjson() { # gjson found|clean TOOL: the JSON a real run of TOOL would print
  case "$1:$2" in
    found:zizmor) echo '[{"ident":"template-injection","desc":"d","locations":[{"symbolic":{"key":{"Local":{"verbatim_path":".github/workflows/ci.yml"}}},"concrete":{"location":{"start_point":{"row":4}}}}]}]' ;;
    found:bandit) echo '{"results":[{"filename":"./app.py","line_number":2,"test_id":"B602","issue_text":"t"}]}' ;;
    found:gosec) echo '{"Issues":[{"file":"'"$(pwd -P)"'/main.go","line":"3","rule_id":"G101","details":"d"}]}' ;;
    found:grype) echo '{"matches":[{"vulnerability":{"id":"CVE-1","description":"d"},"artifact":{"name":"p","version":"1"}}]}' ;;
    found:checkov) echo '{"check_type":"dockerfile","results":{"failed_checks":[{"check_id":"CKV_DOCKER_2","check_name":"n","file_line_range":[1,1]}]}}' ;;
    found:hadolint) echo '[{"file":"Dockerfile","line":1,"code":"DL3006","message":"m","level":"warning"}]' ;;
    clean:bandit) echo '{"results":[]}' ;;
    clean:gosec) echo '{"Issues":[]}' ;;
    clean:grype) echo '{"matches":[]}' ;;
    clean:checkov) echo '{"check_type":"dockerfile","results":{"failed_checks":[]}}' ;;
    clean:*) echo '[]' ;;
  esac
}
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
G commit -q --allow-empty -m base && git branch base
mkdir -p .github/workflows; echo 'on: push' >.github/workflows/ci.yml
echo 'x = 1' >app.py; printf 'package main\n' >main.go; echo 'module example.com/m' >go.mod
echo 'FROM alpine' >Dockerfile; echo '{}' >sbom.json; echo '{}' >.mcp.json; echo '{}' >package-lock.json
G add . && G commit -q -m f
# shim: prints $HUB_JSON (gosec: into the -out file); HUB_MODE=crash exits 9; HUB_RC sets the exit code.
for t in $TOOLS; do
  mkdir -p "$T/s-$t"; cat >"$T/s-$t/$t" <<'S'
#!/usr/bin/env bash
echo "${0##*/} GOPROXY=${GOPROXY:-} $*" >>"${HUB_LOG:-/dev/null}"
[ "${HUB_MODE:-}" != crash ] || exit 9
o=; while [ $# -gt 0 ]; do [ "$1" != -out ] || o=$2; shift; done
if [ -n "$o" ]; then printf '%s' "$HUB_JSON" >"$o"; else printf '%s\n' "$HUB_JSON"; fi
[ -z "${HUB_RC:-}" ] || exit "$HUB_RC"
S
  chmod +x "$T/s-$t/$t"
done
# Inert stubs for the older scanners keep the run offline and fast; real ones may sit on PATH.
mkdir -p "$T/base"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
nck() { jq -e --arg t "$1" 'any(.[]; .tool==$t and .rule=="not-checked" and .file=="")' "$T/out" >/dev/null && ok "$1 $2: not-checked row in JSON" || bad "$1 $2: not-checked row in JSON"; }
run() { PATH="$T/s-$1:$T/base:$PATH" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
for t in $TOOLS; do
  rc=0; [ "$t" != zizmor ] || rc=11
  HUB_JSON=$(gjson found $t) HUB_RC=$rc run "$t"
  jq -e --arg t "$t" 'any(.[]; .tool==$t and .rule!="" and .file!="")' "$T/out" >/dev/null && ok "$t finding" || bad "$t finding"
  ! grep -q "NOT CHECKED: $t" "$T/err" && ok "$t found: no NOT CHECKED" || bad "$t found but NOT CHECKED"
  HUB_JSON=$(gjson clean $t) run "$t"
  jq -e --arg t "$t" 'any(.[]; .tool==$t)|not' "$T/out" >/dev/null && ok "$t clean" || bad "$t clean"
  HUB_JSON='{"unexpected":1}' run "$t"
  jq -e --arg t "$t" 'any(.[]; .tool==$t and .rule!="not-checked")|not' "$T/out" >/dev/null && grep -q "not run: $t (unparseable" "$T/err" && ok "$t bad JSON fails" || bad "$t bad JSON fails"
  nck "$t" "bad JSON"
  grep -q "analyzers ran:.* $t\b" "$T/err" && bad "$t bad JSON listed as ran" || ok "$t bad JSON not listed as ran"
  HUB_MODE=crash HUB_JSON= run "$t"
  grep -q "not run: $t (exit 9)" "$T/err" && ok "$t crash is not clean" || bad "$t crash is not clean"
  nck "$t" crash
  grep -qE "analyzers ran:.*\b$t\b" "$T/err" && bad "$t crash listed as ran" || ok "$t crash not listed as ran"
  PATH="$T/s-none:$T/base:$PATH" bash "$RC" --base base 2>"$T/err" >"$T/out"
  grep -qE "^NOT CHECKED: $t \(install: .+\)" "$T/err" && ok "$t missing -> NOT CHECKED" || bad "$t missing -> NOT CHECKED"
  nck "$t" missing
  HUB_JSON=$(gjson clean $t) run "$t"; grep -qE "analyzers ran:.*\b$t\b" "$T/err" && ok "$t clean listed as ran" || bad "$t clean listed as ran"
done
# bandit: issue_text (B105 embeds the secret) must never reach the output
HUB_JSON='{"results":[{"filename":"./app.py","line_number":2,"test_id":"B105","issue_text":"Possible hardcoded credential: canary-7f3a"}]}' run bandit
jq -e 'any(.[]; .rule=="B105")' "$T/out" >/dev/null && ! grep -q canary-7f3a "$T/out" "$T/err" && ok "bandit issue_text not read" || bad "bandit issue_text not read"
# gosec: load errors with -no-fail leave Issues empty/null; must be not-checked. GOPROXY=off always.
for g in '{"Issues":null,"Golang errors":{"main.go":[{"line":1,"column":1,"error":"x"}]}}' '{"Issues":[],"Golang errors":{"p":[{"error":"x"}]}}'; do
  HUB_JSON=$g run gosec
  jq -e 'any(.[]; .tool=="gosec" and .rule!="not-checked")|not' "$T/out" >/dev/null && grep -q "not run: gosec (unparseable" "$T/err" && nck gosec "Golang errors" || bad "gosec Golang errors"
done
HUB_JSON='{"Issues":null}' run gosec; grep -q "not run: gosec" "$T/err" && bad "gosec Issues:null w/o errors is clean" || ok "gosec Issues:null w/o errors is clean"
: >"$HUB_LOG"; HUB_JSON=$(gjson clean gosec) run gosec; grep -q 'gosec GOPROXY=off ' "$HUB_LOG" && ok "gosec runs with GOPROXY=off" || bad "gosec GOPROXY=off"
# checkov: parsing_errors means the file was not checked
HUB_JSON='{"check_type":"dockerfile","results":{"failed_checks":[],"parsing_errors":["/Dockerfile"]}}' run checkov
grep -q "not run: checkov (unparseable" "$T/err" && nck checkov "parsing_errors" || bad "checkov parsing_errors"
# grype: SBOM only, findings credited to the scanned SBOM; a lockfile alone is never scanned (dir: covers the whole tree)
: >"$HUB_LOG"; HUB_JSON=$(gjson found grype) run grype
jq -e 'any(.[]; .tool=="grype" and .file=="sbom.json")' "$T/out" >/dev/null && ! grep -q 'package-lock' "$T/out" && grep -q 'sbom:./sbom.json' "$HUB_LOG" && ! grep -q 'dir:' "$HUB_LOG" && ok "grype credits sbom.json only" || bad "grype credits sbom.json only"
# docs: gosec network caveat and unverified skill license
H=$ROOT/.claude/skills/deep-code-review/references/tool-hub.md
grep -q 'GOPROXY=off' "$H" && grep -q 'CC-BY-SA.*unverified' "$H" && ok "tool-hub.md caveats" || bad "tool-hub.md caveats"
grep -q '^NOT CHECKED: snyk-agent-scan (unverified' "$T/err" && ok "agent-scan unverified, skipped" || bad "agent-scan unverified"
for t in $TOOLS snyk-agent-scan; do grep -q "\`$t\`" "$ROOT/.claude/skills/deep-code-review/references/tool-hub.md" && ok "$t documented" || bad "$t documented"; done
exit $fail
