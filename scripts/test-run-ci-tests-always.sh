#!/usr/bin/env bash
# Tests for the always= list of `scripts/run-ci-tests.sh --affected`: the whole-tree gates of CI's cheap job that no ci-test names (so selection
# by name never reaches them) run on every non-empty affected run. Origin: an affected run passed 59/59 while the cheap job failed on a line
# ending in a bare mktemp (scripts/test-mktemp-tmpdir.sh). Hermetic temp-repo fixtures, offline. Prints PASS/FAIL per case and "Tests: P/N".
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-always.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR BASE_SHA RUN_CI_BASE
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }

# the list under test, read from the real runner
ALWAYS="$(sed -n "s/^  always='\(.*\)'\$/\1/p" "$ROOT/scripts/run-ci-tests.sh")"
[ -n "$ALWAYS" ] && [ "$(printf '%s\n' "$ALWAYS" | wc -l | tr -d ' ')" -eq 1 ]
ok $? "runner defines one non-empty always= list"
case " $ALWAYS " in *" scripts/test-mktemp-tmpdir.sh "*) c=0 ;; *) c=1 ;; esac
ok $c "the list holds scripts/test-mktemp-tmpdir.sh (the gate the missed failure came from)"
cheap="$(awk '/^  cheap:/{f=1; next} f && /^  [A-Za-z0-9_-]+:/{exit} f' "$ROOT/.github/workflows/ci.yml")"
miss=; for t in $ALWAYS; do [ -f "$ROOT/$t" ] && grep -qF "$t" <<<"$cheap" || miss="$miss $t"; done
[ -n "$ALWAYS" ] && [ -n "$cheap" ] && [ -z "$miss" ]
ok $? "every always entry exists and is run by the cheap job of ci.yml${miss:+ (not:$miss)}"

n="$(printf '%s\n' $ALWAYS | wc -l | tr -d ' ')"
EXP="$(printf '%s\n' $ALWAYS | sort -u | tr '\n' ' ')"       # what ran.log holds when only the always entries ran
EXP2="$(printf '%s\n' a $ALWAYS | sort -u | tr '\n' ' ')"    # ... and when ci-test a ran beside them
PY="$(printf '%s\n' $ALWAYS | grep '\.py$' | head -1)"

# ---- fixture 1: stub always entries (each logs its own path to ran.log; a .py runs only if the runner hands it to python3) and one ci-test
R="$WORK/repo"
mkdir -p "$R/scripts/ci-tests.d" "$R/.claude/skills/agentic-delivery/scripts"
cp "$ROOT/scripts/run-ci-tests.sh" "$R/scripts/"
cp "$ROOT/.claude/skills/agentic-delivery/scripts/scrub_env.sh" "$R/.claude/skills/agentic-delivery/scripts/"
echo 'exit 0' >"$R/scripts/ci-gates.sh"; echo '# none' >"$R/.banlist.txt"  # stub privacy gate; the runner fails closed without one
for t in $ALWAYS; do
  mkdir -p "$R/$(dirname "$t")"
  case "$t" in
    *.py) printf '%s\n' "open('ran.log', 'a').write('$t' + chr(10))" >"$R/$t" ;;
    *) printf '%s\n' "echo $t >>ran.log" >"$R/$t" ;;
  esac
done
printf '%s\n' '# covers foo.txt' 'echo a >>ran.log' >"$R/scripts/ci-tests.d/a.sh"
echo 1 >"$R/foo.txt"; echo 1 >"$R/zzz.txt"
git -C "$R" init -q && git -C "$R" add -A && git -C "$R" -c user.email=t@example.com -c user.name=T commit -qm base
BASE="$(git -C "$R" rev-parse HEAD)"

# run [BASE]: fresh ran.log, run the runner with --affected; sets RC, OUT, RAN (sorted names of what ran)
run() {
  rm -f "$R/ran.log"
  OUT="$(cd "$R" && bash scripts/run-ci-tests.sh --affected "$@" 2>&1)"; RC=$?
  RAN="$(sort -u "$R/ran.log" 2>/dev/null | tr '\n' ' ')"
}

