#!/usr/bin/env bash
# review_checks.sh hub routing for sobelow (Elixir Phoenix, local source) and pmd (Java security ruleset) with stub binaries on a hermetic PATH
# (no real tool, no network): rows keep findings, a missing tool is "NOT CHECKED", and a crash, empty or whitespace output, an exit that disagrees
# with the report, or wrong-shape output is "not run", never clean.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubl2.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
export PERUN_HEAVY_DIR="$T/heavy" HUB_LOG="$T/hub.log" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp"
mkdir -p "$T/repo" "$T/bin" "$T/base" "$T/sys" "$T/tmp" && cd "$T/repo"
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir -p lib; printf 'x\n' >README.md; printf 'defp deps, do: [{:phoenix, "~> 1.7"}]\n' >mix.exs; G add . && G commit -q -m base && git branch base
printf 'x = 1\n' >lib/a.ex; printf 'class A {}\n' >A.java; G add . && G commit -q -m code
cat >"$T/bin/sobelow" <<'S'
#!/usr/bin/env bash
echo "sobelow $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
printf '%s' "$J_sob"
exit "${SOB_RC:-1}"
S
cat >"$T/bin/pmd" <<'S'
#!/usr/bin/env bash
echo "pmd $*" >>"$HUB_LOG"
[ "${HUB_MODE:-}" != crash ] || exit 9
for a in "$@"; do [ -f "$a" ] && cat "$a" >>"$HUB_LOG"; done
printf '%s' "$J_pmd"
exit "${PMD_RC:-4}"
S
chmod +x "$T/bin/sobelow" "$T/bin/pmd"; mkdir "$T/keep"; cp "$T/bin/sobelow" "$T/bin/pmd" "$T/keep/"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"
printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"
chmod +x "$T/base/semgrep" "$T/base/trivy" "$T/base/gitleaks"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
SOB='{"findings":{"high_confidence":[{"type":"XSS.Raw","file":"lib/a.ex","line":3}],"medium_confidence":[],"low_confidence":[{"type":"Config.CSP","file":"lib/other.ex","line":0}]},"total_findings":2,"sobelow_version":"0.13.0"}'
PMD='{"formatVersion":0,"pmdVersion":"7.0.0","timestamp":"t","files":[{"filename":"'"$T/repo"'/A.java","violations":[{"beginline":1,"rule":"HardCodedCryptoKey","ruleset":"Security","priority":3,"description":"hardcoded key"}]}],"processingErrors":[],"configurationErrors":[]}'
LOG=$'\n[INFO] done\n'
export J_sob="$LOG$SOB" J_pmd="$LOG$PMD"
run() { PATH="$T/bin:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
row() { jq -e --arg t "$1" --arg f "$2" --arg r "$3" 'any(.[]; .tool==$t and .file==$f and .rule==$r)' "$T/out" >/dev/null; }
ran() { grep -qE "analyzers ran:.*\b$1\b" "$T/err"; }
notrun() { grep -q "not run: $1" "$T/err" && ! ran "$1"; }
: >"$HUB_LOG"; run
row sobelow lib/a.ex XSS.Raw && ! row sobelow lib/other.ex Config.CSP && ok "sobelow: row for the changed file, unchanged file dropped, leading log line skipped" || bad "sob rows: $(jq -c '[.[]|select(.tool=="sobelow")|.rule]' "$T/out")"
row pmd A.java HardCodedCryptoKey && ok "pmd: row for the changed file, log line skipped" || bad "pmd rows: $(jq -c '[.[]|select(.tool=="pmd")]' "$T/out")"
grep -qx 'sobelow --format json --private --exit low' "$HUB_LOG" && grep -q -- '^pmd check --file-list .* -R category/java/security.xml -f json --no-cache --no-progress$' "$HUB_LOG" && grep -qx './A.java' "$HUB_LOG" && ok "argv: sobelow offline json with --exit low; pmd check on the changed file list" || bad "argv: $(cat "$HUB_LOG")"
ran sobelow && ran pmd && ok "both ran" || bad "ran list"
# never clean: empty, whitespace, exit mismatch, wrong shape, text, errors, a crash
SOB_RC=1 J_sob= PMD_RC=4 J_pmd= run
notrun sobelow && notrun pmd && ok "empty output: not run" || bad "empty"
J_sob=$' \n\t\n' J_pmd=$' \n' run
notrun sobelow && notrun pmd && ok "whitespace-only output: not run" || bad "whitespace"
SOB_RC=0 PMD_RC=0 run
notrun sobelow && notrun pmd && ok "exit 0 with findings: not run" || bad "exit0 rows"
EMPTYS='{"findings":{"high_confidence":[],"medium_confidence":[],"low_confidence":[]},"total_findings":0}'
EMPTYP='{"formatVersion":0,"files":[]}'
SOB_RC=1 J_sob=$EMPTYS PMD_RC=4 J_pmd=$EMPTYP run
notrun sobelow && notrun pmd && ok "nonzero exit with no findings: not run" || bad "exit with no rows"
SOB_RC=0 J_sob=$LOG$EMPTYS PMD_RC=0 J_pmd=$EMPTYP$LOG run
ran sobelow && ran pmd && ! grep -q 'not run: \(sobelow\|pmd\)' "$T/err" && ok "empty reports, exit 0: clean, ran" || bad "clean"
SOB_RC=1 J_sob='{"findings":{"high_confidence":[{"type":"X","file":"lib/a.ex","line":1}],"medium_confidence":[],"low_confidence":[]},"total_findings":5}' run
notrun sobelow && ok "sobelow: total_findings disagrees with the lists: not run" || bad "sob count"
PMD_RC=4 J_pmd='{"files":[{"filename":"A.java","violations":[{"beginline":1,"rule":"R"}]}],"processingErrors":[{"message":"parse error"}]}' run
notrun pmd && ok "pmd: processingErrors non-empty: not run" || bad "pmd errors"
PMD_RC=1 run
notrun pmd && ok "pmd exit 1 (exception): not run" || bad "pmd exit1"
SOB_RC=1 J_sob='{"x":1}' PMD_RC=4 J_pmd='{"x":1}' run
notrun sobelow && notrun pmd && ok "wrong-shape JSON: not run" || bad "wrong shape"
J_sob='This does not appear to be a Phoenix application.' J_pmd='some text' SOB_RC=0 run
notrun sobelow && notrun pmd && ok "plain text: not run" || bad "text"
HUB_MODE=crash run
notrun sobelow && notrun pmd && ok "crash: not run" || bad "crash"
# gates
rm "$T/bin/sobelow" "$T/bin/pmd"; run
grep -q 'NOT CHECKED: sobelow (install: mix escript.install hex sobelow)' "$T/err" && grep -q 'NOT CHECKED: pmd (install: brew install pmd)' "$T/err" && jq -e 'any(.[]; .tool=="pmd" and .rule=="not-checked")' "$T/out" >/dev/null && ok "missing tools: NOT CHECKED with install hint" || bad "missing tool"
cp "$T/keep/sobelow" "$T/keep/pmd" "$T/bin/"
# no Phoenix app: sobelow not routed
git reset -q --hard base; printf 'defp deps, do: []\n' >mix.exs; G commit -qam nophx; mkdir -p lib; printf 'x = 2\n' >lib/a.ex; G add . && G commit -q -m ex; : >"$HUB_LOG"; run
! grep -q 'sobelow' "$HUB_LOG" && ok "no :phoenix in mix.exs: sobelow not routed" || bad "no phoenix"
# mix.exs is code: a diff that changes it is not run
git reset -q --hard base; printf 'defp deps, do: [{:phoenix, "~> 1.7"}, {:x, "1"}]\n' >mix.exs; mkdir -p lib; printf 'x = 3\n' >lib/a.ex; G add . && G commit -q -m mixchg; : >"$HUB_LOG"; run
grep -q 'NOT CHECKED: sobelow (mix.exs changed' "$T/err" && ! grep -q '^sobelow' "$HUB_LOG" && ok "mix.exs changed in the diff: sobelow not run" || bad "mix.exs changed"
exit $fail
