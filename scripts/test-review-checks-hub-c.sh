#!/usr/bin/env bash
# review_checks.sh hub routing for flawfinder, cppcheck (C/C++, XML on stderr) and devskim (SARIF) with stub binaries on a hermetic PATH
# (no real tool, no network): rows keep findings, a missing tool is "NOT CHECKED", and a crash, empty output, wrong shape or a bad exit is "not run", never clean.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubc.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/keep" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
printf 'int main(void){return 0;}\n' >a.c; printf 'int x;\n' >other.c; printf 'class A {}\n' >B.java; G add . && G commit -q -m code
cat >"$T/bin/flawfinder" <<'S'
#!/usr/bin/env bash
echo "flawfinder $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_ff"; exit "${FF_RC:-0}"
S
cat >"$T/bin/cppcheck" <<'S'
#!/usr/bin/env bash
echo "cppcheck $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$X_cpp" >&2; exit "${CPP_RC:-0}"
S
cat >"$T/bin/devskim" <<'S'
#!/usr/bin/env bash
echo "devskim $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_dev"; exit "${DEV_RC:-0}"
S
chmod +x "$T/bin/"*; cp "$T/bin/"* "$T/keep/"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
sarif() { printf '{"version":"2.1.0","runs":[{"tool":{"driver":{"name":"x"}},"results":[%s]}]}' "$1"; }
res() { printf '{"ruleId":"%s","message":{"text":"m"},"locations":[{"physicalLocation":{"artifactLocation":{"uri":"%s"},"region":{"startLine":%s}}}]}' "$1" "$2" "$3"; }
FF=$(sarif "$(res FF.strcpy a.c 3),$(res FF.gets other.c 1)")
DEV=$(sarif "$(res DS.weak-hash a.c 2)")
XH='<?xml version="1.0" encoding="UTF-8"?><results version="2"><cppcheck version="2.x"/><errors>'
CPP="$XH"'<error id="nullPointer" severity="error" msg="Null pointer" verbose="v"><location file="a.c" line="4" column="1"/></error><error id="missingInclude" severity="information" msg="n" verbose="v"/><error id="unusedVariable" severity="style" msg="u" verbose="v"><location file="other.c" line="2"/></error></errors></results>'
CPPE="$XH</errors></results>"
export J_ff=$'[INFO]\n'"$FF" X_cpp=$CPP J_dev=$'log line\n'"$DEV"
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
: >"$HUB_LOG"; run
row flawfinder a.c FF.strcpy && row flawfinder other.c FF.gets && ok "flawfinder: SARIF rows, leading log line skipped" || bad "ff rows: $(jq -c '[.[]|select(.tool=="flawfinder")|.rule]' "$T/out")"
row cppcheck a.c nullPointer && row cppcheck other.c unusedVariable && ! row cppcheck "" missingInclude && ok "cppcheck: XML rows from stderr, information note dropped" || bad "cpp rows: $(jq -c '[.[]|select(.tool=="cppcheck")|.rule]' "$T/out")"
row devskim a.c DS.weak-hash && grep -q 'devskim analyze --source-code ./B.java' "$HUB_LOG" && grep -q 'devskim analyze --source-code ./a.c --file-format sarif' "$HUB_LOG" && ok "devskim: one file per run, SARIF row" || bad "dev rows"
grep -q 'cppcheck --xml --quiet ' "$HUB_LOG" && grep -q 'flawfinder --sarif --quiet ' "$HUB_LOG" && ok "flags as documented, no network flag needed" || bad "flags"
# never clean: empty, wrong shape, bad exit, crash
J_ff= X_cpp= J_dev= run
notrun flawfinder && notrun cppcheck && notrun devskim && ok "empty output: not run" || bad "empty"
J_ff='{"x":1}' X_cpp='<results version="2"></results>' J_dev='{"runs":[]}' run
notrun flawfinder && notrun cppcheck && notrun devskim && ok "wrong shape: not run" || bad "wrong shape"
X_cpp="$XH"'<error id="e" severity="error" msg="m"/></errors></results>' run
notrun cppcheck && ok "cppcheck finding without location: not run" || bad "cpp no location"
FF_RC=2 CPP_RC=2 DEV_RC=2 run
notrun flawfinder && notrun cppcheck && notrun devskim && ok "non-zero exit: not run" || bad "exit"
J_ff=$FF X_cpp=$CPPE run
ran cppcheck && ! row cppcheck a.c nullPointer && ok "cppcheck clean XML: ran, no rows" || bad "cpp clean"
HUB_MODE=crash run
notrun flawfinder && notrun cppcheck && notrun devskim && ok "crash: not run" || bad "crash"
rm "$T/bin/"*; run
for t in flawfinder cppcheck devskim; do
  grep -q "NOT CHECKED: $t (install: " "$T/err" && jq -e --arg t $t 'any(.[]; .tool==$t and .rule=="not-checked")' "$T/out" >/dev/null && ok "$t missing: NOT CHECKED with install hint" || bad "$t missing"
done
exit $fail
