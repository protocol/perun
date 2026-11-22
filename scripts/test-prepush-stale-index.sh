#!/usr/bin/env bash
# pre-push-verify.sh dirty-tree check vs stale index stat data. A tracked file whose mtime changed
# but whose content did not (touch, checkout, editor save) must not read as a dirty tree; a real
# edit must still be refused. Hermetic: a throwaway bare remote + clone under TMPDIR; nothing pushed
# outside it.
# shellcheck disable=SC2088
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PPV=$ROOT/.claude/skills/deep-code-review/templates/pre-push-verify.sh
D=${TMPDIR:-/tmp}; T=$(mktemp -d "${D%/}/dcr-test-stale.XXXXXX") && [ -n "$T" ] && [ -d "$T" ] || { echo "no temp dir" >&2; exit 1; }
trap '[ -n "$T" ] && rm -rf "$T"' EXIT; fail=0
ok() { echo "ok - $1"; }; bad() { echo "FAIL - $1"; fail=1; }
G() { git -c user.name=Test -c user.email=test@example.com "$@"; }
git init -q --bare "$T/remote.git" && git init -q -b main "$T/local" && cd "$T/local" || exit 1
printf 'a\n' >f.txt && G add f.txt && G commit -qm init && G remote add origin "$T/remote.git" && G push -q origin HEAD:main 2>/dev/null
sha=$(git rev-parse HEAD); line="refs/heads/main $sha refs/heads/main $sha"
run() { printf '%s\n' "$line" | DCR_PREPUSH_CMD=true bash "$PPV" origin >"$T/log" 2>&1; }

# 1. mtime-only touch of a tracked file: not a dirty tree
sleep 1; touch f.txt; rc=0; run || rc=$?
if [ "$rc" = 0 ] && ! grep -q 'working tree is dirty' "$T/log"; then ok "mtime-only touch is not a dirty tree"; else bad "mtime-only touch refused"; cat "$T/log"; fi

# 2. real content edit: still refused
printf 'b\n' >>f.txt; rc=0; run || rc=$?
if [ "$rc" != 0 ] && grep -q 'working tree is dirty' "$T/log"; then ok "real edit is still refused"; else bad "real edit not refused"; cat "$T/log"; fi

exit "$fail"
