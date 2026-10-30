#!/usr/bin/env bash
# Tests for `ci-gates.sh guard-registry` (#1592): every hook Perun installs and every ci-gates.sh gate has one row (owner role, reason,
# review-by) in one TSV. A guard with no row, an empty reason, a bad date, a person as owner, a duplicate row, or a row for a guard that
# is gone each fail the gate; `--report` is read-only and lists rows past review-by plus logged guards with no fire in N days ("unknown"
# where there is no log). Hermetic: each case builds a throwaway fixture root under $TMPDIR (no repo state, no network); the last block
# reads the real tree. Prints PASS/FAIL per case and a final "Tests: P/N"; exits non-zero on any failure. Run against a ci-gates.sh
# without the subcommand (GATE=<old copy>), every case that drives the gate fails (exit 2, no such subcommand); only the two
# real-tree file checks (header parity, reply_cap log path) do not depend on it.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-guardreg.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT
GATE="${GATE:-$ROOT/scripts/ci-gates.sh}"
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }

FUTURE="2999-12-31"  # a review date no clock reaches, so the gate cases never rot
PAST="2000-01-01"
TODAY="$(date +%F)"
TEN_DAYS_AGO="$(python3 -c 'import datetime as d; print(d.date.today() - d.timedelta(days=10))')"
YESTERDAY="$(python3 -c 'import datetime as d; print(d.date.today() - d.timedelta(days=1))')"

# base: one row per guard of the fixture root below (a wired hook, a git hook, two gates)
base() {
  printf '%s\t%s\t%s\t%s\n' \
    hook:demo/wired.py demo 'block a thing' "$FUTURE" \
    hook:.githooks/pre-push demo 'rerun the tests' "$FUTURE" \
    gate:alpha demo 'first gate' "$FUTURE" \
    gate:beta-two demo 'second gate' "$FUTURE"
}
# mk <case>: a fixture root with a hook a template wires (wired.py; ghost.py is named but absent), a script no template wires (helper.py), a
# dispatcher with two gates, an install.sh that writes one git hook and one non-hook file, and a registry holding the 4 base rows
mk() {
  R="$WORK/$1"; S="$R/.claude/skills/demo"; REG="$R/reg.tsv"; mkdir -p "$S/scripts" "$S/templates" "$R/scripts"
  : >"$S/scripts/wired.py"; : >"$S/scripts/helper.py"
  # shellcheck disable=SC2016  # file literals: $CLAUDE_PROJECT_DIR, ${GATES_SRC} and "$@" must reach the fixtures unexpanded
  {
    printf '%s\n' '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"python3 \"$CLAUDE_PROJECT_DIR/.claude/skills/demo/scripts/wired.py\""},{"type":"command","command":"python3 ghost.py"}]}]}}' >"$S/templates/demo.settings.json"
    printf '%s\n' 'cmd_alpha() { :; }' 'cmd_beta_two() { :; }' 'case "$subcmd" in' '  alpha) cmd_alpha "$@" ;;' '  beta-two) cmd_beta_two "$@" ;;' '  -h|--help) usage; exit 0 ;;' '  *) usage; exit 2 ;;' 'esac' >"$R/scripts/ci-gates.sh"
    printf '%s\n' '  write_gate_file "${GATES_SRC}/pre-push-verify.sh" "${TARGET_DIR}/.githooks/pre-push" 1' '  write_gate_file "${GATES_SRC}/dcr-gates.sh" "${TARGET_DIR}/scripts/dcr-gates.sh" 1' >"$R/install.sh"
  }
  { printf '# header\n\n'; base; } >"$REG"
}
drop() { grep -vF -- "$1"$'\t' "$REG" >"$REG.n"; mv "$REG.n" "$REG"; }  # <id>: remove that guard's row
setrow() { drop "$1"; local IFS=$'\t'; printf '%s\n' "$*" >>"$REG"; }   # <id> <field>...: replace the row, one tab between fields
run() { out="$(bash "$GATE" guard-registry --registry "$REG" "$@" "$R" 2>&1)"; rc=$?; }  # [option...]: the gate on the current fixture
passes() { [ "$rc" -eq 0 ] && grep -qF -- "$1" <<<"$out"; ok $? "$2"; }   # <expected output substring> <label>
fails() { [ "$rc" -eq 1 ] && grep -qF -- "$1" <<<"$out"; ok $? "$2"; }    # exit 1 (not 2 = no such subcommand) and the output says why
has() { grep -qF -- "$1" <<<"$out"; }

