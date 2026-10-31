#!/usr/bin/env bash
# review_checks.sh marks each diff-mode row "new": true when its file+line is on a line BASE...HEAD adds, false for a pre-existing
# line (also one shifted down, or in a renamed file) and for a file-level (line 0) row, and null in a file whose working copy differs
# from HEAD (an edit, staged or not, or an untracked file: most rows read the working tree, the diff reads commits); --full and --history
# omit the key, as does a failed working-tree listing (which says so on stderr); no row is dropped. A fake shellcheck on a hermetic PATH
# reports one row per FIXME line, and a fake tsc one row per file it is told to blame (a project-wide analyzer, so it can name a file
# outside the diff), so the same rows come out on any host.
# The repo carries hostile git config (no rename detection, no prefixes, merged hunks, forced colour, an external diff, a textconv
# that drops a line, status hiding untracked files): the script must pin its own git flags.
# REVIEW_CHECKS overrides the script under test (to prove the cases fail on the old one).
set -uo pipefail  # no -e: a failed jq must reach chk, which prints the FAIL line
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RC="${REVIEW_CHECKS:-$ROOT/.claude/skills/deep-code-review/scripts/review_checks.sh}"
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-newrows.XXXXXX"); trap 'rm -rf "$T"' EXIT
pass=0 total=0
chk() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
g() { git -c user.email=t@example.com -c user.name=t "$@"; }
mkdir "$T/bin" "$T/sys" "$T/repo"
for b in bash env git grep sed head tail cat rm mkdir mktemp dirname basename python3 perl timeout gtimeout jq true sort uniq paste tr cut wc awk date cp mv ls find touch tee readlink sleep; do
  p=$(type -P "$b") && ln -s "$p" "$T/sys/$b"  # system binaries only: a scanner installed on the host cannot add rows
