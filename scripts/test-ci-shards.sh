#!/usr/bin/env bash
# Guards the sharded CI layout: every step the single serial `gates` job once ran (scripts/ci-step-names.txt, frozen
# from the pre-split ci.yml) must still appear in .github/workflows/ci.yml, the aggregate job must still be named
# `gates` and need every other job, and every SHARD slice of scripts/test-ci-gates.sh must be wired. Offline.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
Y="$ROOT/.github/workflows/ci.yml"
fail=0
bad() { echo "FAIL  $1"; fail=1; }
while IFS= read -r n; do
  grep -qF -e "- name: $n" -e "- uses: $n" "$Y" || bad "step dropped from ci.yml: $n"
done <"$ROOT/scripts/ci-step-names.txt"
grep -qE '^  gates:$' "$Y" || bad "no job named gates"
jobs="$(grep -E '^  [a-z]+:$' "$Y" | tr -d ' :' | grep -vx -e jobs -e gates -e permissions)"
for j in $jobs; do
  sed -n '/^  gates:$/,$p' "$Y" | grep -E '^    needs:' | grep -qw "$j" || bad "gates does not need $j"
done
sed -n '/^  gates:$/,$p' "$Y" | grep -qF "if: always()" || bad "gates lacks if: always()"
grep -qE '^  merge_group:' "$Y" || bad "no merge_group trigger"
n="$(grep -oE 'SHARD: \$\{\{ matrix.shard \}\}/[0-9]+' "$Y" | grep -oE '[0-9]+$')"
for i in $(seq 1 "${n:-0}"); do grep -qE "^if _shard_on $i; then\$" "$ROOT/scripts/test-ci-gates.sh" || bad "shard $i has no cases"; done
[ -n "$n" ] || bad "no SHARD matrix"
[ "$fail" -eq 0 ] && echo "PASS  ci shards keep every step" && echo "Tests: 1/1"
exit "$fail"
