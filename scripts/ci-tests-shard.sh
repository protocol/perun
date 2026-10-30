#!/usr/bin/env bash
# ci-tests-shard.sh — list the scripts/ci-tests.d registrations that shard SHARD=i/N runs, one path per line, sorted.
# Same SHARD=i/N spelling as scripts/test-ci-gates.sh (CI runs SHARD=i/3, one `perpr` matrix leg per slice); unset lists all.
# Sorted in the C locale, serial (*.sh) and background (*.bg.sh) registrations numbered separately from 0 so the slow
# background ones spread over the legs too; shard i takes the numbers equal to i-1 modulo N. The N slices are disjoint and
# cover every registration (a dotfile is not one: the step globs skip it). A malformed SHARD exits 2 and an empty slice
# exits 1, never a silently empty list.
# Run from anywhere; paths are relative to the repo root, as the CI steps and run-ci-tests.sh spell them.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
s="${SHARD:-1/1}"
[[ $s =~ ^([1-9][0-9]*)/([1-9][0-9]*)$ ]] && [ "${BASH_REMATCH[1]}" -le "${BASH_REMATCH[2]}" ] \
  || { echo "ci-tests-shard: SHARD must be i/N with 1 <= i <= N, got: $s" >&2; exit 2; }
find scripts/ci-tests.d -maxdepth 1 -name '*.sh' ! -name '.*' | LC_ALL=C sort \
  | awk -v i="${BASH_REMATCH[1]}" -v n="${BASH_REMATCH[2]}" '{ k = /\.bg\.sh$/ } c[k]++ % n == i - 1' | grep .  # awk-v-ok: i and n are positive integers checked by the regex above
