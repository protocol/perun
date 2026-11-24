#!/usr/bin/env bash
# review_checks.sh scorecard routing (offline, four checks): a seeded repo (pull_request_target checking out the PR head, write-all, unpinned
# action, a committed .exe) gives 4 rows; a fixed repo gives 0; a missing binary is a NOT CHECKED row with an install hint, never a failure.
# CI has no scorecard, so a stub on a hermetic PATH covers parsing, argv, token hygiene and malformed output; the real binary adds the
# seeded/fixed cases when installed.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/sclocal.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
SC=$(type -P scorecard || true)
export PERUN_HEAVY_DIR="$T/heavy" DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= TMPDIR="$T/tmp" HOME="$T/home"
mkdir -p "$T/repo" "$T/sys" "$T/base" "$T/real" "$T/tmp" "$T/home" && cd "$T/repo"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
[ -z "$SC" ] || ln -s "$SC" "$T/real/scorecard"
printf '#!/bin/sh\necho %s\n' "'{\"results\":[],\"errors\":[]}'" >"$T/base/semgrep"; printf '#!/bin/sh\necho %s\n' "'{\"Results\":[]}'" >"$T/base/trivy"
printf '#!/bin/sh\nexit 0\n' >"$T/base/gitleaks"; chmod +x "$T/base/"*
git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base
run() { PATH="$1:$T/base:$T/sys" bash "$RC" --base base 2>"$T/err" >"$T/out"; }
rows() { jq -r '[.[] | select(.tool=="scorecard" and .rule!="not-checked")] | length' "$T/out"; }
# missing binary: NOT CHECKED with the install hint, no scorecard row, run still completes
mkdir -p .github/workflows; printf 'on: push\n' >.github/workflows/ci.yml; G add . && G commit -q -m wf
run "$T/none"
grep -q 'NOT CHECKED: scorecard (install: brew install scorecard)' "$T/err" && [ "$(rows)" = 0 ] && ok "missing scorecard: NOT CHECKED with install hint" || bad "missing: $(grep scorecard "$T/err")"
# stub scorecard: logs argv and which token vars are set, prints $SC_JSON
mkdir -p "$T/stub"; cat >"$T/stub/scorecard" <<'S'
#!/bin/sh
echo "argv: $*" >>"$SC_LOG"; echo "tokens: ${GITHUB_TOKEN:+T}${GH_TOKEN:+G}${GITHUB_AUTH_TOKEN:+A}" >>"$SC_LOG"; printf '%s' "$SC_JSON"
S
chmod +x "$T/stub/scorecard"; export SC_LOG="$T/sc.log" GITHUB_TOKEN=tok1 GH_TOKEN=tok2 GITHUB_AUTH_TOKEN=tok3
srun() { : >"$SC_LOG"; export SC_JSON=$1; shift; run "$T/stub" "$@"; }
ck() { printf '{"name":"%s","score":%s,"reason":"r"}' "$1" "$2"; }
srun "{\"checks\":[$(ck Binary-Artifacts 10),$(ck Dangerous-Workflow 9),$(ck Token-Permissions 0),$(ck Pinned-Dependencies -1)]}"
[ "$(rows)" = 2 ] && [ "$(jq -r '[.[]|select(.tool=="scorecard")|.rule]|sort|join(",")' "$T/out")" = scorecard-Dangerous-Workflow,scorecard-Token-Permissions ] && ok "stub: scores 10/9/0/-1 give the 9 and 0 rows" || bad "stub scores: $(jq -c '[.[]|select(.tool=="scorecard")]' "$T/out")"
[ "$(jq -r '[.[]|select(.tool=="scorecard")|.file]|unique|join(",")' "$T/out")" = . ] && ok "stub: row file is ." || bad "stub row file: $(jq -c '[.[]|select(.tool=="scorecard")]' "$T/out")"
[ "$(grep -c '^argv:' "$SC_LOG")" = 1 ] && grep -qxF 'argv: --local=. --checks=Binary-Artifacts,Dangerous-Workflow,Token-Permissions,Pinned-Dependencies --format=json' "$SC_LOG" && ok "stub: argv is --local=. with exactly the 4 checks" || bad "stub argv: $(cat "$SC_LOG")"
grep -qxF 'tokens: ' "$SC_LOG" && ok "stub: no token env reaches scorecard" || bad "stub tokens: $(grep tokens "$SC_LOG")"
for m in '{}' '{"checks":{}}' '{"checks":[{"name":"X"}]}' '{"checks":[{"score":3}]}' '{"checks":[{"name":"X","score":"3"}]}' '{"checks":[{"name":"X","score":2.5}]}' '{"checks":[{"name":"X","score":true}]}' '{"checks":["X"]}' 'not json' ''; do
  srun "$m"
  [ "$(rows)" = 0 ] && grep -q 'not run' "$T/err" && ! grep -q 'analyzers ran:.*scorecard' "$T/err" && jq -e '[.[]|select(.tool=="scorecard" and .rule=="not-checked")]|length>0' "$T/out" >/dev/null && ok "stub: malformed ($m) is a not-run row, not clean" || bad "stub malformed ($m): $(grep scorecard "$T/err")"
