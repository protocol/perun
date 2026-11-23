#!/usr/bin/env bash
# pre-push-verify.sh must fail fast (one line naming `git fetch <remote> <branch>`) when a new branch is pushed, the remote
# has its default branch, and the local refs/remotes/<remote>/<default> copy is missing, instead of verifying the full local
# history. A remote without that branch (empty, or a different default) keeps the full-history fallback and is not blocked.
# Hermetic: throwaway repos under TMPDIR.
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PPV=$ROOT/.claude/skills/deep-code-review/templates/pre-push-verify.sh
T=$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-nobase.XXXXXX") && [ -d "$T" ] || exit 1
trap 'rm -rf "$T"' EXIT; fail=0
G() { git -c user.name=Test -c user.email=noreply@example.com "$@"; }  # noreply form: the identity gate passes it
push() { rc=0; printf 'refs/heads/topic %s refs/heads/topic 0000000000000000000000000000000000000000\n' "$(git rev-parse HEAD)" \
  | DCR_PREPUSH_CMD=true bash "$PPV" origin >"$T/log" 2>&1 || rc=$?; }
git init -q --bare "$T/full.git" && git init -q --bare "$T/empty.git"
git init -q -b main "$T/l" && cd "$T/l" || exit 1
printf 'a\n' >f.txt && G add f.txt && G commit -qm init && G remote add origin "$T/full.git"
git push -q origin main && git update-ref -d refs/remotes/origin/main
push
if [ "$rc" != 0 ] && grep -q 'git fetch origin main' "$T/log" && ! grep -q 'full local history' "$T/log"; then echo "ok - missing local default ref fails fast"; else echo "FAIL - fail fast rc=$rc"; cat "$T/log"; fail=1; fi
git remote set-url origin "$T/empty.git"
push
if [ "$rc" = 0 ] && grep -q 'full local history' "$T/log"; then echo "ok - empty remote keeps the full-history fallback"; else echo "FAIL - empty remote rc=$rc"; cat "$T/log"; fail=1; fi
exit "$fail"
