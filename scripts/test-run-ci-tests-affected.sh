#!/usr/bin/env bash
# Tests for `scripts/run-ci-tests.sh --affected [BASE]`: on a throwaway git repo, a changed file runs only the ci-tests whose text
# (or a scripts/test-*.sh it invokes, one level) names it as a whole name; also rename/delete/odd names, the test-ci-gates exclusion,
# the reverse-dependency hop, UNCOVERED, no-base and ubiquitous-basename cases. Offline. Prints PASS/FAIL per case and "Tests: P/N".
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-affected.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR BASE_SHA RUN_CI_BASE
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }

R="$WORK/repo"
mkdir -p "$R/scripts/ci-tests.d" "$R/.claude/skills/agentic-delivery/scripts"
cp "$ROOT/scripts/run-ci-tests.sh" "$R/scripts/"
cp "$ROOT/.claude/skills/agentic-delivery/scripts/scrub_env.sh" "$R/.claude/skills/agentic-delivery/scripts/"
printf '%s\n' 'echo "$*" >"$GATES_LOG"' >"$R/scripts/ci-gates.sh"; echo '# none' >"$R/.banlist.txt"  # stub privacy gate (logs its args); the runner fails closed without one
export GATES_LOG="$WORK/gates.log"
# each ci-test appends its name to ran.log; a mentions foo.txt directly, b only through scripts/test-x.sh (which mentions bar.txt)
printf '%s\n' '# covers foo.txt' 'echo a >>ran.log' >"$R/scripts/ci-tests.d/a.sh"
printf '%s\n' 'echo b >>ran.log' 'bash scripts/test-x.sh' >"$R/scripts/ci-tests.d/b.sh"
printf '%s\n' '# exercises bar.txt' 'echo x >>ran.log' >"$R/scripts/test-x.sh"
printf '%s\n' 'echo c >>ran.log' >"$R/scripts/ci-tests.d/c.sh"
echo 1 >"$R/foo.txt"; echo 1 >"$R/bar.txt"; echo 1 >"$R/zzz.txt"
git -C "$R" init -q && git -C "$R" add -A && git -C "$R" -c user.email=t@example.com -c user.name=T commit -qm base
BASE="$(git -C "$R" rev-parse HEAD)"

# run [BASE]: fresh ran.log, run the runner with --affected; sets RC, OUT, RAN (sorted names of the tests that ran)
run() {
  rm -f "$R/ran.log"
  OUT="$(cd "$R" && bash scripts/run-ci-tests.sh --affected "$@" 2>&1)"; RC=$?
  RAN="$(sort -u "$R/ran.log" 2>/dev/null | tr '\n' ' ')"
}

run "$BASE"
[ "$RC" -eq 0 ] && [ -z "$RAN" ] && grep -q 'affected: 0 of 3 tests (no changed files' <<<"$OUT"
ok $? "nothing changed: runs zero tests, says so, exit 0"

echo 2 >"$R/foo.txt"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "a " ] && grep -q 'affected: 1 of 3 tests (selected by: file→test)' <<<"$OUT" && grep -q 'foo.txt→scripts/ci-tests.d/a.sh' <<<"$OUT"
ok $? "changed foo.txt (uncommitted): only the test naming it runs, and the selection is printed"
[ "$(cat "$GATES_LOG")" = "privacy --banlist .banlist.txt -- foo.txt" ]
ok $? "privacy scans only the changed files, not the whole tree"

git -C "$R" checkout -q foo.txt; echo 2 >"$R/bar.txt"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "b x " ] && grep -q 'bar.txt→scripts/ci-tests.d/b.sh' <<<"$OUT"
ok $? "changed bar.txt: ci-test selected through the scripts/test-*.sh it invokes (one level)"

git -C "$R" checkout -q bar.txt; echo 2 >"$R/zzz.txt"; run "$BASE"
[ "$RC" -eq 0 ] && [ -z "$RAN" ] && grep -q 'affected: 0 of 3 tests' <<<"$OUT"
ok $? "changed file no test names: zero tests run, exit 0"