done
# no workflow in the diff: the stub never runs (plain, --hygiene, --full)
mkdir "$T/repo2" && cd "$T/repo2" && git init -q . && G() { git -c user.email=t@example.com -c user.name=t "$@"; }
printf 'x\n' >README.md; G add . && G commit -q -m base && git branch base; printf 'y\n' >notes.txt; G add . && G commit -q -m notes
for f in "" --hygiene --full; do
  : >"$SC_LOG"; PATH="$T/stub:$T/base:$T/sys" SC_JSON='{"checks":[]}' bash "$RC" --base base $f 2>"$T/err" >"$T/out" || true
  [ ! -s "$SC_LOG" ] && ok "stub: no workflow in diff, never run (${f:-plain})" || bad "stub ran without a workflow (${f:-plain}): $(cat "$SC_LOG")"
done
cd "$T/repo"
if [ -z "$SC" ]; then echo "skip - real scorecard not installed: seeded/fixed cases not run"; exit "$fail"; fi
# seeded: 4 rows, one per check, score<10 (Binary-Artifacts scores 9 for one binary)
printf 'name: ci\non: pull_request_target\npermissions: write-all\njobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n        with:\n          ref: ${{ github.event.pull_request.head.sha }}\n' >.github/workflows/ci.yml
printf 'MZ' >tool.exe; G add . && G commit -q -m seeded
run "$T/real"
[ "$(rows)" = 4 ] && [ "$(jq -r '[.[] | select(.tool=="scorecard") | .rule] | sort | join(",")' "$T/out")" = scorecard-Binary-Artifacts,scorecard-Dangerous-Workflow,scorecard-Pinned-Dependencies,scorecard-Token-Permissions ] && ok "seeded repo: 4 scorecard rows" || bad "seeded: $(jq -c '[.[]|select(.tool=="scorecard")|.rule]' "$T/out") $(grep scorecard "$T/err")"
# fixed: sha-pinned, read-only, no binary, no pull_request_target
G rm -q tool.exe
printf 'name: ci\non: push\npermissions: read-all\njobs:\n  b:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683\n' >.github/workflows/ci.yml
G add . && G commit -q -m fixed
run "$T/real"
[ "$(rows)" = 0 ] && ! grep -q 'NOT CHECKED: scorecard' "$T/err" && grep -q 'analyzers ran:.*scorecard' "$T/err" && ok "fixed repo: 0 scorecard rows, listed as ran" || bad "fixed: $(jq -c '[.[]|select(.tool=="scorecard")]' "$T/out") $(grep scorecard "$T/err")"
exit "$fail"