mk clean; run
passes "guard-registry: ok (2 hooks, 2 gates)" "a registry with one row per hook and gate passes; a script no template wires, a template name that resolves to no script, and a non-hook install.sh file are not guards"
mk 'br[a]cket*'; run
passes "guard-registry: ok (2 hooks, 2 gates)" "a root with glob characters in its path works"
mk relroot; out="$(cd "$R" && bash "$GATE" guard-registry --registry reg.tsv . 2>&1)"; rc=$?
passes "guard-registry: ok (2 hooks, 2 gates)" "a relative root (.) works"

# --- coverage: a guard with no row -------------------------------------------------------------------------------------------
mk nohook; drop hook:demo/wired.py; run
fails "hook:demo/wired.py is a guard with no row" "a hook script a template wires, with no row, fails and is named"
mk nogate; drop gate:beta-two; run
fails "gate:beta-two is a guard with no row" "a gate subcommand with no row fails and is named"
mk nogit; drop hook:.githooks/pre-push; run
fails "hook:.githooks/pre-push is a guard with no row" "a git hook install.sh writes, with no row, fails and is named"
mk newgit
# shellcheck disable=SC2016  # install.sh fixture text keeps ${GATES_SRC} unexpanded
printf '%s\n' '  write_gate_file "${GATES_SRC}/x.sh" "${TARGET_DIR}/.githooks/pre-commit" 1' >>"$R/install.sh"; run
fails "hook:.githooks/pre-commit is a guard with no row" "a second git hook install.sh writes needs its own row"
mk second; : >"$S/scripts/wired2.py"; printf '%s\n' '{"hooks":{"PreToolUse":[{"hooks":[{"type":"command","command":"python3 ~/.claude/perun-rules/wired2.py"}]}]}}' >"$S/templates/two.settings.json"; run
fails "hook:demo/wired2.py is a guard with no row" "a hook a second template wires by bare home path is found and needs a row"
mk odd
# shellcheck disable=SC2016  # fixture dispatcher text keeps $x and "$@" unexpanded
printf '%s\n' 'cmd_gamma() { :; }' 'case "$x" in gamma) cmd_gamma "$@";; esac' >>"$R/scripts/ci-gates.sh"; run
fails "a cmd_ function has no dispatcher line like" "a gate function dispatched in another shape is refused, so it cannot skip its row"
mk empty; : >"$REG"; run
fails "hook:demo/wired.py is a guard with no row" "an empty registry fails (every guard is missing)"
mk blankhelp; setrow hook:demo/helper.py demo 'not wired' "$FUTURE"; run
fails "hook:demo/helper.py: row names no guard that ships" "a row for a script no template wires is a stale row"

# --- stale and duplicate rows -------------------------------------------------------------------------------------------------
mk stalegate; setrow gate:gone demo 'was removed' "$FUTURE"; run
fails "gate:gone: row names no guard that ships (delete the row)" "a row for a gate that no longer exists fails"
mk stalehook; setrow hook:demo/old.py demo 'was deleted' "$FUTURE"; run
fails "hook:demo/old.py: row names no guard that ships (delete the row)" "a row for a hook script that no longer exists fails"
mk dup; setrow gate:alpha demo 'first gate' "$FUTURE"; printf 'gate:alpha\tdemo\tagain\t%s\n' "$FUTURE" >>"$REG"; run
fails "gate:alpha: duplicate row" "two rows for one guard fail"
mk wide; setrow gate:alpha demo 'first gate' "$FUTURE" '/tmp/x.log' extra; run
fails "gate:alpha: 6 columns" "a row with more than 5 columns fails"
mk noid; printf '\tdemo\treason\t%s\n' "$FUTURE" >>"$REG"; run
fails "row has no id" "a row with an empty id fails"

