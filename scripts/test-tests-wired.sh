#!/usr/bin/env bash
# Tests for `ci-gates.sh tests-wired` (#1592): a test that no CI step runs fails the gate, and the allowlist row that excuses one
# needs a reason. Hermetic: each case builds a throwaway fixture root under $TMPDIR (no repo state, no network).
# Prints PASS/FAIL per case and a final "Tests: P/N"; exits non-zero on any failure.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-wired.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT
GATE="$ROOT/scripts/ci-gates.sh"
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }

# mk <case>: a fixture root where test_a.py is run by a ci-tests.d registration and test-b.sh by a workflow step
mk() {
  R="$WORK/$1"; mkdir -p "$R/scripts/ci-tests.d" "$R/.github/workflows"
  : >"$R/scripts/test_a.py"; : >"$R/scripts/test-b.sh"; : >"$R/allow.tsv"
  echo 'python3 scripts/test_a.py' >"$R/scripts/ci-tests.d/a.sh"
  printf '      - run: bash scripts/test-b.sh\n' >"$R/.github/workflows/ci.yml"
}
LOC=""  # extra `env` words for the gate runs that follow; the collation cases at the end set it
# shellcheck disable=SC2086  # $LOC is meant to split into env assignments
gate() { out="$(env $LOC bash "$GATE" tests-wired --allowlist "${1:-$R/allow.tsv}" "$R" 2>&1)"; rc=$?; }
passes() { [ "$rc" -eq 0 ] && grep -qF -- "$1" <<<"$out"; ok $? "$2"; }   # <expected output substring> <label>
fails() { [ "$rc" -eq 1 ] && grep -qF -- "$1" <<<"$out"; ok $? "$2"; }    # exit 1 (not 2 = no such subcommand) and the output says why

mk clean; gate
passes "tests-wired: ok (2 tests: 2 run by CI, 0 allowlisted)" "every test named by a registration or a workflow passes"

mk orphan; : >"$R/scripts/test_orphan.py"; gate
fails "scripts/test_orphan.py is run by no CI step" "planted orphan test fails the gate and is named"

mk comment; : >"$R/scripts/test_c.py"
printf '# python3 scripts/test_c.py\npython3 scripts/test_a.py  # test_c.py\n' >>"$R/scripts/ci-tests.d/a.sh"
printf '      # - run: bash scripts/test_c.py\n' >>"$R/.github/workflows/ci.yml"; gate
fails "scripts/test_c.py is run by no CI step" "a name only in a full-line or trailing comment is still an orphan"

mk below; : >"$R/scripts/test_c.py"; echo 'python3 "$ROOT/scripts/test_c.py"' >"$R/scripts/test_a.py"; gate
passes "3 tests: 3 run by CI" "a test named by a test CI runs (one level down, like test-ci-gates.sh) passes"

mk chain; : >"$R/scripts/test_c.py"; : >"$R/scripts/test_d.py"
echo 'python3 scripts/test_d.py' >"$R/scripts/test_c.py"; echo 'python3 scripts/test_c.py' >"$R/scripts/test_a.py"; gate
passes "4 tests: 4 run by CI" "a test named by a test that a run test names (two levels down) passes"

mk deadend; : >"$R/scripts/test_o.py"; : >"$R/scripts/test_c.py"; echo 'python3 scripts/test_c.py' >"$R/scripts/test_o.py"; gate
fails "scripts/test_c.py is run by no CI step" "a test named only by an orphan test is still an orphan"

mk allowed; : >"$R/scripts/test_slow.py"
printf '# header\n\ntest_slow.py\t55 s locally\n' >"$R/allow.tsv"; gate
passes "3 tests: 2 run by CI, 1 allowlisted" "an orphan with an allowlist reason passes (comments and blank lines ignored)"

mk noreason; : >"$R/scripts/test_slow.py"; printf 'test_slow.py\n' >"$R/allow.tsv"; gate
fails "test_slow.py: allowlist row has no reason" "an allowlist row without a tab and reason fails"

mk emptyreason; : >"$R/scripts/test_slow.py"; printf 'test_slow.py\t\n' >"$R/allow.tsv"; gate
fails "test_slow.py: allowlist row has no reason" "an allowlist row with an empty reason fails"

mk gone; printf 'test_nope.py\tit was deleted\n' >"$R/allow.tsv"; gate
fails "test_nope.py: allowlist row names no scripts/test_*.py or scripts/test-*.sh" "a row for a test that does not exist fails"

mk stale; printf 'test_a.py\tslow\n' >"$R/allow.tsv"; gate
fails "test_a.py: allowlisted but CI already runs it" "a row for a test CI already runs fails (the list only shrinks)"

mk noallow; gate "$R/missing.tsv"
fails "allowlist not found" "a missing allowlist file fails closed"

R="$WORK/noreg"; mkdir -p "$R/scripts"; : >"$R/scripts/test_a.py"; : >"$R/allow.tsv"; gate
fails "ci-tests.d not found" "a root with no scripts/ci-tests.d fails closed"

R="$WORK/notests"; mkdir -p "$R/scripts/ci-tests.d"; : >"$R/allow.tsv"; gate
fails "no scripts/test_*.py or scripts/test-*.sh" "a root with no tests fails closed"

out="$(bash "$GATE" tests-wired --bogus 2>&1)"; rc=$?
fails "unknown option" "an unknown option fails"

# The gate sorts in the C locale, so its comm calls must too: en_US.UTF-8 orders `_` and `-` differently, which made comm see
# unsorted input (about 380 false FAILs on the real tree). LC_ALL is forced so an exported LC_COLLATE cannot hide the case.
# A runner without en_US.UTF-8 (a minimal container) prints a SKIP here; every case above still ran.
if [ "$(LC_ALL=en_US.UTF-8 locale charmap 2>/dev/null)" = UTF-8 ]; then
  LOC="LC_ALL=en_US.UTF-8"
  mk allowedloc; : >"$R/scripts/test_slow.py"; printf 'test_slow.py\t55 s locally\n' >"$R/allow.tsv"; gate
  passes "3 tests: 2 run by CI, 1 allowlisted" "an allowlisted orphan passes under en_US.UTF-8 collation"
  mk staleloc; printf 'test_a.py\tslow\n' >"$R/allow.tsv"; gate
  fails "test_a.py: allowlisted but CI already runs it" "a stale row still fails under en_US.UTF-8 collation"
  LOC=""
else
  echo "SKIP  en_US.UTF-8 collation cases: that locale is not installed on this runner"
fi

echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
