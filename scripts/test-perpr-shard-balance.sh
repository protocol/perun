#!/usr/bin/env bash
# Tests for the time balance of the CI `perpr` legs: scripts/ci-tests-shard.sh weighs every serial scripts/ci-tests.d
# registration with scripts/ci-durations.tsv. On the committed table the legs ci.yml's perpr job runs (the N its legs pass in
# SHARD=i/N, read from ci.yml, not assumed) are predicted within 10% of equal, the
# slices stay disjoint and complete for N = 1..5, and a registration the table lacks (or has no valid row for) counts as
# the table's median, so adding a test never needs a table edit. Background (*.bg.sh) registrations run beside the serial
# ones and stay round-robin. The awk command CONTRIBUTING.md gives for rebuilding the table runs on synthetic job logs.
# Hermetic: fixtures live under $TMPDIR; the checkout is only read. The malformed-SHARD and empty-slice exits are pinned in
# scripts/test-perpr-shard.sh.
# Prints PASS/FAIL per case and a final "Tests: P/N"; exits non-zero on any failure.
# shellcheck disable=SC2319 # each `ok $?` reads the status of the check on the line before it, on purpose
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
H="$ROOT/scripts/ci-tests-shard.sh"
T="$ROOT/scripts/ci-durations.tsv"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-shard-balance.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
slice() { env -u SHARD SHARD="$1" bash "${2:-$H}"; }  # <i/N> [helper]: the dry listing of one slice
rows() { grep -v '^#' "$T" | grep .; }  # the table's data rows (comment lines dropped)

# The committed table: one `path<TAB>whole seconds >= 1` row per registration, no path twice, C-sorted so a refresh diffs row by row.
[ "$(rows | wc -l)" -gt 0 ] && ! rows | grep -qvE "^scripts/ci-tests\.d/[^[:space:]]+\.sh$(printf '\t')[1-9][0-9]*$" \
  && [ "$(rows | cut -f1)" = "$(rows | cut -f1 | LC_ALL=C sort -u)" ]
ok $? "scripts/ci-durations.tsv rows are path<TAB>seconds (>= 1), sorted, no path twice"

# Disjoint and complete for any N: the N slices together list each registration exactly once, and none is empty.
all="$(cd "$ROOT" && printf '%s\n' scripts/ci-tests.d/*.sh | LC_ALL=C sort)"
bad=""
for N in 1 2 3 4 5; do
  got=""; i=1
  while [ "$i" -le "$N" ]; do
    s="$(slice "$i/$N")"; [ -n "$s" ] || bad="$bad $i/$N"
    got="$got$s"$'\n'; i=$((i + 1))
  done
  [ "$(grep . <<<"$got" | LC_ALL=C sort)" = "$all" ] || bad="$bad N=$N"
done
[ -z "$bad" ]; ok $? "N = 1..5: the slices of the real tree are non-empty, disjoint and cover every registration${bad:+ (bad:$bad)}"

# Balance: predicted serial seconds per leg = the table seconds of the leg's *.sh registrations, a registration without a row at
# the table's median (the (n/2+1)-th smallest). Background tests are not counted: they run beside the serial ones.
med="$(rows | cut -f2 | sort -n | awk '{ a[NR] = $1 } END { print NR ? a[int(NR / 2) + 1] : 1 }')"
secs() { slice "$1" | awk -F'\t' -v t="$T" -v med="$med" 'BEGIN { while ((getline < t) > 0) w[$1] = $2 } !/\.bg\.sh$/ { s += ($0 in w) ? w[$0] : med } END { print s + 0 }'; }
# N = what ci.yml's perpr legs pass in SHARD=i/N (the same read as scripts/test-perpr-shard.sh), so a matrix change re-aims this case.
nlegs="$(awk '/^  [a-z]+:$/ { j = $1 } j == "perpr:"' "$ROOT/.github/workflows/ci.yml" | grep -oE 'SHARD: \$\{\{ matrix.shard \}\}/[0-9]+' | grep -oE '[0-9]+$' | sort -u)"
case "$nlegs" in '' | *[!0-9]* | 0*) nlegs=0 ;; esac  # not exactly one positive N: the case below fails instead of dividing by it
tot=0 max=0 per=""; i=1
while [ "$i" -le "$nlegs" ]; do s="$(secs "$i/$nlegs")"; per="$per${per:+/}$s"; tot=$((tot + s)); [ "$s" -gt "$max" ] && max=$s; i=$((i + 1)); done
[ "$tot" -gt 0 ] && [ $((max * nlegs * 10)) -le $((tot * 11)) ]  # max <= 1.1 * tot / nlegs, in integers
ok $? "N=$nlegs, the legs of ci.yml's perpr job: the slowest leg is predicted within 1.1x of the mean (legs $per s, slowest $max, mean $((tot / (nlegs ? nlegs : 1))))"

