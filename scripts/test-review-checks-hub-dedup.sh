#!/usr/bin/env bash
# review_checks.sh hub corroboration: semgrep, zizmor and actionlint rows on the same file:line keep one row each, all marked with the three tools
# and a corroborated-by suffix; no row is dropped; a different line is unmarked, and one tool on two lines is not corroboration. Stub tools on a
# hermetic PATH, fictional workflow content only.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/hubdedup.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
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
cat >"$T/bin/zizmor" <<'S'
#!/usr/bin/env bash
cat "$ZZ_JSON"; exit 13
S
cat >"$T/bin/actionlint" <<'S'
#!/usr/bin/env bash
cat "$AL_JSON"; exit 1
S
chmod +x "$T/bin/"*
WF=.github/workflows/ci.yml
mkdir -p "$T/repo" && cd "$T/repo" && git init -q . && G commit -q --allow-empty -m base && git branch base
mkdir -p .github/workflows && printf 'name: acme-ci\non: push\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - run: make test\n      - run: make lint\n      - run: make pack\n' >"$WF"
G add -A && G commit -q -m change
# sg LINE...: one semgrep row per line, message "low: ..."; zz ROW0...: zizmor rows (0-based); al LINE...: actionlint rows, message "error: ..."
sg() { local r= l; for l in "$@"; do r+="${r:+,}{\"check_id\":\"acme-rule\",\"path\":\"$WF\",\"start\":{\"line\":$l},\"extra\":{\"message\":\"low: mutable tag\"}}"; done; printf '{"results":[%s],"errors":[],"paths":{"scanned":["%s"]}}\n' "$r" "$WF"; }
zz() { local r= l; for l in "$@"; do r+="${r:+,}{\"ident\":\"unpinned-uses\",\"desc\":\"d\",\"locations\":[{\"symbolic\":{\"kind\":\"Primary\",\"key\":{\"Local\":{\"verbatim_path\":\"$WF\"}}},\"concrete\":{\"location\":{\"start_point\":{\"row\":$l}}}}]}"; done; printf '[%s]\n' "$r"; }
al() { local r= l; for l in "$@"; do r+="${r:+,}{\"message\":\"error: bad step\",\"filepath\":\"$WF\",\"line\":$l,\"kind\":\"expression\"}"; done; printf '[%s]\n' "$r"; }
go() { PATH="$T/bin:$T/sys" SG_JSON="$T/sg.json" ZZ_JSON="$T/zz.json" AL_JSON="$T/al.json" bash "$RC" --base base >"$T/out" 2>"$T/err" || true; }
at() { jq -c --argjson l "$1" '[.[] | select(.line==$l and .rule!="not-checked")]' "$T/out"; }
eq() { if [ "$1" = "$2" ]; then echo "ok - $3"; else echo "FAIL - $3 (got $1, want $2)"; fail=1; fi; }

sg 5 >"$T/sg.json"; zz 4 >"$T/zz.json"; al 5 >"$T/al.json"; go # all three on line 5
eq "$(at 5 | jq length)" 3 "3 tools, same line: all 3 rows kept"
eq "$(at 5 | jq -r '[.[].tools | sort | join(",")] | unique | join(";")')" "actionlint,semgrep,zizmor" "every row names all 3 tools"
eq "$(at 5 | jq -r 'all(.[]; .message | test("\\[corroborated by: actionlint, semgrep, zizmor\\]$"))')" true "every message carries the suffix"

sg 5 9 >"$T/sg.json"; zz 99 >"$T/zz.json"; al 99 >"$T/al.json"; go # only semgrep has rows on 5 and 9
eq "$(at 5 | jq length)$(at 9 | jq length)" 11 "one tool, 2 lines: 2 rows"
eq "$(jq '[.[] | select(.tools)] | length' "$T/out")" 0 "one tool alone is not corroborated"
eq "$(jq '[.[] | select(.tool=="semgrep")] | length' "$T/out")" 2 "no merge across lines"
exit $fail
