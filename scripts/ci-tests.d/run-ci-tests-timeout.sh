# Tests for the per-test wall-clock bound of scripts/run-ci-tests.sh (PERUN_TEST_TIMEOUT_S): a test that outlives it is killed and the run fails within
# seconds with a "timed out after Ns" line; the process killed is the test itself, not just the env scrubber around it; a missing, non-numeric or
# non-positive value means 900. Hermetic temp-repo fixtures, offline. Prints PASS/FAIL per case and "Tests: P/N".
set +e  # the runner starts a ci-tests.d file with bash -e; the cases below read $? themselves
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-timeout.XXXXXX")" || exit 1
trap 'find "$WORK" -depth -delete' EXIT
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR BASE_SHA RUN_CI_BASE PERUN_TEST_TIMEOUT_S
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_CEILING_DIRECTORIES="$WORK" PIDF="$WORK/pid" PROBE="$WORK/seen"
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }

# fix NAME LINE...: a fixture repo $WORK/NAME with the real runner and env scrubber, a stub privacy gate and one ci-test made of the LINEs
fix() {
  local d="$WORK/$1"; shift
  mkdir -p "$d/scripts/ci-tests.d" "$d/.claude/skills/agentic-delivery/scripts"
  cp "$ROOT/scripts/run-ci-tests.sh" "$d/scripts/"
  cp "$ROOT/.claude/skills/agentic-delivery/scripts/scrub_env.sh" "$d/.claude/skills/agentic-delivery/scripts/"
  echo 'exit 0' >"$d/scripts/ci-gates.sh"; echo '# none' >"$d/.banlist.txt"  # the runner fails closed without a privacy gate
  printf '%s\n' "$@" >"$d/scripts/ci-tests.d/t.sh"
}
# run NAME [SECS]: the fixture's runner with PERUN_TEST_TIMEOUT_S=SECS (unset when SECS is absent); sets RC, output in $WORK/out
run() {
  ( cd "$WORK/$1" && if [ "$#" -ge 2 ]; then export PERUN_TEST_TIMEOUT_S="$2"; fi; bash scripts/run-ci-tests.sh ) >"$WORK/out" 2>&1; RC=$?
}

# a test that sleeps far past a 2 s bound (exec: the sleep is the test's own process)
fix slow 'echo $$ >"$PIDF"' 'exec sleep 30'
s=$SECONDS; run slow 2; took=$((SECONDS - s))
[ "$RC" -ne 0 ] && [ "$took" -lt 10 ] && grep -qF 'run-ci-tests: FAIL scripts/ci-tests.d/t.sh (timed out after 2s)' "$WORK/out"
ok $? "a 30 s test under PERUN_TEST_TIMEOUT_S=2 fails with the timed-out line in ${took}s"
pid="$(cat "$PIDF" 2>/dev/null)"
[ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; gone=$?
ok "$gone" "the timed-out test's own process is gone (the alarm is armed in the test, not in the env scrubber around it)"
[ "$gone" -ne 0 ] && kill -0 "$pid" 2>/dev/null && kill "$pid" 2>/dev/null  # an alarm that missed it must not leave a sleeper behind

fix bad 'exit 3'
run bad 2
[ "$RC" -ne 0 ] && grep -qF 'run-ci-tests: FAIL scripts/ci-tests.d/t.sh' "$WORK/out" && ! grep -q 'timed out' "$WORK/out"
ok $? "an ordinary failure still fails without a timed-out line"

# the armed alarm, read from inside the test (an exec'd perl keeps the test's own alarm and prints what is left of it)
fix probe 'exec perl -e "print alarm(0)" >"$PROBE"'
for v in unset '' abc 0 -5 1.5 12345678901 7 007; do
  want=900; case "$v" in 7|007) want=7 ;; esac
  rm -f "$PROBE"
  if [ "$v" = unset ]; then run probe; else run probe "$v"; fi
  got="$(cat "$PROBE" 2>/dev/null)"
  [ "$RC" -eq 0 ] && [ "$got" -le "$want" ] && [ "$got" -ge $((want - 5)) ]
  ok $? "PERUN_TEST_TIMEOUT_S=${v:-<empty>} arms the test's alarm at ${want}s (it saw ${got:-nothing})"
done

echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