git -C "$R" checkout -q zzz.txt; echo new >"$R/new-file.md"; printf '%s\n' '# covers new-file.md' 'echo c >>ran.log' >"$R/scripts/ci-tests.d/c.sh"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "c " ]
ok $? "untracked file and an edited ci-test itself are selected"

git -C "$R" add -A && git -C "$R" -c user.email=t@example.com -c user.name=T commit -qm more; echo 3 >"$R/foo.txt"
printf '%s\n' '# covers foo.txt' 'echo a >>ran.log' 'false' >"$R/scripts/ci-tests.d/a.sh"; run "$BASE"
[ "$RC" -ne 0 ] && grep -q 'run-ci-tests: FAIL scripts/ci-tests.d/a.sh' <<<"$OUT"
ok $? "a failing selected test fails the run (no pipe masking)"

run "no-such-base"
[ "$RC" -ne 0 ] && [ -z "$RAN" ] && grep -q 'is not a commit' <<<"$OUT"
ok $? "unresolvable explicit BASE fails closed"

# ---- second fixture: hop, exclusion, odd names, ubiquitous basenames, no base
R="$WORK/repo2"; mkdir -p "$R/scripts/ci-tests.d" "$R/.claude/skills/agentic-delivery/scripts" "$R/docs"
cp "$ROOT/scripts/run-ci-tests.sh" "$R/scripts/"
cp "$ROOT/.claude/skills/agentic-delivery/scripts/scrub_env.sh" "$R/.claude/skills/agentic-delivery/scripts/"
cp "$WORK/repo/scripts/ci-gates.sh" "$R/scripts/"; echo '# none' >"$R/.banlist.txt"
mk() { printf '%s\n' "# $2" "echo $1 >>ran.log" >"$R/scripts/ci-tests.d/$1.sh"; }  # mk NAME TEXT: ci-test NAME whose text is TEXT
mk a 'covers foo.txt'; mk c 'covers foo2.txt'; mk d 'covers é ü.txt'; mk e 'runs scripts/hook.py'; mk f 'mentions SKILL.md'
mk g 'covers docs/SKILL.md'; mk h 'rebar.txt bar.txt.bak'; mk i 'covers fooc.txt'; mk j 'runs scripts/test-j.sh'; echo 'echo j >>ran.log' >"$R/scripts/test-j.sh"
printf '%s\n' 'import helper' >"$R/scripts/hook.py"; echo x >"$R/scripts/helper.py"; echo x >"$R/scripts/orphan.py"
printf '%s\n' '# covers foo.txt' 'echo gates >>ran.log' >"$R/scripts/test-ci-gates.sh"
echo 1 >"$R/foo.txt"; echo 1 >"$R/bar.txt"; echo 1 >"$R/docs/SKILL.md"; mkdir "$R/dir with space"; echo 1 >"$R/dir with space/é ü.txt"
git -C "$R" init -q && git -C "$R" add -A && git -C "$R" -c user.email=t@example.com -c user.name=T commit -qm base
BASE="$(git -C "$R" rev-parse HEAD)"
reset() { git -C "$R" reset -q --hard "$BASE"; git -C "$R" clean -qffd; rm -f "$GATES_LOG"; }

