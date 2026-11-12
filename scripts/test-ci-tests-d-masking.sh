#!/usr/bin/env bash
# Regression: a multi-command ci-tests.d registration run bare (`bash <file>`, no -e) must still fail when its first
# command fails. low-context-index.sh once returned only its last command's status, hiding a failing size gate.
set -u
d=$(mktemp -d "${TMPDIR:-/tmp}/masking.XXXXXX") || exit 1; trap 'rm -f "$d/python3"; rmdir "$d"' EXIT
printf '#!/bin/sh\n[ "$(basename "$1")" = test_skill_index_entry.py ] && exit 1\nexit 0\n' > "$d/python3"; chmod +x "$d/python3"
PATH="$d:$PATH" bash scripts/ci-tests.d/low-context-index.sh >/dev/null 2>&1 && { echo "FAIL: low-context-index.sh masked a failing child (rc 0)" >&2; exit 1; }
echo "ok: failing child propagates"
