#!/usr/bin/env bash
# review_checks.sh hub routing for pmd (Java) and solhint (Solidity) with stub binaries on a hermetic PATH (no real tool, no network):
# rows keep findings, a missing tool is "NOT CHECKED", and a crash, empty output, wrong-shape output or a non-zero exit with no row is
# "not run", never clean. The fail-open cases (exit 4/1 with an empty results list) fail before the guard in review_checks.sh.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubpms.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" "$T/home" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
mkdir -p src contracts
printf 'class A {}\n' >src/A.java; printf 'pragma solidity ^0.8.0;\n' >contracts/T.sol; printf 'a\n' >notes.txt
G add . && G commit -q -m code
cat >"$T/bin/pmd" <<'S'
#!/usr/bin/env bash
echo "pmd $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_pmd"
exit "${PMD_RC:-4}"
S
cat >"$T/bin/solhint" <<'S'
#!/usr/bin/env bash
echo "solhint $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
[ "$1" != --config ] || echo "cfg: $(cat "$2")" >>"$HUB_LOG"
printf '%s' "$J_sol"
exit "${SOL_RC:-1}"
S
chmod +x "$T/bin/pmd" "$T/bin/solhint"; mkdir "$T/keep"; cp "$T/bin/pmd" "$T/bin/solhint" "$T/keep/"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
sarif() { printf '{"version":"2.1.0","runs":[{"results":[%s]}]}' "$1"; }
res() { printf '{"ruleId":"%s","message":{"text":"m"},"locations":[{"physicalLocation":{"artifactLocation":{"uri":"%s"},"region":{"startLine":%s}}}]}' "$1" "$2" "$3"; }
export J_pmd="$(sarif "$(res HardCodedCryptoKey src/A.java 3)")"
export J_sol="$(sarif "$(res avoid-tx-origin contracts/T.sol 4)")"
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
: >"$HUB_LOG"; run
row pmd src/A.java HardCodedCryptoKey && ran pmd && ok "pmd: exit 4 with a row: row kept, ran" || bad "pmd rows: $(jq -c '[.[]|select(.tool=="pmd")]' "$T/out")"
row solhint contracts/T.sol avoid-tx-origin && ran solhint && ok "solhint: exit 1 with a row: row kept, ran" || bad "sol rows: $(jq -c '[.[]|select(.tool=="solhint")]' "$T/out")"
grep -q 'pmd check --no-cache --no-progress -R category/java/security.xml -f sarif -d ./src/A.java' "$HUB_LOG" && ! grep -q 'notes.txt' "$HUB_LOG" && ok "pmd argv: built-in security ruleset, one file" || bad "pmd argv: $(grep '^pmd' "$HUB_LOG")"
grep -q -- 'solhint --config .* -f sarif --noPoster --disc ./contracts/T.sol' "$HUB_LOG" && grep -q 'cfg: {"extends":"solhint:recommended"}' "$HUB_LOG" && ok "solhint argv: throwaway recommended config, sarif, no update check" || bad "sol argv: $(grep solhint "$HUB_LOG")"
# fail-open regressions: never clean
J_pmd= J_sol= run
notrun pmd && notrun solhint && ok "empty output: not run" || bad "empty"
J_pmd=$' \n' J_sol=$' \n' run
notrun pmd && notrun solhint && ok "whitespace-only output: not run" || bad "whitespace"
J_pmd='{"x":1}' J_sol='{"x":1}' run
notrun pmd && notrun solhint && ok "wrong-shape JSON: not run" || bad "wrong shape"
J_pmd='{"runs":[]}' J_sol='{"runs":[]}' run
notrun pmd && notrun solhint && ok "SARIF with no runs: not run" || bad "no runs"
HUB_MODE=crash run
notrun pmd && notrun solhint && ok "crash: not run" || bad "crash"
PMD_RC=4 SOL_RC=1 J_pmd="$(sarif "")" J_sol="$(sarif "")" run
notrun pmd && notrun solhint && ok "violation exit (4 / 1) with an empty results list: not run, not clean (fail-open guard)" || bad "rc-with-no-row"
PMD_RC=5 J_pmd="$(sarif "$(res HardCodedCryptoKey src/A.java 3)")" run
notrun pmd && ok "pmd: exit 5 (recoverable error) even with a row: not run" || bad "pmd exit5"
PMD_RC=1 J_pmd="$(sarif "")" run
notrun pmd && ok "pmd: exit 1 (exception): not run" || bad "pmd exit1"
SOL_RC=3 J_sol="$(sarif "$(res avoid-tx-origin contracts/T.sol 4)")" run
notrun solhint && ok "solhint: exit 3 (not 0/1): not run" || bad "sol exit3"
PMD_RC=0 SOL_RC=0 J_pmd="$(sarif "")" J_sol="$(sarif "")" run
ran pmd && ran solhint && ! grep -q 'not run: pmd\|not run: solhint' "$T/err" && ok "exit 0 and an empty results list: clean, ran" || bad "clean"
PMD_RC=4 J_pmd="$(sarif "{\"ruleId\":\"x\",\"message\":{\"text\":\"m\"}}")" run
notrun pmd && ok "pmd: a result with no location: not run, never dropped" || bad "no location"
# gates
cp "$T/keep/pmd" "$T/keep/solhint" "$T/bin/"; rm "$T/bin/pmd" "$T/bin/solhint"; run
grep -q 'NOT CHECKED: pmd (install: brew install pmd)' "$T/err" && grep -q 'NOT CHECKED: solhint (install: npm install -g solhint)' "$T/err" && jq -e 'any(.[]; .tool=="pmd" and .rule=="not-checked")' "$T/out" >/dev/null && ok "missing tools: NOT CHECKED with install hint" || bad "missing tools"
cp "$T/keep/pmd" "$T/keep/solhint" "$T/bin/"
git checkout -q -b other base; mkdir docs; printf 'x\n' >docs/a.md; printf '{"plugins":["evil"]}\n' >.solhint.json; G add . && G commit -q -m docs; : >"$HUB_LOG"; run
! grep -q '^pmd\|^solhint' "$HUB_LOG" && ok "no .java or .sol in the diff: neither tool runs (a project .solhint.json alone is never read)" || bad "unrouted"
[ "$fail" = 0 ]