done
cat >"$T/bin/shellcheck" <<'STUB'
#!/usr/bin/env bash
f=${!#}
grep -an FIXME "$f" | while IFS=: read -r n _; do echo "$f:$n:1: warning: fixme [SC9001]"; done
if grep -aq ZERO "$f"; then echo "$f:0:1: warning: file level [SC9002]"; fi
exit 0
STUB
chmod +x "$T/bin/shellcheck"
cd "$T/repo" && g init -q -b main .
git config diff.renames false; git config diff.noprefix true; git config diff.interHunkContext 8; git config color.ui always
git config status.showUntrackedFiles no; git config diff.external echo; git config diff.skip1.textconv 'sed 1d'; echo '*.sh diff=skip1' >.gitattributes
printf 'echo one\necho FIXME old\necho three\necho four\n' >a.sh
printf 'echo 1\necho FIXME renamed\necho 3\necho 4\necho 5\necho 6\n' >ren.sh
printf 'echo FIXME pure\necho 2\n' >pure.sh
g add -A; g commit -q -m base; g branch base
g checkout -q -b feat
printf 'echo one\necho FIXME added\necho FIXME old\necho three\necho FIXME added too\necho four\n' >a.sh  # two hunks with a pre-existing line between them
g mv ren.sh moved.sh; printf 'echo FIXME new\n' >>moved.sh
g mv pure.sh pure2.sh
printf 'echo hi\necho FIXME ZERO\n' >fresh.sh
printf 'echo FIXME\n' >"sp ace.sh"
printf 'echo a\necho FIXME\0\n' >nul.sh  # a NUL byte makes git call the file binary unless diffed with -a
g add -A; g commit -q -m feat
run() { PATH="$T/bin:$T/sys" DCR_USER_BIN= bash "$RC" --base base "$@" 2>"$T/err" >"$T/out"; }
row() { jq -e --arg f "$1" --argjson l "$2" --argjson n "$3" --arg t "${4:-shellcheck}" 'any(.[]; .tool == $t and .file == $f and .line == $l and has("new") and .new == $n)' "$T/out" >/dev/null; }
nul() { jq -e --arg f "$1" '[.[] | select(.file == $f)] | length > 0 and all(.[]; has("new") and .new == null)' "$T/out" >/dev/null; }  # file has rows, every one null
run
row a.sh 2 true; chk $? "edited file: the added line is new"
row a.sh 3 false; chk $? "edited file: a pre-existing finding shifted down, between two hunks, is not new and its row is kept"
row a.sh 5 true; chk $? "edited file: the second hunk's added line is new"
row moved.sh 2 false; chk $? "renamed and edited file: a pre-existing line is not new"
row moved.sh 7 true; chk $? "renamed and edited file: the added line is new"
row pure2.sh 1 false; chk $? "pure rename: not new"
row fresh.sh 2 true; chk $? "new file: its line is new"
row fresh.sh 0 false; chk $? "file-level row (line 0) is false even in a new file"
row "sp ace.sh" 1 true; chk $? "path with a space"
row nul.sh 2 true; chk $? "text file with a NUL byte still has its added lines"
jq -e 'length > 0 and all(.[]; .new | type == "boolean")' "$T/out" >/dev/null; chk $? "every row carries a boolean new"
n=$(jq '[.[] | select(.new)] | length' "$T/out"); m=$(jq length "$T/out")
grep -qxF "review_checks: $n of $m rows are on lines this diff adds" "$T/err"; chk $? "stderr: $n of $m rows are on lines this diff adds"
for mode in --full --history; do
  run "$mode"
  jq -e 'length > 0 and all(.[]; has("new") | not)' "$T/out" >/dev/null; chk $? "$mode: rows have no new key"
  ! grep -q 'rows are on lines this diff adds' "$T/err"; chk $? "$mode: no count line"
done
# Uncommitted edits: most rows read the working tree, the diff reads commits, so a file whose working copy differs from HEAD gets null,
# never a wrong true or false; a clean file keeps its flag, one the diff does not touch included.
printf 'echo ok\n' >app.ts; echo '{}' >tsconfig.json; g add app.ts tsconfig.json; g commit -q -m ts  # a changed .ts plus a tsconfig make tsc run
cat >"$T/bin/tsc" <<'STUB'
#!/usr/bin/env bash
echo "loose.ts(1,1): error TS9001: in an untracked file"
echo ".gitattributes(1,1): error TS9002: in a tracked file the diff does not touch"
exit 0
STUB
chmod +x "$T/bin/tsc"
{ echo 'echo hdr'; cat a.sh; } >a.sh.new && mv a.sh.new a.sh  # unstaged edit: every line moves down one
printf 'echo FIXME ZERO\n' >>"sp ace.sh"; g add "sp ace.sh"  # staged edit; adds a file-level row too
echo x >loose.ts  # untracked
run
nul a.sh; chk $? "unstaged edit: every row in the file is null"
nul "sp ace.sh"; chk $? "staged edit, path with a space: every row is null, the file-level one too"
row loose.ts 1 null tsc; chk $? "untracked file: its row is null"
row .gitattributes 1 false tsc; chk $? "clean tracked file the diff does not touch: still false"
row moved.sh 7 true; chk $? "clean edited file: an added line is still true"
row moved.sh 2 false; chk $? "clean edited file: a pre-existing line is still false"
row fresh.sh 2 true; chk $? "clean new file: its line is still true"
row fresh.sh 0 false; chk $? "clean new file: its file-level row is still false"
jq -e 'length > 0 and all(.[]; has("new") and (.new == null or (.new | type == "boolean")))' "$T/out" >/dev/null; chk $? "every row carries true, false or null"
n=$(jq '[.[] | select(.new == true)] | length' "$T/out"); k=$(jq '[.[] | select(.new == null)] | length' "$T/out"); m=$(jq length "$T/out")
[ "$k" -eq 7 ]; chk $? "exactly the 7 rows of the three uncommitted files are null, no clean row is (got $k)"
grep -qxF "review_checks: $n of $m rows are on lines this diff adds, $k unknown (file differs from HEAD)" "$T/err"; chk $? "stderr: $n of $m rows are on lines this diff adds, $k unknown (file differs from HEAD)"
# The listing is a read: a file whose mtime changed but whose content did not (so git would refresh its index entry) must not make the run rewrite .git/index.
touch moved.sh; i=$(ls -i .git/index); run; [ "$(ls -i .git/index)" = "$i" ]; chk $? "the run leaves .git/index alone even when a tracked file's mtime changed"
# A root file named HEAD makes a bare `git diff HEAD` fail as ambiguous; the listing names no revision, so the flags survive.
echo hi >HEAD; g add -- HEAD; g commit -q -m 'root file named HEAD' -- HEAD
printf '#!/usr/bin/env bash\necho "HEAD(1,1): error TS9003: in a root file named HEAD"\n' >"$T/bin/tsc"
run
row HEAD 1 true tsc; chk $? "root file named HEAD: its row keeps its flag"
nul a.sh; chk $? "root file named HEAD: a file with uncommitted edits is still null"
# A listing that fails must say so: silence would look like --full. Garbage in .git/index fails the working-tree read, not the commit diff.
echo garbage >.git/index; run
jq -e 'length > 0 and all(.[]; has("new") | not)' "$T/out" >/dev/null; chk $? "unreadable index: rows have no new key"
grep -qxF 'review_checks: could not list files that differ from HEAD; "new" omitted' "$T/err"; chk $? "unreadable index: stderr says why new is missing"
echo "Tests: $pass/$total"; [ "$pass" -eq "$total" ]
