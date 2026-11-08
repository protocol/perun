#!/usr/bin/env bash
# review_checks.sh action-tag dedup: a semgrep github-actions-mutable-action-tag row is dropped when zizmor flagged the same file and line
# as unpinned-uses (one defect reported twice). A different line, or zizmor not running, keeps the semgrep row. Stub semgrep and zizmor on a
# hermetic PATH, fictional workflow content only. REVIEW_CHECKS=<path> runs another copy of the script (used to prove the same-line case fails before the change).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/actdedup.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT
fail=0
export DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 REVIEW_SEMGREP_REGISTRY=0
unset REVIEW_OSV REVIEW_OSV_DB_DIR OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY REVIEW_SEMGREP_CONFIG REVIEW_FIXTURE_ROWS REVIEW_TEST_CMD
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir -p "$T/bin" "$T/zbin" "$T/sys"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep cmp nice uname; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b" # only the system binaries review_checks.sh needs, never the host PATH
done
cat >"$T/bin/semgrep" <<'S'
#!/usr/bin/env bash
cat "$SG_JSON"
S
cat >"$T/zbin/zizmor" <<'S'
#!/usr/bin/env bash
cat "$ZZ_JSON"; exit 13
S
chmod +x "$T/bin/semgrep" "$T/zbin/zizmor"
WF=.github/workflows/ci.yml
mkdir -p "$T/repo" && cd "$T/repo" && git init -q . && G commit -q --allow-empty -m base && git branch base
mkdir -p .github/workflows && printf 'name: acme-ci\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: make test\n      - run: make lint\n      - run: make pack\n' >"$WF"
G add -A && G commit -q -m change
sgjson() { printf '{"results":[{"check_id":"github-actions-mutable-action-tag","path":"%s","start":{"line":%s},"extra":{"message":"mutable tag"}}],"errors":[],"paths":{"scanned":["%s"]}}\n' "$WF" "$1" "$WF"; }
zzjson() { printf '[{"ident":"unpinned-uses","desc":"d","locations":[{"symbolic":{"kind":"Primary","key":{"Local":{"verbatim_path":"%s"}}},"concrete":{"location":{"start_point":{"row":%s}}}}]}]\n' "$WF" "$1"; }
# go PATH SG_LINE ZZ_ROW: run the hub on the change; the semgrep row sits on SG_LINE, the zizmor row on 0-based ZZ_ROW (empty = no zizmor output)
go() {
  sgjson "$2" >"$T/sg.json"; [ -z "$3" ] || zzjson "$3" >"$T/zz.json"
  PATH="$1:$T/sys" SG_JSON="$T/sg.json" ZZ_JSON="$T/zz.json" bash "$RC" --base base >"$T/out" 2>"$T/err" || true
}
# cnt TOOL RULE_SUFFIX LINE: rows of TOOL whose rule ends with RULE_SUFFIX on LINE
cnt() { jq --arg t "$1" --arg r "$2" --argjson l "$3" '[.[] | select(.tool==$t and (.rule|endswith($r)) and .line==$l)] | length' "$T/out"; }
eq() { if [ "$1" = "$2" ]; then echo "ok - $3"; else echo "FAIL - $3 (got $1, want $2)"; fail=1; fi; }

go "$T/bin:$T/zbin" 5 4 # same file:line (zizmor row 0-based 4 = line 5)
eq "$(cnt semgrep github-actions-mutable-action-tag 5)" 0 "same line: semgrep mutable-action-tag row dropped"
eq "$(cnt zizmor unpinned-uses 5)" 1 "same line: zizmor unpinned-uses row kept"

go "$T/bin:$T/zbin" 5 8 # zizmor flags line 9, semgrep line 5
eq "$(cnt semgrep github-actions-mutable-action-tag 5)" 1 "different line: semgrep row kept"
eq "$(cnt zizmor unpinned-uses 9)" 1 "different line: zizmor row kept"

go "$T/bin" 5 "" # zizmor not run
eq "$(cnt semgrep github-actions-mutable-action-tag 5)" 1 "zizmor absent: semgrep row kept"
exit $fail
