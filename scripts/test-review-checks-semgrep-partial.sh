#!/usr/bin/env bash
# review_checks.sh semgrep partial coverage: when semgrep reports errors on some files, the hub names each of those files in a
# not-checked row (20 per chunk, then one summary row) and appends the error counts by type and level to the partial line, which keeps
# its prefix. Stub semgrep on a hermetic PATH and synthetic fixtures only, so it runs offline anywhere. Blocks:
#  warn       a warn-level PartialParsing on 1 of 3 files: still partial (never downgraded), one row for that file, counts on stderr, findings unchanged
#  cap        25 errored files and no findings: 20 named rows plus one summary row naming the first path left out, counts exact and ordered by count
#  chunks     two chunks (200 and 30 files) with equal error counts: each keeps its own summary row and its own partial line (the closing dedup of identical rows must not merge them)
#  summary    the stderr "N findings" counts rows other than not-checked, and a separate line counts the not-checked rows
#  same file  several errors on one file are one row; an error with no path is counted, not rowed
#  every file errors on every scanned file, or a path-less error and no findings: NOT RUN as before, and no row names a file
#  shapes     odd error shapes never lose the findings; a control character in a path becomes "?" and the row stays
# REVIEW_CHECKS=<path> runs another copy of the script (used to prove the cases fail before the change).
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
RC=${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}
T=$(mktemp -d "${TMPDIR:-/tmp}/sgpart.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap 'cd /; rm -r -- "$T"' EXIT
unset REVIEW_OSV REVIEW_OSV_DB_DIR OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY REVIEW_SEMGREP_CONFIG REVIEW_SEMGREP_REGISTRY REVIEW_TRIVY_CACHE REVIEW_FIXTURE_ROWS REVIEW_TEST_CMD
export DCR_CACHE_ROOT="$T/nocache" DCR_USER_BIN= # hermetic: a provisioned host cache or ~/.local/bin must not change which branch runs
n=0 fail=0
t() { local d=$1; shift; n=$((n + 1)); if "$@" >/dev/null 2>&1; then echo "ok - $d"; else echo "FAIL - $d"; fail=$((fail + 1)); fi; }
not() { ! "$@"; }
G() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir -p "$T/bin" "$T/sys"
# Hermetic PATH: the stub dir plus $T/sys (symlinks to only the system binaries review_checks.sh needs), never the host PATH.
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep cmp nice uname; do
  p=$(type -P "$b") || continue; ln -s "$p" "$T/sys/$b"
done
cat >"$T/bin/semgrep" <<'S'
#!/usr/bin/env bash
# call N of a hub run (one per 200-file chunk) answers with $SG_DIR/N.json
n=$(( $(cat "$SG_DIR/n" 2>/dev/null || echo 0) + 1 )); echo "$n" >"$SG_DIR/n"; cat "$SG_DIR/$n.json"
S
chmod +x "$T/bin/semgrep"
newrepo() { # newrepo NAME: fresh repo under $T with an empty commit tagged `base`; leaves cwd inside it
  mkdir -p "$T/$1" && cd "$T/$1" && git init -q . && case "$(git rev-parse --show-toplevel)" in "$(cd "$T" && pwd -P)"/*) ;; *) echo "refusing: repo not under temp dir" >&2; exit 1 ;; esac
  G commit -q --allow-empty -m base && git branch base
}
commit() { G add -A && G commit -q -m change; }
sg() { # sg JSON...: run the hub on the repo; the Nth semgrep call (one per 200-file chunk) answers with the Nth JSON; stdout -> $T/out, stderr -> $T/err
  local d i=0 j; d=$(mktemp -d "$T/sgd.XXXXXX")
  for j in "$@"; do i=$((i + 1)); printf '%s\n' "$j" >"$d/$i.json"; done
  PATH="$T/bin:$T/sys" SG_DIR=$d REVIEW_SEMGREP_REGISTRY=0 PERUN_HEAVY_DIR="$T/heavy" REVIEW_LEASE_WAIT=0 bash "$RC" --base base >"$T/out" 2>"$T/err" || true
}
row() { jq -e --arg f "$1" --arg r "$2" 'any(.[]; .tool=="semgrep" and .file==$f and .rule==$r)' "$T/out"; } # row FILE RULE
nrows() { jq -e --argjson n "$2" "[.[] | select(.tool==\"semgrep\" and $1)] | length == \$n" "$T/out"; } # nrows JQ_FILTER COUNT
errhas() { grep -qE -- "$1" "$T/err"; }
errcount() { [ "$(grep -cE -- "$1" "$T/err" || true)" = "$2" ]; } # errcount REGEX COUNT: stderr lines matching
ran() { errhas "analyzers ran:.*\\bsemgrep\\b"; }
PREFIX='review_checks: partial: semgrep ran but reported errors \(coverage incomplete; findings above are real\)'

# --- warn: a warn-level PartialParsing is a gap, not a clean; the file gets a row and the counts land on the partial line
newrepo warn; mkdir src; for f in acme_tool acme_lib acme_other; do echo 'echo hi' >"src/$f.sh"; done; commit
sg '{"results":[{"check_id":"acme.shell.eval-input","path":"src/acme_lib.sh","start":{"line":4},"extra":{"message":"eval of input"}}],
 "errors":[{"code":3,"level":"warn","type":["PartialParsing",[{"path":"src/acme_tool.sh","start":{"line":9,"col":1,"offset":120},"end":{"line":9,"col":5,"offset":124}}]],"path":"src/acme_tool.sh","message":"Syntax error at line 9"}],
 "paths":{"scanned":["src/acme_lib.sh","src/acme_other.sh","src/acme_tool.sh"]}}'
t "warn: not voided (no NOT RUN)" not errhas 'NOT RUN:.*semgrep'
t "warn: listed as ran" ran
t "warn: partial in the closing line" errhas 'partial: semgrep\(errors\)'
t "warn: partial line keeps its prefix and ends with the counts" errhas "^$PREFIX \(1 error\(s\) on 1 of 3 scanned file\(s\): PartialParsing \(warn\) x1; see not-checked rows\)\$"
t "warn: one not-checked row" nrows '.rule=="not-checked"' 1
t "warn: ...on the errored path, line 0, naming type and level" jq -e 'any(.[]; .tool=="semgrep" and .rule=="not-checked" and .file=="src/acme_tool.sh" and .line==0 and .message=="semgrep could not fully read this file (PartialParsing, warn); rules may have missed part of it")' "$T/out"
t "warn: finding row unchanged" jq -e 'any(.[]; .tool=="semgrep" and .file=="src/acme_lib.sh" and .line==4 and .rule=="acme.shell.eval-input" and .message=="eval of input")' "$T/out"
t "warn: ...and it is the only finding" nrows '.rule!="not-checked"' 1

# --- cap: 25 errored files of 30 and no findings (so 5 scanned files raised no error: partial, not NOT RUN)
newrepo cap; mkdir f
python3 - "$T/cap.json" <<'PY'
import json, sys
names = [f"f/{i:02d}.txt" for i in range(30)]
for p in names: open(p, "w").write("x\n")
errs = [{"code": 3, "level": "error", "type": "Syntax error", "path": p, "message": "m"} if i % 2 == 0
        else {"code": 3, "level": "warn", "type": ["PartialParsing", [{"path": p}]], "path": p, "message": "m"} for i, p in enumerate(names[:25])]
json.dump({"results": [], "errors": errs, "paths": {"scanned": names}}, open(sys.argv[1], "w"))
PY
commit
sg "$(cat "$T/cap.json")"
t "cap: not voided (no NOT RUN)" not errhas 'NOT RUN:.*semgrep'
t "cap: listed as ran" ran
t "cap: counts are exact (all 25) and ordered by count" errhas "^$PREFIX \(25 error\(s\) on 25 of 30 scanned file\(s\): Syntax error \(error\) x13, PartialParsing \(warn\) x12; see not-checked rows\)\$"
t "cap: 20 named rows" nrows '.rule=="not-checked" and .file!="."' 20
t "cap: ...the first 20 paths in order" jq -e '[.[] | select(.tool=="semgrep" and .file!=".") | .file] == [range(20) | "f/\(. | tostring | if length < 2 then "0" + . else . end).txt"]' "$T/out"
t "cap: the 21st path has no row" not row f/20.txt not-checked
t "cap: one summary row for the rest, path ., naming the first path left out" jq -e 'any(.[]; .tool=="semgrep" and .rule=="not-checked" and .file=="." and .line==0 and .message=="semgrep could not fully read 5 more file(s) (25 with errors in this chunk; the first 20 in path order are listed, the rest start at f/20.txt); rules may have missed part of them")' "$T/out"
t "cap: 21 semgrep rows in all" nrows 'true' 21

# --- chunks: 230 files make two semgrep calls (200 + 30). Each call has 25 errored files and no findings, so both report the same
# error counts: their summary rows were identical, and the closing dedup of identical not-checked rows merged them into one (the JSON undercounted)
newrepo chunks; mkdir f
python3 - "$T" <<'PY'
import json, sys
names = [f"f/{i:03d}.txt" for i in range(230)]
for p in names: open(p, "w").write("x\n")
for k, scanned in enumerate((names[:200], names[200:]), 1):
    errs = [{"code": 3, "level": "error", "type": "Syntax error", "path": p, "message": "m"} for p in scanned[:25]]
    json.dump({"results": [], "errors": errs, "paths": {"scanned": scanned}}, open(f"{sys.argv[1]}/c{k}.json", "w"))
PY
commit
sg "$(cat "$T/c1.json")" "$(cat "$T/c2.json")"
t "chunks: not voided (no NOT RUN)" not errhas 'NOT RUN:.*semgrep'
t "chunks: 40 named rows (20 per chunk)" nrows '.rule=="not-checked" and .file!="."' 40
t "chunks: two summary rows, one per chunk" nrows '.rule=="not-checked" and .file=="."' 2
t "chunks: ...each names the first path its chunk left out" jq -e '[.[] | select(.tool=="semgrep" and .file==".") | .message | capture("the rest start at (?<p>[^)]+)\\)").p] == ["f/020.txt", "f/220.txt"]' "$T/out"
t "chunks: two partial lines, one per chunk" errcount "^$PREFIX" 2
t "chunks: ...the first scanned 200 files" errcount "^$PREFIX \(25 error\(s\) on 25 of 200 scanned file\(s\): Syntax error \(error\) x25; see not-checked rows\)\$" 1
t "chunks: ...the second scanned 30" errcount "^$PREFIX \(25 error\(s\) on 25 of 30 scanned file\(s\): Syntax error \(error\) x25; see not-checked rows\)\$" 1

# --- summary: "N findings" counts the rows that are not not-checked; the not-checked rows get a line of their own, only when there are any
newrepo summ; mkdir src; for f in a b c; do echo 'echo hi' >"src/$f.sh"; done; commit
sg '{"results":[{"check_id":"acme.shell.eval-input","path":"src/b.sh","start":{"line":2},"extra":{"message":"eval of input"}}],
 "errors":[{"code":3,"level":"warn","type":"Syntax error","path":"src/a.sh","message":"m"}],
 "paths":{"scanned":["src/a.sh","src/b.sh","src/c.sh"]}}'
nck=$(jq '[.[] | select(.rule=="not-checked")] | length' "$T/out"); nf=$(jq '[.[] | select(.rule!="not-checked")] | length' "$T/out")
t "summary: the run has a finding (else the count check proves nothing)" test "$nf" -gt 0
t "summary: ...and a not-checked row" test "$nck" -gt 0
t "summary: N findings leaves the not-checked rows out" errcount "^review_checks: $nf findings; " 1
t "summary: the not-checked rows are counted on their own line" errcount "^review_checks: $nck not-checked row\\(s\\) " 1
newrepo none
sg '{"results":[],"paths":{"scanned":[]}}'
t "summary: nothing scanned reads 0 findings" errhas '^review_checks: 0 findings; '
t "summary: ...with no not-checked line" not errhas 'not-checked row\(s\)'

# --- same file: errors on one file are one row listing each distinct type and level; a path-less error is counted but never rowed
newrepo same; mkdir src; for f in a b c; do echo 'echo hi' >"src/$f.sh"; done; commit
sg '{"results":[{"check_id":"acme.shell.eval-input","path":"src/b.sh","start":{"line":2},"extra":{"message":"eval of input"}}],
 "errors":[{"code":3,"level":"warn","type":["PartialParsing",[]],"path":"src/a.sh","message":"m"},
           {"code":3,"level":"warn","type":["PartialParsing",[]],"path":"src/a.sh","message":"m"},
           {"code":2,"level":"error","type":"Syntax error","path":"src/a.sh","message":"m"},
           {"code":4,"level":"warn","type":"Timeout","message":"no path"}],
 "paths":{"scanned":["src/a.sh","src/b.sh","src/c.sh"]}}'
t "same file: counts cover all 4 errors on 1 of 3 files, ties by name" errhas "^$PREFIX \(4 error\(s\) on 1 of 3 scanned file\(s\): PartialParsing \(warn\) x2, Syntax error \(error\) x1, Timeout \(warn\) x1; see not-checked rows\)\$"
t "same file: one row for src/a.sh with each distinct type and level" jq -e 'any(.[]; .tool=="semgrep" and .file=="src/a.sh" and .rule=="not-checked" and .message=="semgrep could not fully read this file (PartialParsing, warn; Syntax error, error); rules may have missed part of it")' "$T/out"
t "same file: ...the only not-checked row (the path-less error has none)" nrows '.rule=="not-checked"' 1
t "same file: finding kept" row src/b.sh acme.shell.eval-input
sg '{"results":[{"check_id":"acme.shell.eval-input","path":"src/b.sh","start":{"line":2},"extra":{"message":"eval of input"}}],
 "errors":[{"code":4,"level":"warn","type":"Timeout","message":"slow rule"}],
 "paths":{"scanned":["src/a.sh","src/b.sh","src/c.sh"]}}'
t "path-less only: counted on the partial line, with no pointer to rows" errhas "^$PREFIX \(1 error\(s\) on 0 of 3 scanned file\(s\): Timeout \(warn\) x1\)\$"
t "path-less only: no not-checked row" nrows '.rule=="not-checked"' 0
t "path-less only: finding kept and still partial" row src/b.sh acme.shell.eval-input
t "path-less only: ...listed as partial in the closing line" errhas 'partial: semgrep\(errors\)'

# --- every file: the exit-4 case is decided on the findings alone, so a scan with nothing usable stays NOT RUN and names no file
sg '{"results":[],"errors":[{"path":"src/a.sh","level":"warn","type":"Syntax error"},{"path":"src/b.sh","level":"warn","type":"Syntax error"},{"path":"src/c.sh","level":"warn","type":"Syntax error"}],
 "paths":{"scanned":["src/a.sh","src/b.sh","src/c.sh"]}}'
t "every file: NOT RUN" errhas 'NOT RUN:.*semgrep \(scan errored, no findings\)'
t "every file: no partial line" not errhas 'partial: semgrep ran'
t "every file: no row names a file" not jq -e 'any(.[]; .tool=="semgrep" and .file!="")' "$T/out"
sg '{"results":[],"errors":[{"level":"warn","type":"Timeout","message":"no path"}],"paths":{"scanned":["src/a.sh","src/b.sh","src/c.sh"]}}'
t "path-less error and no findings: NOT RUN (the unread files are unknown)" errhas 'NOT RUN:.*semgrep \(scan errored, no findings\)'
t "path-less error and no findings: no row names a file" not jq -e 'any(.[]; .tool=="semgrep" and .file!="")' "$T/out"

# --- shapes: nothing in the errors list may make the reader fail (that voids the chunk's findings as "unparseable output")
sg '{"results":[{"check_id":"acme.shell.eval-input","path":"src/a.sh","start":{"line":3},"extra":{"message":"eval of input"}}],
 "errors":[null,"boom",{"message":"no type or level"},{"type":[],"level":null,"path":"src/b.sh"},
           {"type":"Syntax error","level":"error","path":["src","c.sh"]},{"type":"Lexical error","level":"info","path":"src/acme\rtool.sh"}],
 "paths":{"scanned":["src/a.sh","src/b.sh","src/c.sh","src/acme\rtool.sh"]}}'
t "shapes: no unparseable output" not errhas 'unparseable output'
t "shapes: finding kept" row src/a.sh acme.shell.eval-input
t "shapes: counts name a missing type and level as unknown" errhas "^$PREFIX \(6 error\(s\) on 2 of 4 scanned file\(s\): unknown \(unknown\) x4, Lexical error \(info\) x1, Syntax error \(error\) x1; see not-checked rows\)\$"
t "shapes: a missing type and level in a row say unknown" jq -e 'any(.[]; .tool=="semgrep" and .file=="src/b.sh" and .rule=="not-checked" and (.message|test("\\(unknown, unknown\\)")))' "$T/out"
t "shapes: a control character in a path becomes ?, the row is kept" jq -e 'any(.[]; .tool=="semgrep" and .file=="src/acme?tool.sh" and .rule=="not-checked" and (.message|test("\\(Lexical error, info\\)")))' "$T/out"
t "shapes: a path that is not a string is counted, not rowed" nrows '.rule=="not-checked"' 2
echo "Tests: $((n - fail))/$n"
[ "$fail" = 0 ]