# --- owner, reason, date ------------------------------------------------------------------------------------------------------
mk noowner; setrow gate:alpha '' 'first gate' "$FUTURE"; run
fails "gate:alpha: owner must be a lowercase role slug" "an empty owner fails"
for o in 'Jane Smith' 'jane@example.com' '@jsmith' 'Jane' 'jane smith' 'role_x' '-lead' '9lead'; do
  mk person; setrow gate:alpha "$o" 'first gate' "$FUTURE"; run
  fails "gate:alpha: owner must be a lowercase role slug (a role, never a person), got '$o'" "owner '$o' (a person, not a role slug) fails"
done
mk role; setrow gate:alpha release-owner 'first gate' "$FUTURE"; run
passes "guard-registry: ok" "a lowercase role slug with a hyphen passes"
mk noreason; setrow gate:alpha demo '' "$FUTURE"; run
fails "gate:alpha: reason must not be empty" "an empty reason fails"
mk blankreason; setrow gate:alpha demo '   ' "$FUTURE"; run
fails "gate:alpha: reason must not be empty" "a blank reason fails"
mk short; drop gate:alpha; printf 'gate:alpha\tdemo\n' >>"$REG"; run
fails "gate:alpha: reason must not be empty" "a row cut after the owner has no reason"
fails "gate:alpha: review-by '' is not a real YYYY-MM-DD date" "a row cut after the owner has no review-by either"
mk nodate; drop gate:alpha; printf 'gate:alpha\tdemo\tfirst gate\n' >>"$REG"; run
fails "gate:alpha: review-by '' is not a real YYYY-MM-DD date" "a row with no review-by column fails"
for d in 2027-13-01 2027-02-30 2027-02-29 2027-00-10 2027-01-00 0000-01-01 27-1-1 2027-1-30 soon 2027-01-30T00:00 20270130 ""; do
  mk bad-date; setrow gate:alpha demo 'first gate' "$d"; run
  fails "review-by '$d' is not a real YYYY-MM-DD date" "review-by ${d:-<empty>} fails as a bad date"
done
# Arabic-Indic digits (UTF-8 bytes, so this file stays ASCII) are not digits here: a gate that used \d would accept them
mk arabic-date; setrow gate:alpha demo 'first gate' "$(printf '\331\242\331\240\331\242\331\247-\331\240\331\241-\331\243\331\240')"; run
fails "is not a real YYYY-MM-DD date" "a review-by written in Arabic-Indic digits fails (only 0-9 count)"
mk leap; setrow gate:alpha demo 'first gate' 2028-02-29; run
passes "guard-registry: ok" "a real leap day passes"
mk allbad; setrow gate:alpha '' '' soon; run
{ [ "$rc" -eq 1 ] && has "owner must be" && has "reason must not be empty" && has "is not a real YYYY-MM-DD date"; }; ok $? "one row with three faults reports all three"
mk past; setrow gate:alpha demo 'first gate' "$PAST"; run
{ [ "$rc" -eq 0 ] && has "guard-registry: ok (2 hooks, 2 gates)" && ! has "report"; }; ok $? "a past review-by does not fail the plain gate (no time bomb) and prints no report"
mk comments; { printf '  # indented comment\n\n\n'; cat "$REG"; printf '# trailing\n'; } >"$REG.n"; mv "$REG.n" "$REG"; run
passes "guard-registry: ok (2 hooks, 2 gates)" "comments (also indented) and blank lines are ignored"