git -C "$R" mv foo.txt foo2.txt; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "a c " ]
ok $? "rename: both the old (deleted) and the new name select their tests"
reset; rm "$R/foo.txt"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "a " ] && [ ! -e "$GATES_LOG" ]
ok $? "delete: a deleted file still selects the test naming it, and is not handed to the privacy scan"
reset; echo 2 >"$R/dir with space/é ü.txt"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "d " ] && [ "$(cat "$GATES_LOG")" = "privacy --banlist .banlist.txt -- dir with space/é ü.txt" ]
ok $? "space + non-ASCII name: unquoted path selects its test and reaches the privacy scan intact"
reset; echo 2 >"$R/foo.txt"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "a " ] && grep -q 'test-ci-gates: left to CI' <<<"$OUT" && ! grep -q 'gates$' "$R/ran.log"
ok $? "test-ci-gates.sh is left to CI when only a file it names changed"
reset; echo '# edit' >>"$R/scripts/ci-gates.sh"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "gates " ] && ! grep -q 'left to CI' <<<"$OUT" && [ "$(cat "$GATES_LOG")" = "privacy --banlist .banlist.txt -- ." ]
ok $? "ci-gates.sh changed: test-ci-gates.sh runs and privacy scans the whole tree"
reset; echo '# edit' >>"$R/.banlist.txt"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$(cat "$GATES_LOG")" = "privacy --banlist .banlist.txt -- ." ]
ok $? "banlist changed: privacy scans the whole tree"
reset; echo 2 >"$R/scripts/helper.py"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "e " ] && grep -q 'helper.py→hook.py→scripts/ci-tests.d/e.sh' <<<"$OUT" && ! grep -q UNCOVERED <<<"$OUT"
ok $? "reverse-dep hop: helper.py (imported by hook.py) selects the test naming hook.py"
reset; echo 2 >"$R/scripts/orphan.py"; run "$BASE"
[ "$RC" -eq 0 ] && [ -z "$RAN" ] && grep -qxF 'UNCOVERED: scripts/orphan.py (no test names it; CI only)' <<<"$OUT"
ok $? "UNCOVERED: a changed script no test or dependent names is reported, exit 0"
reset; echo '# edit' >>"$R/scripts/test-j.sh"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "j " ] && ! grep -q UNCOVERED <<<"$OUT"
ok $? "a changed scripts/test-*.sh is covered by the ci-test that invokes it (not UNCOVERED)"
reset; echo '# edit' >>"$R/scripts/ci-tests.d/a.sh"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "a " ] && ! grep -q UNCOVERED <<<"$OUT"
ok $? "a changed ci-test selects itself and is not UNCOVERED"
reset; echo 2 >"$R/docs/SKILL.md"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "g " ]
ok $? "ubiquitous basename: only the test naming the repo-relative path runs (not the one naming SKILL.md)"
reset; echo 2 >"$R/bar.txt"; run "$BASE"
[ "$RC" -eq 0 ] && [ -z "$RAN" ]
ok $? "boundary match: rebar.txt and bar.txt.bak do not select a change to bar.txt"
reset; echo 2 >"$R/foo.txt"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "a " ]
ok $? "boundary match: foo.txt does not select the test naming fooc.txt"
reset; mkdir "$R/sub" && git -C "$R/sub" init -q && git -C "$R/sub" -c user.email=t@example.com -c user.name=T commit -q --allow-empty -m x; run "$BASE"
[ "$RC" -ne 0 ] && [ -z "$RAN" ] && grep -q 'neither file, symlink nor deleted' <<<"$OUT"
ok $? "a changed path that is not a file, symlink or deletion fails closed"
reset; echo 2 >"$R/foo.txt"; BASE_SHA="$BASE" run
[ "$RC" -eq 0 ] && [ "$RAN" = "a " ]
ok $? "no BASE arg: the hook's BASE_SHA is the base"
reset; echo 2 >"$R/foo.txt"; run
[ "$RC" -eq 0 ] && [ -z "$RAN" ] && grep -qxF 'affected: NOT RUN (no base)' <<<"$OUT" && [ ! -e "$GATES_LOG" ]
ok $? "no base at all (no arg, env or origin/main): NOT RUN, exit 0, nothing runs"

hook="$(cat "$ROOT/.githooks/pre-push")"
grep -qF 'DCR_PREPUSH_CMD="${DCR_PREPUSH_CMD:-bash scripts/run-ci-tests.sh --affected}"' <<<"$hook"
ok $? "pre-push default DCR_PREPUSH_CMD is the --affected runner, env override kept"

echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
