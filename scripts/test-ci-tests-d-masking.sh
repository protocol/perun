#!/usr/bin/env bash
# Regression: a multi-command ci-tests.d registration run bare (`bash <file>`, no -e) must still fail when its first
# command fails. low-context-index.sh once returned only its last command's status, hiding a failing size gate.
set -u
cd "$(dirname "$0")/.." || exit 1
t=scripts/ci-tests.d/low-context-index.sh
[ -f "$t" ] || { echo "FAIL: $t missing" >&2; exit 1; }
d=$(mktemp -d "${TMPDIR:-/tmp}/masking.XXXXXX") || exit 1; trap 'rm -f "$d/python3"; rmdir "$d"' EXIT
printf '#!/bin/sh\n[ "$(basename "$1")" = test_skill_index_entry.py ] && exit 1\nexit 0\n' > "$d/python3"; chmod +x "$d/python3"
PATH="$d:$PATH" bash "$t" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 1 ] || { echo "FAIL: $t returned rc $rc for a failing child (want 1; 0 = masked, 127 = not run)" >&2; exit 1; }
echo "ok: failing child propagates"