# --- fail closed and arguments -----------------------------------------------------------------------------------------------
mk noreg; rm "$REG"; run
fails "registry not found" "a missing registry fails closed"
mk noskills; rm -r "$R/.claude"; run
fails ".claude/skills not found (fail closed)" "a root without .claude/skills fails closed"
mk nogates; rm "$R/scripts/ci-gates.sh"; run
fails "scripts/ci-gates.sh not found (fail closed)" "a root without scripts/ci-gates.sh fails closed"
mk noinstall; rm "$R/install.sh"; run
fails "install.sh not found (fail closed)" "a root without install.sh fails closed"
mk noguards; rm -r "$S/scripts" "$S/templates"; mkdir "$S/scripts"; : >"$R/install.sh"; : >"$REG"
# shellcheck disable=SC2016  # fixture dispatcher text keeps $x unexpanded
printf 'case "$x" in\nesac\n' >"$R/scripts/ci-gates.sh"; run
fails "no hook or gate found (fail closed)" "a root that ships no guard at all fails closed instead of passing on an empty set"
out="$(bash "$GATE" guard-registry "$WORK/clean" 2>&1)"; rc=$?
fails "--registry <file> and <root> are required" "no registry fails"
mk noroot; out="$(bash "$GATE" guard-registry --registry "$REG" 2>&1)"; rc=$?
fails "--registry <file> and <root> are required" "no root fails"
mk opt; run --bogus
fails "unknown option: --bogus" "an unknown option fails"
mk extra; run "$R"
fails "unexpected extra argument" "a second root fails"
out="$(bash "$GATE" guard-registry --registry 2>&1)"; rc=$?
fails "--registry needs a value" "--registry with no value fails"
mk dayval; out="$(bash "$GATE" guard-registry --report --days 2>&1)"; rc=$?
fails "--days needs a value" "--days with no value fails"
for d in 0 abc -3 100000 1.5 ""; do
  mk bad-days; run --report --days "$d"
  fails "--days wants a whole number from 1 to 99999, got: $d" "--days ${d:-<empty>} fails"
done
out="$(bash "$GATE" --help 2>&1)"; rc=$?
{ [ "$rc" -eq 0 ] && has "guard-registry --registry <file> [--report [--days N]] <root>"; }; ok $? "--help lists the subcommand"

# --- --report: read-only owner view --------------------------------------------------------------------------------------------
mk rep-none; run --report
{ [ "$rc" -eq 0 ] && has "guard-registry: report $TODAY, fire window 30 days" && has "0 of 4 guards past review-by" \
  && has "0 guards with a fire log fired 0 times in the last 30 days" && has "fires unknown for 4 of 4 guards"; }
ok $? "--report on current rows with no fire log lists nothing, says fires are unknown for every guard, and exits 0"
{ [ "$rc" -eq 0 ] && has "this report never deletes or edits a row"; }; ok $? "--report tells the owner to confirm or retire and edits nothing"
mk rep-gate-first; setrow gate:alpha demo 'first gate' soon; run --report
{ [ "$rc" -eq 1 ] && has "FAIL gate:alpha: review-by 'soon'" && ! has "guard-registry: ok" && ! has "report $TODAY" && ! has Traceback; }; ok $? "--report on a malformed registry fails with the gate's message and prints no report"
mk rep-past; setrow gate:alpha demo 'first gate' "$PAST"; run --report
{ [ "$rc" -eq 0 ] && has "1 of 4 guards past review-by" && has "gate:alpha  owner=demo  review-by=$PAST  fires=unknown  why=first gate" && ! has "gate:beta-two  owner"; }
ok $? "--report lists only the row past review-by, with owner, date, fire status and reason, and exits 0"
mk rep-days; run --report --days 7
has "fire window 7 days"; ok $? "--days sets the fire window"
mk rep-today; setrow gate:alpha demo 'first gate' "$TODAY"; run --report
{ [ "$rc" -eq 0 ] && has "0 of 4 guards past review-by"; }; ok $? "a review-by of today is not yet past"
mk rep-yest; setrow gate:alpha demo 'first gate' "$YESTERDAY"; run --report
{ [ "$rc" -eq 0 ] && has "1 of 4 guards past review-by"; }; ok $? "a review-by of yesterday is past"