# A fixture root. Seconds: x1 10, x2 6, x3 6, x4 2, x5 2; u.sh has a malformed row (so no row); y.bg.sh and a stale row (gone.sh) carry
# big seconds and weigh no leg. They are valid rows, so they count in the median like any other (7 rows: the 4th smallest is 6) but
# do not move it here (5 rows: the 3rd smallest is 6), so u weighs 6. Longest first, ties by name: x1 u x2 x3 x4 x5; N=2 puts x1 on
# leg 1, u and x2 on leg 2, x3 on leg 1, x4 and x5 on leg 2 (a sorted-position split, or u at 0, 1 or 5, differs).
FX="$WORK/fx"; D=scripts/ci-tests.d; mkdir -p "$FX/$D"; cp "$H" "$FX/scripts/"; FH="$FX/scripts/ci-tests-shard.sh"
for n in u x1 x2 x3 x4 x5 y.bg z.bg; do echo : >"$FX/$D/$n.sh"; done
tab=$'\t'
printf '%s\n' "# a comment" "" "$D/x1.sh${tab}10" "$D/x2.sh${tab}6" "$D/x3.sh${tab}6" "$D/x4.sh${tab}2" "$D/x5.sh${tab}2" \
  "$D/u.sh${tab}fast" "$D/y.bg.sh${tab}99" "$D/gone.sh${tab}50" >"$FX/scripts/ci-durations.tsv"
[ "$(slice 1/2 "$FH")" = "$D/x1.sh"$'\n'"$D/x3.sh"$'\n'"$D/y.bg.sh" ] \
  && [ "$(slice 2/2 "$FH")" = "$D/u.sh"$'\n'"$D/x2.sh"$'\n'"$D/x4.sh"$'\n'"$D/x5.sh"$'\n'"$D/z.bg.sh" ]
ok $? "fixture N=2: longest first onto the least-loaded leg, a malformed row weighs the median, background stays round-robin"
echo : >"$FX/$D/zz-new.sh"  # a new registration with no table row
got="$(slice 1/2 "$FH"; slice 2/2 "$FH")"
[ "$(grep -c . <<<"$got")" -eq 9 ] && [ "$(grep -c 'zz-new\.sh$' <<<"$got")" -eq 1 ]
ok $? "fixture: a registration with no table row is listed by exactly one slice (adding a test needs no table edit)"

# CONTRIBUTING.md's rebuild command on synthetic logs. a.sh crosses midnight (5.4 s -> 5), b.sh is 0.2 s (at least 1), c.sh 4.4 s (4),
# d.sh 1.5 s (2), f.sh 7 s; the background waits (two in a row, as on leg 1) are no rows, and e.sh, the last serial line of leg2.log,
# gets no row (it must not pair with the first line of leg3.log).
LG="$WORK/logs"; mkdir -p "$LG"
printf '%s\n' "2026-10-30T23:59:58.2000000Z Current runner version" "2026-10-30T23:59:59.0000000Z == $D/a.sh" "2026-10-31T00:00:03.6000000Z output" \
  "2026-10-31T00:00:04.4000000Z == $D/b.sh" "2026-10-31T00:00:04.6000000Z == $D/c.sh" \
  "2026-10-31T00:00:09.0000000Z == $D/q.bg.sh (started in the background)" \
  "2026-10-31T00:00:12.0000000Z == $D/r.bg.sh (started in the background)" >"$LG/leg1.log"
printf '%s\n' "2026-10-31T00:01:00.0000000Z == $D/d.sh" "2026-10-31T00:01:01.5000000Z == $D/e.sh" >"$LG/leg2.log"
printf '%s\n' "2026-10-31T00:05:00.0000000Z == $D/f.sh" "2026-10-31T00:05:07.0000000Z == $D/g.bg.sh (started in the background)" >"$LG/leg3.log"
prog="$(grep -m1 "^  awk '" "$ROOT/CONTRIBUTING.md" | sed "s/^  awk '//; s/' leg.*//")"
[ -n "$prog" ] && [ "$(cd "$LG" && awk "$prog" leg1.log leg2.log leg3.log | LC_ALL=C sort)" \
  = "$(printf '%s\t%s\n' "$D/a.sh" 5 "$D/b.sh" 1 "$D/c.sh" 4 "$D/d.sh" 2 "$D/f.sh" 7)" ]
ok $? "CONTRIBUTING.md's table rebuild command: seconds between == lines, rounded, at least 1, midnight wrap, no row for a background wait or a file's last test"

echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
