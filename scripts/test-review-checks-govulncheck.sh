#!/usr/bin/env bash
# review_checks.sh govulncheck routing, with stub binaries on a hermetic PATH (no real govulncheck, go or network):
# a called vulnerability becomes one row on go.mod (an imported-only one and a repeated one do not), a clean run is listed as ran,
# a missing govulncheck or Go toolchain is "NOT CHECKED", output without a config message, a stray line in the stream and a crash
# are "not run" (never clean), the run is offline-locked (GOPROXY=off GOTOOLCHAIN=local), and only a changed root go.mod routes it.
# REVIEW_CHECKS=<path> runs another copy of the script (used to prove the cases fail before the change).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/govuln.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN=
mkdir -p "$T/repo" "$T/bin" "$T/go" "$T/base" "$T/sys" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
G commit -q --allow-empty -m base && git branch base
printf 'package main\n' >main.go; echo 'module example.com/m' >go.mod; echo 'x' >go.sum
G add . && G commit -q -m go
cat >"$T/bin/govulncheck" <<'S'
#!/usr/bin/env bash
echo "govulncheck GOPROXY=${GOPROXY:-} GOTOOLCHAIN=${GOTOOLCHAIN:-} $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s\n' "$GV_JSON"
S
printf '#!/bin/sh\nexit 0\n' >"$T/go/go"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/bin/govulncheck" "$T/go/go" "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b" # only the system binaries review_checks.sh needs, never the host PATH
done
CFG='{"config":{"protocol_version":"v1.0.0","scanner_name":"govulncheck"}}'
PROG='{"progress":{"message":"Scanning your code"}}'
OSVM='{"osv":{"id":"GO-2021-0001"}}'
CALLED='{"finding":{"osv":"GO-2021-0001","fixed_version":"v1.2.3","trace":[{"module":"example.org/dep","version":"v1.0.0","package":"example.org/dep/pkg","function":"Parse","position":{"filename":"/dep/pkg/p.go","line":3}},{"module":"example.com/m","package":"example.com/m","function":"main","position":{"filename":"'"$(pwd -P)"'/main.go","line":7}}]}}'
IMPORTED='{"finding":{"osv":"GO-2021-0002","trace":[{"module":"example.org/other","version":"v0.1.0","package":"example.org/other"}]}}'
GV_JSON=$(printf '%s\n' "$CFG" "$PROG" "$OSVM" "$IMPORTED" "$CALLED" "$CALLED")
run() { local p=$1; shift; PATH="$p:$T/base:$T/sys" bash "$RC" --base "${BASE:-base}" 2>"$T/err" >"$T/out"; }
GP="$T/bin:$T/go"
export GV_JSON
run "$GP"
n=$(jq '[.[] | select(.tool=="govulncheck")] | length' "$T/out")
[ "$n" = 1 ] && jq -e 'any(.[]; .tool=="govulncheck" and .file=="go.mod" and .rule=="GO-2021-0001" and (.message|test("example.org/dep@v1.0.0 example.org/dep/pkg.Parse is called from main.go:7; fixed in v1.2.3")))' "$T/out" >/dev/null && ok "called vulnerability: one row on go.mod with the call site (imported-only and repeat dropped)" || bad "called vulnerability row (rows: $n)"
grep -q 'govulncheck GOPROXY=off GOTOOLCHAIN=local -format json ./...' "$HUB_LOG" && ok "runs offline-locked with -format json ./..." || bad "args/env"
! grep -q "NOT CHECKED: govulncheck" "$T/err" && ok "found: no NOT CHECKED" || bad "found but NOT CHECKED"
GV_JSON=$(printf '%s\n' "$CFG" "$PROG" "$IMPORTED") run "$GP"
jq -e 'any(.[]; .tool=="govulncheck")|not' "$T/out" >/dev/null && grep -qE "analyzers ran:.*\bgovulncheck\b" "$T/err" && ok "imported-only is clean and listed as ran" || bad "imported-only clean"
nck() { jq -e 'any(.[]; .tool=="govulncheck" and .rule=="not-checked" and .file=="")' "$T/out" >/dev/null && ok "$1: not-checked row" || bad "$1: not-checked row"; }
run "$T/go"
grep -qE '^NOT CHECKED: govulncheck \(install: .+\)' "$T/err" && nck "missing tool" || bad "missing tool -> NOT CHECKED"
run "$T/bin"
grep -q '^NOT CHECKED: govulncheck (go toolchain missing)' "$T/err" && nck "missing go" || bad "missing go -> NOT CHECKED"
GV_JSON='{"progress":{"message":"x"}}' run "$GP"
grep -q 'not run: govulncheck (unparseable' "$T/err" && nck "no config message" || bad "no config message is not clean"
GV_JSON=$(printf '%s\nstray log line\n%s\n' "$CFG" "$CALLED") run "$GP"
grep -q 'not run: govulncheck (unparseable' "$T/err" && jq -e 'any(.[]; .tool=="govulncheck" and .rule!="not-checked")|not' "$T/out" >/dev/null && ok "stray line in the stream fails closed" || bad "stray line fails closed"
HUB_MODE=crash GV_JSON= run "$GP"
grep -q 'not run: govulncheck (exit 9)' "$T/err" && nck crash && ! grep -qE "analyzers ran:.*\bgovulncheck\b" "$T/err" && ok "crash is not clean and not listed as ran" || bad "crash"
# only a changed root go.mod routes it: a .go or go.sum edit alone does not
: >"$HUB_LOG"; echo 'package main // edit' >main.go; echo y >go.sum; G add . && G commit -q -m edit && git branch mid
BASE=mid run "$GP"; [ ! -s "$HUB_LOG" ] && ok "no go.mod change: govulncheck not run" || bad "routed without a go.mod change"
H=$ROOT/.claude/skills/deep-code-review/references/tool-hub.md
grep -q '^| `govulncheck` |' "$H" && ok "documented in tool-hub.md" || bad "documented in tool-hub.md"
exit $fail
