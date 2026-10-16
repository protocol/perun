#!/usr/bin/env bash
# size-ratchet measures a raise against the file's real size at the base ref, so a base whose
# size-budgets.tsv rows are stale (an unlanded wave: lanes do not commit rows) neither blocks an
# untouched file nor lets real growth through. Own fixture repo; run in CI via scripts/ci-tests.d/.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/.."
GATES="$PWD/scripts/ci-gates.sh"
W="$(mktemp -d "${TMPDIR:-/tmp}/ratchet-stale.XXXXXX")"
trap 'rm -rf "$W"' EXIT
fail=0
check() { # check <label> <expected-rc: 0|nonzero> <expected-log-grep or ''>
  local label=$1 want=$2 pat=$3 rc=0
  bash "$GATES" size-ratchet --base "$BASE" --config "$W/scripts/size-budgets.tsv" "$W" >"$W/log" 2>&1 || rc=$?
  if { [ "$want" = 0 ] && [ "$rc" -eq 0 ]; } || { [ "$want" != 0 ] && [ "$rc" -ne 0 ] && grep -q -- "$pat" "$W/log"; }; then
    echo "ok   $label"
  else
    echo "FAIL $label (rc=$rc)"; tail -5 "$W/log"; fail=1
  fi
}
rows() { printf '# unit: bytes\n.claude/skills/demo/SKILL.md\t%s\n' "$1" >"$W/scripts/size-budgets.tsv"; }
commit() { git -C "$W" add -A >/dev/null 2>&1; git -C "$W" commit -qm "$1" >/dev/null 2>&1; }

mkdir -p "$W/.claude/skills/demo" "$W/scripts"
git -C "$W" init -q
git -C "$W" config user.email test@example.com
git -C "$W" config user.name Test
SKILL="$W/.claude/skills/demo/SKILL.md"
printf '%020d' 0 >"$SKILL"      # 20 bytes at base
rows 12                          # stale row: the file already grew past it on the base
commit base
BASE="$(git -C "$W" rev-parse HEAD)"

# A: untouched file, row regenerated to the real size (20): not a raise although 12 -> 20 vs the stale row.
rows 20; commit regen
check "untouched file with a stale base row passes" 0 ""

# B: planted RED, real growth 20 -> 30 with no marker: must fail, naming the real base size.
git -C "$W" reset -q --hard "$BASE"
printf '%030d' 0 >"$SKILL"; rows 30; commit grow
check "real growth is measured from the base size, not the stale row (planted RED)" nonzero 'raised 20->30'

# C: the marker names the real base size: passes.
git -C "$W" reset -q --hard "$BASE"
printf '%030d' 0 >"$SKILL"; rows 30
commit "grow with marker

size-budget-raise: .claude/skills/demo/SKILL.md 20→30 fixture growth is deliberate"
check "growth with a marker naming the real base size passes" 0 ""

# D: a marker built on the stale row (12→30) no longer approves the growth.
git -C "$W" reset -q --hard "$BASE"
printf '%030d' 0 >"$SKILL"; rows 30
commit "grow with a stale-row marker

size-budget-raise: .claude/skills/demo/SKILL.md 12→30 stale"
check "a marker built on the stale row does not approve the growth (planted RED)" nonzero 'raised 20->30'

[ "$fail" -eq 0 ] && echo "size-ratchet stale-base: 4/4" || { echo "size-ratchet stale-base: FAILED"; exit 1; }
