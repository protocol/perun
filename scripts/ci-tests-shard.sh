#!/usr/bin/env bash
# ci-tests-shard.sh — list the scripts/ci-tests.d registrations that shard SHARD=i/N runs, one path per line, sorted.
# Same SHARD=i/N spelling as scripts/test-ci-gates.sh (CI runs one `perpr` matrix leg per slice); unset lists all.
# Serial (*.sh) registrations are balanced by recorded time: scripts/ci-durations.tsv (path<TAB>whole seconds, from one CI run)
# is taken longest first (ties by name, C locale) and each test goes to the least-loaded leg (ties to the lowest index). A
# registration with no valid row counts as the table's median (1 for an empty or missing table), so adding a test never needs
# a table edit. Background (*.bg.sh) registrations run beside the serial ones, so they are not weighed: sorted in the C locale
# and numbered from 0, shard i takes the numbers equal to i-1 modulo N. The N slices are disjoint and cover every registration
# (a dotfile is not one: the step globs skip it) whatever the table says. A malformed SHARD exits 2 and an empty slice exits 1,
# never a silently empty list.
# Run from anywhere; paths are relative to the repo root, as the CI steps and run-ci-tests.sh spell them.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
s="${SHARD:-1/1}"
[[ $s =~ ^([1-9][0-9]*)/([1-9][0-9]*)$ ]] && [ "${BASH_REMATCH[1]}" -le "${BASH_REMATCH[2]}" ] \
  || { echo "ci-tests-shard: SHARD must be i/N with 1 <= i <= N, got: $s" >&2; exit 2; }
# ponytail: the pick below is an O(tests^2) scan, fine for hundreds of registrations; sort the weights first if it reaches thousands
# awk-v-ok: i and n are positive integers checked by the regex above
find scripts/ci-tests.d -maxdepth 1 -name '*.sh' ! -name '.*' | LC_ALL=C sort \
  | awk -F'\t' -v i="${BASH_REMATCH[1]}" -v n="${BASH_REMATCH[2]}" '
    BEGIN {
      i += 0; n += 0  # i and n are compared below, so force numbers whatever the awk does with -v values
      while ((getline < "scripts/ci-durations.tsv") > 0)
        if ($2 ~ /^[1-9][0-9]*$/) { t[$1] = $2 + 0; v[++k] = $2 + 0 }
      med = 1  # the (k/2+1)-th smallest row of the table
      for (a = 1; a <= k; a++) {
        lt = le = 0
        for (b = 1; b <= k; b++) { lt += (v[b] < v[a]); le += (v[b] <= v[a]) }
        if (lt <= int(k / 2) && le > int(k / 2)) { med = v[a]; break }
      }
    }
    /\.bg\.sh$/ { if (g++ % n == i - 1) print; next }
    { nm[++s] = $0; w[s] = ($0 in t) ? t[$0] : med }
    END {
      for (r = 0; r < s; r++) {
        x = 0
        for (j = 1; j <= s; j++) if (!d[j] && (!x || w[j] > w[x])) x = j  # the first of the heaviest left is the lowest name
        d[x] = 1
        m = 1
        # the least loaded leg, the lowest index on a tie; a leg past s gets no test (weights are >= 1), so the scan stops at s
        for (j = 2; j <= n && j <= s; j++) if (L[j] + 0 < L[m] + 0) m = j
        L[m] += w[x]
        if (m == i) print nm[x]
      }
    }' | LC_ALL=C sort | grep .
