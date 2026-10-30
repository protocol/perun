#!/usr/bin/env bash
# Tests that `ci-gates.sh rules` answers the same under en_US.UTF-8 as under the C locale (#1592). Its rows are C-sorted, so its
# comm calls must run in the C locale too: `Zeta` sorts before `alpha` in C but after it in en_US.UTF-8, which made comm see
# unsorted input and report false FAILs. Hermetic: an own git fixture under $TMPDIR, no network.
# Prints PASS/FAIL per case and a final "Tests: P/N"; exits non-zero on any failure.
set -uo pipefail
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null  # the fixture commits must not depend on the host's git config
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-rules-locale.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT
GATE="$ROOT/scripts/ci-gates.sh"
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }

# Two unenforced hard rules in one SKILL.md. The baseline also holds a stale row (Zoo) that sits between them in C order.
R="$WORK/r"; SK="$R/.claude/skills/demo/SKILL.md"; RB="$R/scripts/rule-enforcement-baseline.tsv"
mkdir -p "${SK%/*}" "${RB%/*}"
git -C "$R" init -q; git -C "$R" config user.email test@example.com; git -C "$R" config user.name Test
SKILL_MD='# Demo\n\nZeta: you MUST do this.\n\nalpha: you MUST do that.\n'
printf '%b' "$SKILL_MD" >"$SK"
row() { printf '.claude/skills/demo/SKILL.md\t%s\n' "$1"; }
{ row 'Zeta: you MUST do this.'; row 'Zoo: you MUST do a thing since removed.'; row 'alpha: you MUST do that.'; } >"$RB"
git -C "$R" add -A >/dev/null && git -C "$R" commit -qm base && BASE="$(git -C "$R" rev-parse HEAD)"

# en_US.UTF-8 is the locale that showed the bug. A runner without it (a minimal container) prints a SKIP and still runs the C cases.
LOCALES=(C)
if [ "$(LC_ALL=en_US.UTF-8 locale charmap 2>/dev/null)" = UTF-8 ]; then LOCALES+=(en_US.UTF-8); else echo "SKIP  en_US.UTF-8 cases: that locale is not installed on this runner"; fi

for L in "${LOCALES[@]}"; do
  gate() { out="$(LC_ALL=$L bash "$GATE" rules "$@" 2>&1)"; rc=$?; }
  gate --baseline "$RB" "$R"
  [ "$rc" -eq 0 ] && grep -qF 'rules: ok (2 ' <<<"$out"; ok $? "$L: baselined rules pass, with a stale baseline row between them in C order"
  printf '\nYak: you MUST do the third thing.\n' >>"$SK"; gate --baseline "$RB" "$R"
  [ "$rc" -eq 1 ] && grep -qF 'Yak: you MUST' <<<"$out" && ! grep -qF 'alpha: you MUST' <<<"$out"; ok $? "$L: a new rule is named and the baselined ones are not"
  printf '%b' "$SKILL_MD" >"$SK"
done

{ row 'Zeta: you MUST do this.'; row 'alpha: you MUST do that.'; } >"$RB"; git -C "$R" commit -qam shrink
for L in "${LOCALES[@]}"; do
  out="$(LC_ALL=$L bash "$GATE" rules --baseline "$RB" --base "$BASE" "$R" 2>&1)"; rc=$?
  [ "$rc" -eq 0 ] && grep -qF 'rules: ok (2 ' <<<"$out"; ok $? "$L: a baseline that only shrank vs base is not growth"
done

echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