LOG="$WORK/fire.log"
mk rep-old; printf '%s lines=6 chars=700\n%s lines=4 chars=600\n' "$PAST" "2001-02-03" >"$LOG"; setrow gate:alpha demo 'first gate' "$FUTURE" "$LOG"; run --report
{ [ "$rc" -eq 0 ] && has "1 guards with a fire log fired 0 times in the last 30 days" && has "gate:alpha  owner=demo  log=$LOG  newest=2001-02-03" \
  && has "fires unknown for 3 of 4 guards"; }
ok $? "a guard whose log holds only old dated lines is listed with zero fires and its newest date; the other three stay unknown"
mk rep-new; printf '%s lines=6 chars=700\n' "$PAST" >"$LOG"; printf '%s lines=2 chars=800\n' "$TODAY" >>"$LOG"; setrow gate:alpha demo 'first gate' "$FUTURE" "$LOG"; run --report
{ [ "$rc" -eq 0 ] && has "0 guards with a fire log fired 0 times" && ! has "gate:alpha  owner"; }; ok $? "a guard with a dated line inside the window is not listed"
mk rep-past-fired; setrow gate:alpha demo 'first gate' "$PAST" "$LOG"; run --report
{ [ "$rc" -eq 0 ] && has "gate:alpha  owner=demo  review-by=$PAST  fires=1 in 30d  why=first gate"; }; ok $? "a row past review-by shows how often its logged guard fired"
mk rep-win; printf '%s lines=6 chars=700\n' "$TEN_DAYS_AGO" >"$LOG"; setrow gate:alpha demo 'first gate' "$FUTURE" "$LOG"; run --report --days 5
{ [ "$rc" -eq 0 ] && has "gate:alpha  owner=demo  log=$LOG  newest=$TEN_DAYS_AGO"; }; ok $? "a fire 10 days old is zero fires in a 5-day window"
run --report --days 30
{ [ "$rc" -eq 0 ] && has "0 guards with a fire log fired 0 times"; }; ok $? "the same fire counts inside a 30-day window"
run --report --days 10
{ [ "$rc" -eq 0 ] && has "0 guards with a fire log fired 0 times"; }; ok $? "a fire dated exactly N days ago is inside the N-day window"
run --report --days 9
{ [ "$rc" -eq 0 ] && has "1 guards with a fire log fired 0 times"; }; ok $? "a fire dated N+1 days ago is outside the N-day window"
mk rep-missing; setrow gate:alpha demo 'first gate' "$FUTURE" "$WORK/no-such.log"; run --report
{ [ "$rc" -eq 0 ] && has "0 guards with a fire log fired 0 times" && has "fires unknown for 4 of 4 guards"; }; ok $? "a fire log that does not exist is unknown, never zero fires"
mk rep-undated; printf '{"lane":1}\nnot a date\n' >"$LOG"; setrow gate:alpha demo 'first gate' "$FUTURE" "$LOG"; run --report
{ [ "$rc" -eq 0 ] && has "0 guards with a fire log fired 0 times" && has "fires unknown for 4 of 4 guards"; }; ok $? "a log with no dated line (another format) is unknown, never zero fires"
mk rep-badday; printf '2026-13-45 lines=1\n' >"$LOG"; setrow gate:alpha demo 'first gate' "$FUTURE" "$LOG"; run --report
{ [ "$rc" -eq 0 ] && has "fires unknown for 4 of 4 guards"; }; ok $? "a line that starts like a date but is not a real day does not count as a fire"
mk rep-emptylog; : >"$LOG"; setrow gate:alpha demo 'first gate' "$FUTURE" "$LOG"; run --report
{ [ "$rc" -eq 0 ] && has "0 guards with a fire log fired 0 times" && has "fires unknown for 4 of 4 guards"; }; ok $? "an existing empty log (truncated or rotated) is unknown, never zero fires"
mk rep-dir; setrow gate:alpha demo 'first gate' "$FUTURE" "$WORK"; run --report
{ [ "$rc" -eq 0 ] && has "fires unknown for 4 of 4 guards"; }; ok $? "a fire log path that is a directory is unknown"
mk rep-home; mkdir "$WORK/home"; printf '%s lines=1 chars=9\n' "$PAST" >"$WORK/home/fire.log"
# shellcheck disable=SC2088  # the registry cell holds a literal ~ for the gate to expand
setrow gate:alpha demo 'first gate' "$FUTURE" '~/fire.log'
out="$(HOME="$WORK/home" bash "$GATE" guard-registry --report --registry "$REG" "$R" 2>&1)"; rc=$?
{ [ "$rc" -eq 0 ] && has "gate:alpha  owner=demo  log=~/fire.log  newest=$PAST"; }; ok $? "~ in the fire log path expands to HOME"
# shellcheck disable=SC2016  # the registry cell holds a literal $VAR for the gate to expand
setrow gate:alpha demo 'first gate' "$FUTURE" '$GUARD_TEST_DIR/fire.log'
out="$(GUARD_TEST_DIR="$WORK/home" bash "$GATE" guard-registry --report --registry "$REG" "$R" 2>&1)"; rc=$?
{ [ "$rc" -eq 0 ] && has "gate:alpha  owner=demo  log=\$GUARD_TEST_DIR/fire.log  newest=$PAST"; }; ok $? "an environment variable in the fire log path expands"
mk rep-ro; setrow gate:alpha demo 'first gate' "$PAST" "$LOG"; printf '%s lines=1 chars=9\n' "$PAST" >"$LOG"
before="$(cksum "$REG" "$LOG" "$S/scripts/wired.py" "$R/install.sh" "$R/scripts/ci-gates.sh"; find "$R" "$LOG" -type f | LC_ALL=C sort)"
run --report
after="$(cksum "$REG" "$LOG" "$S/scripts/wired.py" "$R/install.sh" "$R/scripts/ci-gates.sh"; find "$R" "$LOG" -type f | LC_ALL=C sort)"
{ [ "$rc" -eq 0 ] && has "past review-by" && [ "$before" = "$after" ]; }; ok $? "--report on a past-due, zero-fire guard changes and removes nothing (registry, log, scripts and the file list are byte-identical)"

