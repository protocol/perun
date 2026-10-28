#!/usr/bin/env bash
# train_flake.sh removes the flake-store/flake-out temp dirs it makes (EXIT trap), on triage and --base paths, and leaves
# unrelated TMPDIR entries alone. Also pins the triage-rule wording in red-gate-triage.md. Stubs only; writes under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train-flake-cleanup.XXXXXX")"
trap '[ -n "$WORK" ] && rm -r "$WORK" 2>/dev/null' EXIT
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

mkdir -p "$WORK/tmp"; echo keep >"$WORK/tmp/unrelated"; echo x >"$WORK/id"
export SEEN="$WORK/seen" FLAKE_INVOCATION=x RERUN_CMD='[ -d "$FLAKE_STORE" ] && : >"$SEEN" && echo "FAIL x"; false'
TMPDIR="$WORK/tmp" bash "$SC/train_flake.sh" "$WORK/id" >/dev/null 2>&1
[ -f "$WORK/seen" ]; ok $? "positive control: triage run saw its flake store"
left=$(find "$WORK/tmp" -mindepth 1 -name 'flake-*' | wc -l | tr -d ' ')
[ "$left" -eq 0 ]; ok $? "triage path leaves no flake-store/flake-out dirs ($left left)"
TMPDIR="$WORK/tmp" bash "$SC/train_flake.sh" --base x >/dev/null 2>&1
left=$(find "$WORK/tmp" -mindepth 1 -name 'flake-*' | wc -l | tr -d ' ')
[ "$left" -eq 0 ]; ok $? "--base path leaves no flake-store/flake-out dirs ($left left)"
[ -f "$WORK/tmp/unrelated" ]; ok $? "unrelated TMPDIR entry untouched"
grep -q "solo with one worker" "$ROOT/.claude/skills/agentic-delivery/references/red-gate-triage.md" \
  && grep -q "AIMD" "$ROOT/.claude/skills/agentic-delivery/references/red-gate-triage.md"; ok $? "red-gate-triage.md carries solo-rerun and AIMD rules"
grep -q "Deletion budget" "$ROOT/.claude/skills/agentic-delivery/references/pipeline-optimizer.md"; ok $? "pipeline-optimizer.md carries deletion budget"
grep -q "pin test" "$ROOT/.claude/skills/agentic-delivery/references/retrospective.md"; ok $? "retrospective.md carries pin-test rule"
echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
