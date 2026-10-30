#!/usr/bin/env bash
# Tests for the CI `perpr` job's sharding: scripts/ci-tests-shard.sh (the SHARD=i/N slices of scripts/ci-tests.d) and the two
# ci.yml steps that run one leg. The 3 slices of the real tree are disjoint and cover every registration, a malformed SHARD or
# an empty slice fails closed, a leg runs exactly its slice and its tests never see SHARD, a failing test fails its own leg,
# and `gates` still needs `perpr`. Hermetic: fixtures live under $TMPDIR; the checkout is only read.
# Prints PASS/FAIL per case and a final "Tests: P/N"; exits non-zero on any failure.
# shellcheck disable=SC2319 # each `ok $?` reads the status of the [ ] check on the line before it, on purpose
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
Y="$ROOT/.github/workflows/ci.yml"
H="$ROOT/scripts/ci-tests-shard.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-perpr-shard.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }
slice() { env -u SHARD SHARD="$1" bash "${2:-$H}"; }  # <i/N> [helper]: the dry listing of one slice

# The real tree: 3 slices, disjoint, covering every registration (serial and .bg.sh), spread evenly.
all="$(cd "$ROOT" && printf '%s\n' scripts/ci-tests.d/*.sh | LC_ALL=C sort)"
s1="$(slice 1/3)"; s2="$(slice 2/3)"; s3="$(slice 3/3)"
joined="$(printf '%s\n%s\n%s\n' "$s1" "$s2" "$s3")"
[ -z "$(LC_ALL=C sort <<<"$joined" | uniq -d)" ]; ok $? "slices 1/3, 2/3 and 3/3 of scripts/ci-tests.d are disjoint"
[ "$(LC_ALL=C sort <<<"$joined")" = "$all" ]; ok $? "slices 1/3, 2/3 and 3/3 together cover every registration"
[ "$(env -u SHARD bash "$H")" = "$all" ] && [ "$(slice 1/1)" = "$all" ]; ok $? "SHARD unset or 1/1 lists every registration"
n1=$(grep -c . <<<"$s1"); n2=$(grep -c . <<<"$s2"); n3=$(grep -c . <<<"$s3")
[ "$n1" -gt 0 ] && [ $((n1 - n2)) -le 2 ] && [ $((n2 - n1)) -le 2 ] && [ $((n1 - n3)) -le 2 ] && [ $((n3 - n1)) -le 2 ] && [ $((n2 - n3)) -le 2 ] && [ $((n3 - n2)) -le 2 ]
ok $? "the 3 slices differ by at most 2 registrations ($n1/$n2/$n3)"
[ "$s1" = "$(LC_ALL=C sort <<<"$s1")" ]; ok $? "a slice is listed sorted"

# Fail closed: a bad SHARD is exit 2 with nothing on stdout, never an empty or full list a leg would run on.
bad=0
for v in 0/3 4/3 1/0 x/3 1 1/3/5 ' 1/3' -1/3 01/3; do
  out="$(slice "$v" 2>/dev/null)"; rc=$?
  [ "$rc" -eq 2 ] && [ -z "$out" ] || { bad=1; echo "  SHARD='$v' gave rc=$rc out=[$out]"; }
done
[ "$bad" -eq 0 ]; ok $? "a malformed SHARD (0/3, 4/3, 1/0, x/3, 1, 1/3/5, ' 1/3', -1/3, 01/3) exits 2 with no output"

# A fixture root: serial a c d f h and background b e g. Each kind is numbered from 0 on its own, so 3 background tests spread 1/2/3.
FX="$WORK/fx"; mkdir -p "$FX/scripts/ci-tests.d" "$WORK/bin"; cp "$H" "$FX/scripts/"
for n in a b.bg c d e.bg f g.bg h; do
  # shellcheck disable=SC2016  # the fixture test expands these itself
  echo 'echo "$0 shard=${SHARD-unset}" >>"$PERPR_LOG"' >"$FX/scripts/ci-tests.d/$n.sh"
done
D=scripts/ci-tests.d
[ "$(slice 1/3 "$FX/scripts/ci-tests-shard.sh")" = "$D/a.sh"$'\n'"$D/b.bg.sh"$'\n'"$D/f.sh" ]; ok $? "fixture 1/3 = serial 0 and 3, background 0"
[ "$(slice 2/3 "$FX/scripts/ci-tests-shard.sh")" = "$D/c.sh"$'\n'"$D/e.bg.sh"$'\n'"$D/h.sh" ]; ok $? "fixture 2/3 = serial 1 and 4, background 1"
[ "$(slice 3/3 "$FX/scripts/ci-tests-shard.sh")" = "$D/d.sh"$'\n'"$D/g.bg.sh" ]; ok $? "fixture 3/3 = serial 2, background 2"
out="$(slice 9/9 "$FX/scripts/ci-tests-shard.sh" 2>&1)"; rc=$?
[ "$rc" -eq 1 ] && [ -z "$out" ]; ok $? "an empty slice (9/9 of 8 registrations) exits 1 instead of running nothing and passing"
echo 'exit 9' >"$FX/$D/.a.sh"   # sorts first; the step globs skip dotfiles, so counting it would shift every later position
[ "$(slice 1/3 "$FX/scripts/ci-tests-shard.sh")" = "$D/a.sh"$'\n'"$D/b.bg.sh"$'\n'"$D/f.sh" ] && [ "$(slice 3/3 "$FX/scripts/ci-tests-shard.sh")" = "$D/d.sh"$'\n'"$D/g.bg.sh" ]
ok $? "a dotfile in scripts/ci-tests.d (the step globs skip it) is not counted: the fixture slices stay as above"
rm "$FX/$D/.a.sh"

