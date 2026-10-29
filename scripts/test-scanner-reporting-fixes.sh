#!/usr/bin/env bash
# Regression tests for four scanner-reporting bugs (stub scanners, hermetic, offline):
#  1 review_checks.sh keeps every temp file in one private per-run dir (concurrent runs sharing $TMPDIR do not clobber)
#  2 semgrep that emits findings is never reported "not run"; a partial scan says "partial: semgrep ran"
#  3 tsc is found at the repo's node_modules/.bin/tsc when not on PATH, runs only with REVIEW_TEST_CMD (project code), never from a parent above the git toplevel
#  5 semgrep exit 3 with zero results reads as not run ("scan errored"), not ran
#  4 supply_chain_check.sh: no workflows = n/a for zizmor/actionlint, not SKIPPED/INCOMPLETE; workflows + missing tool = SKIPPED; a glob metachar in the dir path still finds workflows
# shellcheck disable=SC2015
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SK=$ROOT/.claude/skills/deep-code-review/scripts
T=$(mktemp -d "${TMPDIR:-/tmp}/srf.XXXXXX") && [ -d "$T" ] || exit 1
trap 'rm -rf "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
mkdir -p "$T/stub" "$T/repo" "$T/tmp" "$T/nowf" "$T/wf/.github/workflows"
: >"$T/wf/.github/workflows/ci.yml"
cat >"$T/stub/semgrep" <<'S'
#!/usr/bin/env bash
# records how many entries sit directly in $TMPDIR while a scanner runs; sleeps so runs overlap
ls "$TMPDIR" | wc -l | tr -d " " >>"$SG_ENTRIES"
sleep "${SG_SLEEP:-0}"
r="{\"path\":\"app.py\",\"start\":{\"line\":2},\"check_id\":\"perun.$TAG\",\"extra\":{\"message\":\"m\"}}"; [ -z "${SG_EMPTY:-}" ] || r=
echo "{\"results\":[$r],\"errors\":[${SG_ERR:-}]}"
S
chmod +x "$T/stub/semgrep"
export PERUN_HEAVY_DIR="$T/heavy" SG_ENTRIES="$T/entries"; : >"$SG_ENTRIES"
mkrepo() { mkdir -p "$1" && cd "$1" && git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base && git branch base
  printf 'x\ny\n' >app.py; git add . && git -c user.email=t@example.com -c user.name=t commit -q -m f; }
mkrepo "$T/repo"
rc() { (cd "$T/repo" && PATH="$T/stub:$PATH" TMPDIR="$T/tmp" bash "$SK/review_checks.sh" --base base "$@"); }

# 1: one private dir while running, nothing left after, two overlapping runs keep their own output
TAG=one SG_SLEEP=2 rc >"$T/o1" 2>"$T/e1" & p1=$!
TAG=two SG_SLEEP=2 rc >"$T/o2" 2>"$T/e2" & p2=$!
wait $p1 $p2
[ -s "$SG_ENTRIES" ] && ! grep -qvx 2 "$SG_ENTRIES" && ok "temp files live in one private dir per run (2 dirs for 2 runs)" || { bad "temp files not in one private dir"; cat "$SG_ENTRIES"; }
jq -e 'any(.[]; .rule=="perun.one")' "$T/o1" >/dev/null && ! jq -e 'any(.[]; .rule=="perun.two")' "$T/o1" >/dev/null \
  && jq -e 'any(.[]; .rule=="perun.two")' "$T/o2" >/dev/null && ! jq -e 'any(.[]; .rule=="perun.one")' "$T/o2" >/dev/null && ok "concurrent runs do not clobber each other" || bad "concurrent output mixed"
[ -z "$(ls "$T/tmp")" ] && ok "TMPDIR clean after runs" || bad "temp left behind"

# 2: semgrep status matches findings
TAG=ok rc >"$T/o" 2>"$T/e"
! grep -q 'not run: semgrep' "$T/e" && jq -e 'any(.[]; .tool=="semgrep")' "$T/o" >/dev/null && ok "clean semgrep run: findings, no not-run line" || bad "clean semgrep status"
SG_ERR='{"message":"x"}' TAG=part rc >"$T/o" 2>"$T/e"
jq -e 'any(.[]; .tool=="semgrep")' "$T/o" >/dev/null && ! grep -q 'not run: semgrep' "$T/e" && grep -q 'partial: semgrep ran' "$T/e" && ok "partial semgrep: ran + partial note, findings kept" || { bad "partial semgrep status"; cat "$T/e"; }

