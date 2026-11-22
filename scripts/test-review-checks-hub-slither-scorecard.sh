#!/usr/bin/env bash
# review_checks.sh hub routing for slither (Solidity) and the scorecard NOT CHECKED row, with stub binaries on a hermetic PATH
# (no real tool, no network): slither rows are kept, a missing slither is "NOT CHECKED", a crash, a missing or wrong-shape SARIF file
# and a non-zero exit with no row are "not run", never clean; a committed slither.config.json is never loaded (the stub applies slither's
# own lookup: no --config-file means ./slither.config.json); scorecard is never executed, only named under --full or --hygiene.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubslsc.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_PWNED="$T/pwned" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/home" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
mkdir -p contracts .github/workflows
printf 'pragma solidity ^0.8.0;\n' >contracts/T.sol; printf 'a\n' >notes.txt; printf 'name: ci\n' >.github/workflows/ci.yml
G add . && G commit -q -m code
# slither stub: writes $J_sl to the file named after --sarif
cat >"$T/bin/slither" <<'S'
#!/usr/bin/env bash
echo "slither $*" >>"$HUB_LOG"
cfg=; a=("$@"); for ((i = 0; i < ${#a[@]}; i++)); do [ "${a[i]}" != --config-file ] || cfg=${a[i+1]}; done
[ -n "$cfg" ] || { [ -f slither.config.json ] && cfg=slither.config.json; } || true
[ -z "$cfg" ] || ! grep -q compile_custom_build "$cfg" || touch "$HUB_PWNED"
[ "${HUB_MODE:-}" != crash ] || exit 255
while [ $# -gt 0 ]; do [ "$1" != --sarif ] || { f=$2; break; }; shift; done
[ "${NO_FILE:-}" = 1 ] || printf '%s' "$J_sl" >"$f"
exit "${SL_RC:-0}"
S
cat >"$T/bin/scorecard" <<'S'
#!/usr/bin/env bash
echo "scorecard $*" >>"$HUB_LOG"
exit 0
S
printf '#!/bin/sh\nexit 0\n' >"$T/bin/solc"; chmod +x "$T/bin/slither" "$T/bin/scorecard" "$T/bin/solc"; mkdir "$T/keep"; cp "$T/bin/slither" "$T/keep/"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep seq; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
sarif() { printf '{"version":"2.1.0","runs":[{"results":[%s]}]}' "$1"; }
res() { printf '{"ruleId":"%s","message":{"text":"m"},"locations":[{"physicalLocation":{"artifactLocation":{"uri":"%s"},"region":{"startLine":%s}}}]}' "$1" "$2" "$3"; }
export J_sl="$(sarif "$(res reentrancy-eth "$(pwd -P)/contracts/T.sol" 4)")"
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base "$@" 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
: >"$HUB_LOG"; SL_RC=255 run
row slither contracts/T.sol reentrancy-eth && ran slither && ok "slither: exit 255 with a row: row kept, ran" || bad "slither rows: $(jq -c '[.[]|select(.tool=="slither")]' "$T/out")"
grep -q -- 'slither /[^ ]*/contracts/T.sol --sarif .* --compile-force-framework solc' "$HUB_LOG" && ! grep -q 'notes.txt' "$HUB_LOG" && ok "slither argv: one .sol file, plain solc" || bad "argv: $(grep '^slither' "$HUB_LOG")"
SL_RC=0 run
row slither contracts/T.sol reentrancy-eth && ok "slither: exit 0 with a row: row kept" || bad "exit 0"
J_sl="$(sarif "")" SL_RC=0 run
ran slither && ! grep -q 'not run: slither' "$T/err" && ok "slither: exit 0 and an empty results list: clean, ran" || bad "clean"
J_sl="$(sarif "")" SL_RC=255 run
notrun slither && ok "slither: non-zero exit with no row: not run, never clean" || bad "rc-with-no-row"
NO_FILE=1 SL_RC=0 run
notrun slither && ok "slither: no SARIF file written: not run" || bad "no file"
J_sl='{"x":1}' run
notrun slither && ok "slither: wrong-shape output: not run" || bad "wrong shape"
HUB_MODE=crash run
notrun slither && ok "slither: crash (255): not run" || bad "crash"
cp "$T/keep/slither" "$T/bin/"; rm "$T/bin/slither"; run
grep -q 'NOT CHECKED: slither (install: pipx install slither-analyzer)' "$T/err" && jq -e 'any(.[]; .tool=="slither" and .rule=="not-checked")' "$T/out" >/dev/null && ok "slither missing: NOT CHECKED with install hint, not-checked row" || bad "missing: $(grep slither "$T/err")"
cp "$T/keep/slither" "$T/bin/"; rm "$T/bin/solc"; : >"$HUB_LOG"; run
grep -q 'NOT CHECKED: slither (no working solc on PATH' "$T/err" && ! grep -q '^slither' "$HUB_LOG" && ! ran slither && ok "no solc on PATH: NOT CHECKED, slither never run" || bad "no solc: $(grep slither "$T/err")"
printf '#!/bin/sh\nexit 1\n' >"$T/bin/solc"; chmod +x "$T/bin/solc"; : >"$HUB_LOG"; run
grep -q 'NOT CHECKED: slither (no working solc on PATH' "$T/err" && ! ran slither && ok "solc shim failing --version: NOT CHECKED, slither never run" || bad "solc shim: $(grep slither "$T/err")"
printf '#!/bin/sh\nexit 0\n' >"$T/bin/solc"; chmod +x "$T/bin/solc"
# a committed slither.config.json whose crytic-compile key would run a repo command is never read: the hub passes its own empty config
printf '{"compile_custom_build": "touch pwned"}\n' >slither.config.json; printf 'pragma solidity ^0.8.1;\n' >contracts/T.sol; G add . && G commit -q -m cfg
: >"$HUB_LOG"; SL_RC=0 run
ran slither && [ ! -e "$T/pwned" ] && grep -q -- '--config-file /' "$HUB_LOG" && ! grep -q -- '--config-file [^/]' "$HUB_LOG" && ok "slither: a repo slither.config.json is never loaded (empty temp config passed)" || bad "slither config: pwned=$([ -e "$T/pwned" ] && echo yes || echo no) $(grep '^slither' "$HUB_LOG")"
# scorecard: never executed, named only under --full or --hygiene
: >"$HUB_LOG"; run
! grep -q 'NOT CHECKED: scorecard' "$T/err" && ! grep -q '^scorecard' "$HUB_LOG" && ok "scorecard: silent in a plain diff run" || bad "plain: $(grep scorecard "$T/err")"
run --hygiene
grep -q 'NOT CHECKED: scorecard (OpenSSF Scorecard has no offline mode' "$T/err" && jq -e 'any(.[]; .tool=="scorecard" and .rule=="not-checked")' "$T/out" >/dev/null && ! grep -q '^scorecard' "$HUB_LOG" && ok "scorecard --hygiene: NOT CHECKED row, binary never run" || bad "hygiene: $(grep scorecard "$T/err")"
run --full
grep -q 'NOT CHECKED: scorecard' "$T/err" && ! grep -q '^scorecard' "$HUB_LOG" && ok "scorecard --full: NOT CHECKED, binary never run" || bad "full"
bash "$RC" --list-tools | grep -qx slither && bash "$RC" --list-tools | grep -qx scorecard && ok "--list-tools names slither and scorecard" || bad "list-tools"
[ "$fail" = 0 ]
