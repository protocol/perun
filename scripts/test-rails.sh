#!/usr/bin/env bash
# Tests for `ci-gates.sh rails` (#1592): every guard/hook script carries `# rail: owner=..., why=..., review=YYYY-MM-DD`; a missing
# or empty field or a bad date fails the gate, and a review date in the past shows only in --audit. Hermetic: each case builds a
# throwaway fixture root under $TMPDIR (no repo state, no network). Prints PASS/FAIL per case and a final "Tests: P/N"; exits
# non-zero on any failure. Run against a ci-gates.sh without the subcommand, every case fails (exit 2, no such subcommand).
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-rails.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT
GATE="$ROOT/scripts/ci-gates.sh"
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }

FUTURE="2999-12-31"  # a review date no clock reaches, so the audit cases never rot
# rail <file> [line 2]: a script whose second line is the given header (default: a valid one); "" writes no header
rail() { printf '#!/usr/bin/env python3\n%s\n"""doc."""\n' "${2-# rail: owner=demo, why=test rail, review=$FUTURE}" >"$1"; }
# mk <case>: a fixture root with a rail named like one (a_guard.py), a rail a hook template wires (wired.py) and a plain helper
mk() {
  R="$WORK/$1"; S="$R/.claude/skills/demo"; mkdir -p "$S/scripts" "$S/templates"
  rail "$S/scripts/a_guard.py"; rail "$S/scripts/wired.py"; printf '#!/usr/bin/env python3\n"""helper."""\n' >"$S/scripts/helper.py"
  # shellcheck disable=SC2016  # a JSON literal: $CLAUDE_PROJECT_DIR must reach the file unexpanded
  printf '%s\n' '{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"python3 \"$CLAUDE_PROJECT_DIR/.claude/skills/demo/scripts/wired.py\" --x"},{"type":"command","command":"python3 ghost.py"}]}]}}' >"$S/templates/demo.settings.json"
}
gate() { out="$(bash "$GATE" rails "$@" 2>&1)"; rc=$?; }
passes() { [ "$rc" -eq 0 ] && grep -qF -- "$1" <<<"$out"; ok $? "$2"; }   # <expected output substring> <label>
fails() { [ "$rc" -eq 1 ] && grep -qF -- "$1" <<<"$out"; ok $? "$2"; }    # exit 1 (not 2 = no such subcommand) and the output says why

mk clean; gate "$R"
passes "rails: ok (2 rails)" "a name-pattern rail and a template-wired rail with a header pass; a plain helper and an unresolved template name are ignored"

mk relroot; out="$(cd "$R" && bash "$GATE" rails . 2>&1)"; rc=$?
passes "rails: ok (2 rails)" "a relative root (.) works"

for n in b_gate.py c_cap.py d_hook.sh e_gate.sh f_guard.sh; do
  mk "bare-$n"; rail "$S/scripts/$n" ""; gate "$R"
  fails ".claude/skills/demo/scripts/$n: needs exactly one" "$n without a header fails and is named"
done

mk wired; rail "$S/scripts/wired.py" ""; gate "$R"
fails "scripts/wired.py: needs exactly one" "a script a hook template wires, outside the name pattern, still needs a header"

mk noowner; rail "$S/scripts/a_guard.py" "# rail: why=test rail, review=$FUTURE"; gate "$R"
fails "scripts/a_guard.py: needs exactly one" "a header with no owner field fails"

mk nowhy; rail "$S/scripts/a_guard.py" "# rail: owner=demo, review=$FUTURE"; gate "$R"
fails "scripts/a_guard.py: needs exactly one" "a header with no why field fails"

mk noreview; rail "$S/scripts/a_guard.py" "# rail: owner=demo, why=test rail"; gate "$R"
fails "scripts/a_guard.py: needs exactly one" "a header with no review field fails"

mk emptyowner; rail "$S/scripts/a_guard.py" "# rail: owner=, why=test rail, review=$FUTURE"; gate "$R"
fails "scripts/a_guard.py: owner and why must not be empty" "an empty owner fails"

mk blankowner; rail "$S/scripts/a_guard.py" "# rail: owner=   , why=test rail, review=$FUTURE"; gate "$R"
fails "scripts/a_guard.py: owner and why must not be empty" "a blank owner fails"

mk emptywhy; rail "$S/scripts/a_guard.py" "# rail: owner=demo, why=, review=$FUTURE"; gate "$R"
fails "scripts/a_guard.py: owner and why must not be empty" "an empty why fails"

for d in 2027-13-01 2027-02-30 2027-02-29 2027-00-10 2027-01-00 0000-01-01 27-1-1 2027-1-30 soon 2027-01-30T00:00 20270130 ""; do
  mk bad-date; rail "$S/scripts/a_guard.py" "# rail: owner=demo, why=test rail, review=$d"; gate "$R"
  fails "review='$d' is not a real YYYY-MM-DD date" "review=${d:-<empty>} fails as a bad date"