echo 2 >"$R/zzz.txt"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "$EXP" ] && grep -q "affected: $n of $((n + 1)) tests" <<<"$OUT" && grep -q 'always→scripts/test-mktemp-tmpdir.sh' <<<"$OUT"
ok $? "a changed file no test names: every always entry runs (a .py under python3), the ci-test does not, and the selection is printed"

rm -f "$R/ran.log"; OUT="$(cd "$R" && bash scripts/run-ci-tests.sh --list-affected "$BASE" 2>&1)"; RC=$?
SEL="$(grep '^selected: ' <<<"$OUT" | sed 's/^selected: //' | sort -u | tr '\n' ' ')"
[ "$RC" -eq 0 ] && [ "$SEL" = "$EXP" ] && [ ! -e "$R/ran.log" ]
ok $? "--list-affected lists every always entry (the receipt claim re-derives it) and runs nothing"

git -C "$R" checkout -q zzz.txt; echo 2 >"$R/foo.txt"; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "$EXP2" ] && [ "$(tail -1 "$R/ran.log")" = a ]
ok $? "a file a ci-test names selects that test; the always entries run beside it, first"

git -C "$R" checkout -q foo.txt; run "$BASE"
[ "$RC" -eq 0 ] && [ -z "$RAN" ] && grep -q 'affected: 0 of .* tests (no changed files' <<<"$OUT"
ok $? "nothing changed: the always entries do not run either"

for t in $ALWAYS; do echo >>"$R/$t"; done; run "$BASE"
[ "$RC" -eq 0 ] && [ "$RAN" = "$EXP" ] && [ "$(wc -l <"$R/ran.log" | tr -d ' ')" -eq "$n" ] && ! grep -q UNCOVERED <<<"$OUT"
ok $? "a changed always gate runs once and is not reported UNCOVERED"

git -C "$R" checkout -q -- .; echo 2 >"$R/zzz.txt"; [ -z "$PY" ] || echo 'raise SystemExit(1)' >>"$R/$PY"; run "$BASE"
[ -n "$PY" ] && [ "$RC" -ne 0 ] && grep -q "run-ci-tests: FAIL $PY" <<<"$OUT"
ok $? "a failing always entry fails the run"

# ---- fixture 2: the real mktemp gate on a tree holding a bare mktemp line no ci-test names (the missed failure)
R="$WORK/repo2"
mkdir -p "$R/scripts/ci-tests.d" "$R/.claude/skills/agentic-delivery/scripts"
cp "$ROOT/scripts/run-ci-tests.sh" "$ROOT/scripts/test-mktemp-tmpdir.sh" "$R/scripts/"
cp "$ROOT/.claude/skills/agentic-delivery/scripts/scrub_env.sh" "$R/.claude/skills/agentic-delivery/scripts/"
cp "$WORK/repo/scripts/ci-gates.sh" "$R/scripts/"; echo '# none' >"$R/.banlist.txt"
printf '%s\n' '# covers planted.sh' 'echo x >>ran.log' >"$R/scripts/ci-tests.d/x.sh"  # a ci-test the planted file selects
git -C "$R" init -q && git -C "$R" add -A && git -C "$R" -c user.email=t@example.com -c user.name=T commit -qm base
BASE="$(git -C "$R" rev-parse HEAD)"

printf 'd=$(%s -d)\n' "mktemp" >"$R/scripts/planted.sh"; run "$BASE"
[ "$RC" -ne 0 ] && grep -q 'FAIL bare mktemp' <<<"$OUT" && grep -q 'run-ci-tests: FAIL scripts/test-mktemp-tmpdir.sh' <<<"$OUT"
ok $? "a bare mktemp line in a file no ci-test names fails the affected run"
[ -z "$RAN" ] && grep -q 'x.sh' <<<"$OUT" && ! grep -q '^== scripts/ci-tests.d/x.sh' <<<"$OUT"
ok $? "the failure comes first: the selected ci-test never starts (fail-fast)"

rm "$R/scripts/planted.sh"; echo 2 >"$R/note.txt"; run "$BASE"
[ "$RC" -eq 0 ] && grep -q 'ok   no bare mktemp in shipped scripts' <<<"$OUT"
ok $? "the same tree without that line passes"

echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
