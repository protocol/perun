#!/usr/bin/env bash
# review_checks.sh hub routing for skillspector (SKILL.md files) with a stub binary on a hermetic PATH (no real tool, no network):
# canned SARIF is read from the -o file, a missing tool is "NOT CHECKED", and a crash, empty output, wrong shape or a non-zero exit
# with no row is "not run", never clean.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubss.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/home" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
mkdir -p skills/acme; printf '# Acme skill\n' >skills/acme/SKILL.md; printf 'a\n' >notes.txt
G add . && G commit -q -m skill
# stub: logs argv, writes the canned report to the -o file (as the real CLI does), exits SS_RC (1 = risk score over 50)
cat >"$T/bin/skillspector" <<'S'
#!/usr/bin/env bash
echo "skillspector $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
while [ $# -gt 0 ]; do [ "$1" != -o ] || o=$2; shift; done
printf '%s' "$J_ss" >"$o"
exit "${SS_RC:-1}"
S
chmod +x "$T/bin/skillspector"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
sarif() { printf '{"version":"2.1.0","runs":[{"results":[%s]}]}' "$1"; }
res() { printf '{"ruleId":"%s","message":{"text":"m"},"locations":[{"physicalLocation":{"artifactLocation":{"uri":"%s"},"region":{"startLine":%s}}}]}' "$1" "$2" "$3"; }
export J_ss="$(sarif "$(res prompt-injection skills/acme/SKILL.md 3)")"
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
: >"$HUB_LOG"; run
row skillspector skills/acme/SKILL.md prompt-injection && ran skillspector && ok "exit 1 with a row: row kept, ran" || bad "rows: $(jq -c '[.[]|select(.tool=="skillspector")]' "$T/out")"
grep -q 'skillspector scan ./skills/acme/SKILL.md --no-llm -f sarif -o ' "$HUB_LOG" && ! grep -q notes.txt "$HUB_LOG" && ok "argv: offline --no-llm, sarif, one SKILL.md" || bad "argv: $(grep '^skillspector' "$HUB_LOG")"
SS_RC=0 J_ss="$(sarif "")" run
ran skillspector && ! notrun skillspector && ok "exit 0 with an empty results list: ran clean" || bad "clean"
J_ss= run
notrun skillspector && ok "empty output: not run" || bad "empty"
J_ss='{"x":1}' run
notrun skillspector && ok "wrong-shape JSON: not run" || bad "wrong shape"
HUB_MODE=crash run
notrun skillspector && ok "crash: not run" || bad "crash"
SS_RC=1 J_ss="$(sarif "")" run
notrun skillspector && ok "exit 1 (score over 50) with no row: not run, never clean" || bad "rc-with-no-row"
SS_RC=2 J_ss="$(sarif "")" run
notrun skillspector && ok "exit 2 (error): not run" || bad "exit 2"
rm "$T/bin/skillspector"; run
grep -q 'NOT CHECKED: skillspector (install: uv tool install git+https://github.com/NVIDIA/skillspector.git)' "$T/err" && jq -e 'any(.[]; .tool=="skillspector" and .rule=="not-checked")' "$T/out" >/dev/null && ok "missing tool: NOT CHECKED row" || bad "missing: $(grep -i skillspector "$T/err")"
[ "$fail" = 0 ]
