#!/usr/bin/env bash
# review_checks.sh hub routing for staticcheck (Go, whole module, offline) with stub binaries on a hermetic PATH (no real tool, no network):
# diagnostics land as rows on changed files, a missing tool or go toolchain is "NOT CHECKED", and a crash, an exit 1 with no output or
# wrong-shape output is "not run" (never clean). Empty output with exit 0 is the one clean case (staticcheck prints nothing when clean).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubsc.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp"
mkdir -p "$T/repo/pkg" "$T/bin" "$T/base" "$T/sys" "$T/tmp" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
printf 'module example.com/m\n\ngo 1.22\n' >go.mod; printf 'package pkg\n' >pkg/a.go; printf 'package pkg\n' >pkg/b.go
G add . && G commit -q -m files
cat >"$T/bin/staticcheck" <<'S'
#!/usr/bin/env bash
echo "staticcheck $* GOPROXY=${GOPROXY:-}" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_sc"
exit "${SC_RC:-1}"
S
printf '#!/bin/sh\nexit 0\n' >"$T/bin/go"; chmod +x "$T/bin/staticcheck" "$T/bin/go"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
export J_sc='{"code":"SA4006","severity":"warning","location":{"file":"pkg/a.go","line":7,"column":2},"end":{"file":"pkg/a.go","line":7,"column":3},"message":"this value of err is never used"}
{"code":"U1000","location":{"file":"'"$(cd "$T/repo" && pwd -P)"'/pkg/b.go","line":3,"column":6},"end":{"file":"x","line":3,"column":9},"message":"func f is unused"}
{"code":"S1000","severity":"warning","location":{"file":"other/c.go","line":1,"column":1},"end":{"file":"other/c.go","line":1,"column":2},"message":"not a changed file"}'
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg f "$1" --arg r "$2" 'any(.[]; .tool=="staticcheck" and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\bstaticcheck\b" "$T/err"; }
: >"$HUB_LOG"; run
row pkg/a.go SA4006 && row pkg/b.go U1000 && ok "findings: rows on changed files, absolute path made relative, absent severity defaults" || bad "rows: $(jq -c '[.[]|select(.tool=="staticcheck")|.file]' "$T/out")"
jq -e 'any(.[]; .tool=="staticcheck" and .file=="other/c.go")|not' "$T/out" >/dev/null && ok "row for an unchanged file dropped" || bad "unchanged row"
grep -qx 'staticcheck -f json ./... GOPROXY=off' "$HUB_LOG" && [ "$(grep -c ^staticcheck "$HUB_LOG")" = 1 ] && ok "one whole-module call, offline (GOPROXY=off)" || bad "args: $(cat "$HUB_LOG")"
ran && ok "exit 1 with diagnostics: ran" || bad "ran list"
# clean: exit 0, nothing printed
SC_RC=0 J_sc= run
ran && ! grep -q 'not run: staticcheck' "$T/err" && jq -e 'any(.[]; .tool=="staticcheck")|not' "$T/out" >/dev/null && ok "exit 0 with empty output: clean, ran" || bad "clean"
# never clean: exit 1 with no output (setup failure), whitespace, wrong shape, a crash
SC_RC=1 J_sc= run
grep -q 'not run: staticcheck' "$T/err" && ! ran && ok "exit 1 with empty output: not run" || bad "exit 1 empty"
SC_RC=2 J_sc= run
grep -q 'not run: staticcheck' "$T/err" && ! ran && ok "exit 2 (usage error): not run" || bad "exit 2"
SC_RC=1 J_sc='{"x":1}' run
grep -q 'not run: staticcheck' "$T/err" && ! ran && ok "wrong-shape JSON: not run" || bad "wrong shape"
SC_RC=1 J_sc='some text' run
grep -q 'not run: staticcheck' "$T/err" && ! ran && ok "plain text: not run" || bad "text"
HUB_MODE=crash run
grep -q 'not run: staticcheck' "$T/err" && ! ran && ok "crash: not run" || bad "crash"
# gates: no go.mod, no go toolchain, no tool
git rm -q go.mod && G commit -q -m nomod; run
grep -q 'NOT CHECKED: staticcheck (no go.mod at repo root)' "$T/err" && ok "no go.mod: NOT CHECKED" || bad "go.mod gate"
git checkout -q HEAD~1 -- go.mod && G commit -q -m mod; rm "$T/bin/go"; run
grep -q 'NOT CHECKED: staticcheck (go toolchain missing)' "$T/err" && ok "no go: NOT CHECKED" || bad "go gate"
rm "$T/bin/staticcheck"; printf '#!/bin/sh\nexit 0\n' >"$T/bin/go"; chmod +x "$T/bin/go"; run
jq -e 'any(.[]; .tool=="staticcheck" and .rule=="not-checked")' "$T/out" >/dev/null && grep -q 'NOT CHECKED: staticcheck (install: brew install staticcheck)' "$T/err" && ok "missing tool: NOT CHECKED with install hint" || bad "missing tool"
[ "$fail" = 0 ] && echo "PASS" || { echo "FAILED"; exit 1; }