# --- the real tree --------------------------------------------------------------------------------------------------------------
REAL="$ROOT/scripts/guard-registry.tsv"
nh="$(grep -c '^hook:' "$REAL")"; ng="$(grep -c '^gate:' "$REAL")"
out="$(bash "$GATE" guard-registry --registry "$REAL" "$ROOT" 2>&1)"; rc=$?
passes "guard-registry: ok ($nh hooks, $ng gates)" "the real registry passes: one row per installed hook and per ci-gates.sh gate (counts match the rows)"
out="$(bash "$GATE" guard-registry --report --registry "$REAL" "$ROOT" 2>&1)"; rc=$?
{ [ "$rc" -eq 0 ] && has "guard-registry: report $TODAY"; }; ok $? "--report runs on the real tree"
# the hook rows repeat the owner and review date of the script's own `# rail:` header (scripts/ci-gates.sh rails); a change in one place must be made in both
drift=""
while IFS=$'\t' read -r id owner why review _; do
  case "$id" in hook:.githooks/*|'#'*|'') continue ;; hook:*) ;; *) continue ;; esac
  rest="${id#hook:}"
  head -n 10 "$ROOT/.claude/skills/${rest%%/*}/scripts/${rest#*/}" | grep -qxF "# rail: owner=$owner, why=$why, review=$review" || drift="$drift $id"
done <"$REAL"
[ -z "$drift" ]; ok $? "every hook row carries the same owner, reason and review date as its script's # rail: header (drift:${drift:- none})"
# shellcheck disable=SC2088  # compares against the literal ~ the registry cell holds
{ grep -qF "perun/reply-cap.log" "$ROOT/.claude/skills/agentic-delivery/scripts/reply_cap.py" \
  && [ "$(grep -F 'hook:agentic-delivery/reply_cap.py' "$REAL" | cut -f5)" = "~/.cache/perun/reply-cap.log" ]; }
ok $? "the reply_cap row's fire log is the path reply_cap.py writes"

echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
