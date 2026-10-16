#!/usr/bin/env bash
# Review-cost cut: SKILL.md stays small and the sections moved to
# references/stage-and-closeout.md stay present, routed and floor-safe.
# Plain bash; read-only. Prints PASS/FAIL lines; exits non-zero on any failure.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
D="$ROOT/.claude/skills/deep-code-review"
R="$D/references/stage-and-closeout.md"
fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; else echo "FAIL  $2"; fail=1; fi; }

[ "$(wc -c <"$D/SKILL.md")" -le 20000 ]
ok $? "SKILL.md (read on every review) is at most 20000 bytes"

grep -qF '`stage-and-closeout.md`' "$D/SKILL.md" && sed -n 3p "$R" | grep -q '^Read this when'
ok $? "stage-and-closeout.md is routed from SKILL.md and carries a Read-this-when trigger"

for a in 'Stage-evolution lenses' '| `prototype` |' '**Declared or evidenced, never guessed.**' \
  '**Stage moves urgency, not intrinsic severity.**' '## Definition of done (a)' 'Coverage ledger reconciled' \
  'Identity Arrival Map printed' '`mechanism-unproven` fixes keep the finding open.' '| `idea-critic` |' \
  '`--with-gates` is a **mechanism, not a skill**'; do
  grep -qF -- "$a" "$R" && ! grep -qF -- "$a" "$D/SKILL.md"
  ok $? "moved once, not duplicated: $a"
done

for a in '**(b) Target ship-ready**' '`prototype` with an exposed credential is still Critical' \
  'boundary is absolute:** plan/tabletop/analyse' 'Unstated → the stricter'; do
  grep -qF -- "$a" "$D/SKILL.md"
  ok $? "stays in the always-loaded SKILL.md: $a"
done
exit $fail