done

mk leap; rail "$S/scripts/a_guard.py" "# rail: owner=demo, why=test rail, review=2028-02-29"; gate "$R"
passes "rails: ok (2 rails)" "a real leap day passes"

mk line10; { echo '#!/usr/bin/env python3'; for i in 1 2 3 4 5 6 7 8; do echo "# filler $i"; done; echo "# rail: owner=demo, why=test rail, review=$FUTURE"; } >"$S/scripts/a_guard.py"; gate "$R"
passes "rails: ok (2 rails)" "a header on line 10 is seen"

mk line11; { echo '#!/usr/bin/env python3'; for i in 1 2 3 4 5 6 7 8 9; do echo "# filler $i"; done; echo "# rail: owner=demo, why=test rail, review=$FUTURE"; } >"$S/scripts/a_guard.py"; gate "$R"
fails "scripts/a_guard.py: needs exactly one" "a header on line 11 is not seen"

mk twice; rail "$S/scripts/a_guard.py" "# rail: owner=demo, why=test rail, review=$FUTURE
# rail: owner=other, why=second line, review=$FUTURE"; gate "$R"
fails "scripts/a_guard.py: needs exactly one" "two header lines fail (one source of truth)"

mk optin; rail "$S/scripts/helper.py"; gate "$R"
passes "rails: ok (3 rails)" "a script outside the set that carries a header is counted"

mk optinbad; rail "$S/scripts/helper.py" "# rail: owner=demo, why=test rail, review=2027-02-30"; gate "$R"
fails "scripts/helper.py: review='2027-02-30' is not a real YYYY-MM-DD date" "a script outside the set that carries a bad header is checked too"

mk past; rail "$S/scripts/a_guard.py" "# rail: owner=demo, why=test rail, review=2000-01-01"; gate "$R"
{ [ "$rc" -eq 0 ] && grep -qF "rails: ok (2 rails)" <<<"$out" && ! grep -qF "audit" <<<"$out"; }; ok $? "a past review date does not fail the plain gate (no time bomb) and prints no audit"

gate --audit "$R"
{ [ "$rc" -eq 0 ] && grep -qF "rails: audit" <<<"$out" && grep -qF "1 of 2 past their review date" <<<"$out" \
  && grep -qF "scripts/a_guard.py  owner=demo  review=2000-01-01  why=test rail" <<<"$out" && ! grep -qF "scripts/wired.py" <<<"$out"; }
ok $? "--audit lists only the rail past its review date, with owner and why, and exits 0"
{ [ "$rc" -eq 0 ] && grep -qF "this audit never removes a rail" <<<"$out"; }; ok $? "--audit tells the owner to confirm or retire and removes nothing"
{ [ "$rc" -eq 0 ] && grep -qF "firing counts: none" <<<"$out" && ! grep -qiE "never-firing:|never fired" <<<"$out"; }
ok $? "--audit makes no never-firing claim: no firing log is shared, so it says so"
{ [ "$rc" -eq 0 ] && grep -qF "rails: audit" <<<"$out" && [ -f "$S/scripts/a_guard.py" ]; }; ok $? "--audit removed nothing (the expired rail is still there)"

mk current; gate --audit "$R"
{ [ "$rc" -eq 0 ] && grep -qF "0 of 2 past their review date" <<<"$out"; }; ok $? "--audit with every rail current lists none"

mk auditbad; rail "$S/scripts/a_guard.py" "# rail: owner=demo, why=test rail, review=nope"; gate --audit "$R"
fails "review='nope' is not a real YYYY-MM-DD date" "--audit still fails on a malformed header"

R="$WORK/norails"; mkdir -p "$R/.claude/skills/demo/scripts"; printf '#!/usr/bin/env python3\n' >"$R/.claude/skills/demo/scripts/helper.py"; gate "$R"
fails "no guard or hook scripts" "a root with no rail fails closed"

R="$WORK/noskills"; mkdir -p "$R"; gate "$R"
fails ".claude/skills not found (fail closed)" "a root without .claude/skills fails closed"

gate
fails "<root> is required" "no root fails"

gate --bogus "$WORK/clean"
fails "unknown option" "an unknown option fails"

gate "$WORK/clean" "$WORK/clean"
fails "unexpected extra argument" "a second root fails"

# The real tree: every shipped guard/hook script carries its header (the count is cross-checked against the scripts that carry one).
n=0; for f in "$ROOT"/.claude/skills/*/scripts/*; do [ -f "$f" ] && head -n 10 "$f" | grep -q '^# rail:' && n=$((n + 1)); done
gate "$ROOT"
passes "rails: ok ($n rails)" "the real tree passes and the count matches the scripts that carry the header"
gate --audit "$ROOT"
{ [ "$rc" -eq 0 ] && grep -qF "of $n past their review date" <<<"$out"; }; ok $? "--audit runs on the real tree"

echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