# ci.yml: the perpr job is a matrix 1..N whose legs pass SHARD=i/N, and `gates` fails unless every leg passed.
p="$(awk '/^  [a-z]+:$/ { j = $1 } j == "perpr:"' "$Y")"
n="$(grep -oE 'SHARD: \$\{\{ matrix.shard \}\}/[0-9]+' <<<"$p" | grep -oE '[0-9]+$' | sort -u)"
want=1; i=2; while [ "$i" -le "${n:-0}" ]; do want="$want, $i"; i=$((i + 1)); done  # "1, 2, 3": BSD seq -s leaves a trailing separator
[ -n "$n" ] && [ "$(sed -n 's/^        shard: \[\(.*\)\]$/\1/p' <<<"$p")" = "$want" ]
ok $? "perpr: the matrix is exactly shard 1..N for the N its legs pass in SHARD=i/N (no slice dropped)"
grep -qF 'fail-fast: false' <<<"$p"; ok $? "perpr: every leg runs to the end (fail-fast: false)"
g="$(sed -n '/^  gates:$/,$p' "$Y")"
grep -E '^    needs:' <<<"$g" | grep -qw perpr \
  && grep -qF "contains(needs.*.result, 'failure')" <<<"$g" && grep -qF "contains(needs.*.result, 'cancelled')" <<<"$g" \
  && grep -qF "contains(needs.*.result, 'skipped')" <<<"$g"
ok $? "gates needs perpr and fails on a failed, cancelled or skipped leg"

# ci.yml's own start + per-PR step bodies, run as each leg over the fixture (a dead line cannot pass).
body() { awk -v n="- name: $1" 'index($0, n) { f = 1 } f && /^        run: \|$/ { r = 1; next } r { if ($0 ~ /[^ ]/ && substr($0, 1, 10) != "          ") exit; print substr($0, 11) }' "$Y"; }
{ body "Start background per-PR tests"; echo "("; body "Per-PR tests (scripts/ci-tests.d)"; echo ")"; } >"$WORK/steps.sh"
command -v timeout >/dev/null || { printf '#!/bin/sh\nshift; exec "$@"\n' >"$WORK/bin/timeout"; chmod +x "$WORK/bin/timeout"; }  # macOS has no coreutils timeout
leg() { # leg <i>: leg i of 3 in a fresh RUNNER_TEMP; output in $WORK/leg<i>.out, exit status returned
  rt="$(mktemp -d "$WORK/rt.XXXXXX")"
  (cd "$FX" && PATH="$WORK/bin:$PATH" PERPR_LOG="$WORK/log" RUNNER_TEMP="$rt" SHARD="$1/3" BG_WAIT_S=30 bash -e "$WORK/steps.sh") >"$WORK/leg$1.out" 2>&1
}
: >"$WORK/log"
rcs=""; for i in 1 2 3; do leg $i; rcs="$rcs$? "; done
[ "$rcs" = "0 0 0 " ]; ok $? "the 3 legs of the real ci.yml steps all pass over the fixture (rc: $rcs)"
[ "$(LC_ALL=C sort "$WORK/log" | sed 's/ shard=.*//' | tr '\n' ' ')" = "$D/a.sh $D/b.bg.sh $D/c.sh $D/d.sh $D/e.bg.sh $D/f.sh $D/g.bg.sh $D/h.sh " ]
ok $? "across the 3 legs every registration ran exactly once"
[ "$(grep -c ' shard=unset$' "$WORK/log")" -eq 8 ]; ok $? "no test inherited SHARD (a test that reads SHARD would run only its own slice)"
good=0
for i in 1 2 3; do
  [ "$(sed -n 's/^== \([^ ]*\).*/\1/p' "$WORK/leg$i.out" | LC_ALL=C sort)" = "$(slice $i/3 "$FX/scripts/ci-tests-shard.sh")" ] || good=1
done
[ "$good" -eq 0 ]; ok $? "each leg runs exactly the registrations its dry listing names"
body "Per-PR tests (scripts/ci-tests.d)" >"$WORK/solo.sh"; : >"$WORK/log"   # the per-PR step without the start step before it: no list
solo=0; (cd "$FX" && PATH="$WORK/bin:$PATH" PERPR_LOG="$WORK/log" RUNNER_TEMP="$(mktemp -d "$WORK/rt.XXXXXX")" bash -e "$WORK/solo.sh") >"$WORK/solo.out" 2>&1 || solo=1
[ "$solo" -eq 1 ] && [ ! -s "$WORK/log" ] && grep -q 'wrote no test list' "$WORK/solo.out"
ok $? "the per-PR step fails and runs nothing when the start step left no list (a skipped start step cannot pass vacuously)"
echo 'exit 7' >"$FX/$D/d.sh"; echo 'exit 3' >"$FX/$D/e.bg.sh"   # d is serial in leg 3, e is background in leg 2
rcs=""; for i in 1 2 3; do leg $i; rcs="$rcs$(( $? > 0 )) "; done
[ "$rcs" = "0 1 1 " ]; ok $? "a failing serial test fails leg 3 and a failing background test fails leg 2, leg 1 stays green (failed: $rcs)"

echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