# 5: semgrep errored with no results is not "ran"
cd "$T/repo" && SG_EMPTY=1 SG_ERR='{"message":"x"}' TAG=empty rc >"$T/o" 2>"$T/e"
grep -q 'not run: semgrep (scan errored, no findings)' "$T/e" && ! grep -q 'partial: semgrep ran' "$T/e" && ! grep 'analyzers ran:' "$T/e" | grep -q semgrep && ! jq -e 'any(.[]; .tool=="semgrep" and .rule!="not-checked")' "$T/o" >/dev/null && ok "semgrep empty + errors: not run, not ran" || { bad "empty errored semgrep status"; cat "$T/e"; cat "$T/o"; }
cd "$ROOT" || exit 1

# 3: tsc from node_modules/.bin (not on PATH)
mkdir -p "$T/tsc/node_modules/.bin" && cd "$T/tsc" && git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base && git branch base
echo '{}' >tsconfig.json; echo 'let a: number = "s";' >a.ts
printf '#!/usr/bin/env bash\necho "a.ts(1,5): error TS2322: bad"\nexit 2\n' >node_modules/.bin/tsc; chmod +x node_modules/.bin/tsc
git add tsconfig.json a.ts && git -c user.email=t@example.com -c user.name=t commit -q -m f
tscrun() { PATH="/usr/bin:/bin" TMPDIR="$T/tmp" bash "$SK/review_checks.sh" --base base >"$T/o" 2>"$T/e"; }
REVIEW_TEST_CMD=true tscrun
! grep -q 'not run: tsc' "$T/e" && jq -e 'any(.[]; .tool=="tsc" and .rule=="TS2322")' "$T/o" >/dev/null && ok "local node_modules/.bin/tsc detected and run with REVIEW_TEST_CMD" || { bad "local tsc not detected"; cat "$T/e"; }
tscrun
grep -q 'not run: tsc (repo-local tsc not run' "$T/e" && ! jq -e 'any(.[]; .tool=="tsc" and .rule=="TS2322")' "$T/o" >/dev/null && ok "local tsc not executed without REVIEW_TEST_CMD" || { bad "local tsc ran without opt-in"; cat "$T/e"; }
# tsc only in a parent above the git toplevel: must not be found or executed
mkdir -p "$T/par/node_modules/.bin" "$T/par/repo" && cp node_modules/.bin/tsc "$T/par/node_modules/.bin/tsc"
cd "$T/par/repo" && git init -q . && git -c user.email=t@example.com -c user.name=t commit -q --allow-empty -m base && git branch base
echo '{}' >tsconfig.json; echo 'let a: number = "s";' >a.ts; git add . && git -c user.email=t@example.com -c user.name=t commit -q -m f
REVIEW_TEST_CMD=true tscrun
grep -q 'not run: tsc (not installed)' "$T/e" && ! jq -e 'any(.[]; .tool=="tsc")' "$T/o" >/dev/null && ok "tsc in a parent above the toplevel is ignored" || { bad "parent tsc used"; cat "$T/e"; }
cd "$ROOT" || exit 1

# 4: supply chain: no workflows = n/a; workflows + missing tool = SKIPPED
SC=$SK/supply_chain_check.sh; sys=$T/sys; mkdir -p "$sys"; for t in cat grep python3 dirname env bash find head; do ln -sf "$(command -v $t)" "$sys/$t"; done
o=$(PATH="$sys" /bin/bash "$SC" "$T/nowf" 2>&1)
printf '%s' "$o" | grep -q 'n/a zizmor' && printf '%s' "$o" | grep -q 'n/a actionlint' && ! printf '%s' "$o" | grep -qE 'SKIPPED (zizmor|actionlint)|INCOMPLETE:.*(zizmor|actionlint)' && ok "no workflows: n/a, not INCOMPLETE" || { bad "no workflows still skipped"; echo "$o"; }
o=$(PATH="$sys" /bin/bash "$SC" "$T/wf" 2>&1)
printf '%s' "$o" | grep -q 'SKIPPED zizmor: not installed' && printf '%s' "$o" | grep -qE 'INCOMPLETE:.*zizmor' && ok "workflows + missing tool: INCOMPLETE" || { bad "missing tool with workflows not INCOMPLETE"; echo "$o"; }
mkdir -p "$T/g[1]x/.github/workflows" && : >"$T/g[1]x/.github/workflows/ci.yml"
o=$(PATH="$sys" /bin/bash "$SC" "$T/g[1]x" 2>&1)
! printf '%s' "$o" | grep -q 'n/a zizmor' && printf '%s' "$o" | grep -q 'SKIPPED zizmor: not installed' && ok "glob metachar in dir: workflows still detected" || { bad "glob dir read as no workflows"; echo "$o"; }
exit $fail
