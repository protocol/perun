#!/usr/bin/env bash
# regen-unlanded.sh [--check] <base-ref> — keep derived files out of lane PRs.
#
# SHA256SUMS, scripts/size-budgets.tsv rows and the INDEX.md files are derived from the skill trees.
# Committing them in every lane PR makes any two PRs conflict on them as soon as one merges, so lanes
# do not commit them. They are rebuilt at land time (`land-release.sh`), and that land commit is where
# they are checked byte-for-byte.
#
# A tree is "landed" when its VERSION differs from <base-ref>'s (only land-release.sh bumps it).
#   (no flag)  unlanded: rebuild the derived files in place so every later gate sees them current (CI
#              runs this first; the size ratchet still compares the rebuilt rows to the base's rows).
#              landed or <base-ref> unresolvable: do nothing, so the committed files are checked as-is.
#   --check    exit 0 when the tree is unlanded (derived files are not expected to be committed), else 1.
# An unresolvable base counts as landed: fail closed, the strict check runs.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
check=0; [ "${1:-}" = "--check" ] && { check=1; shift; }
base=${1:-}
v=.claude/skills/deep-code-review/VERSION
unlanded=0
if [ -n "$base" ] && git cat-file -e "$base^{commit}" 2>/dev/null \
  && [ "$(git show "$base:$v" | tr -d '[:space:]')" = "$(tr -d '[:space:]' <"$v")" ]; then unlanded=1; fi
[ "$check" -eq 1 ] && { [ "$unlanded" -eq 1 ]; exit; }
if [ "$unlanded" -eq 1 ]; then bash scripts/land-release.sh --regen; echo "regen-unlanded: derived files rebuilt"
else echo "regen-unlanded: landed tree or no base; committed derived files are checked as-is"; fi
