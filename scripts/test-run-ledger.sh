#!/usr/bin/env bash
# Tests for run_ledger.sh: report-first teardown of recorded worktrees and dev servers (temp fixture only).
set -uo pipefail
S="$(cd "$(dirname "$0")/.." && pwd)/.claude/skills/agentic-delivery/scripts/run_ledger.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/run-ledger.XXXXXX"); T=$(cd "$T" && pwd -P)
pass=0 fail=0; PIDS=""
ok() { if [ "$1" = 0 ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $2"; fi; }
cleanup() { for p in $PIDS; do kill "$p" 2>/dev/null; done; [ -n "$T" ] && [ -d "$T/repo" ] && git -C "$T/repo" worktree prune; }
trap cleanup EXIT
export PERUN_LEDGER="$T/ledger.tsv" GH=false GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
R="$T/repo"; git init -q -b main "$R"; git -C "$R" commit -q --allow-empty -m base; git -C "$R" update-ref refs/remotes/origin/main HEAD
for w in merged dirty unrecorded active; do git -C "$R" worktree add -q -b "b-$w" "$T/wt-$w" 2>&1 >/dev/null; done
echo x >"$T/wt-dirty/f"; git -C "$T/wt-active" commit -q --allow-empty -m wip   # not in origin/main: still active
sleep 300 & PA=$!; sleep 300 & PB=$!; PIDS="$PA $PB"
for w in merged dirty active; do bash "$S" record-worktree "$T/wt-$w"; done
bash "$S" record-pid "$PA"
bash "$S" record-worktree "$T/wt-unrecorded-typo" 2>/dev/null; ok $((! $?)) "record of a non-directory is refused"
bash "$S" record-worktree "" 2>/dev/null; ok $((! $?)) "record of an empty path is refused"
bash "$S" record-worktree "$R" 2>/dev/null; ok $((! $?)) "record of the main checkout is refused"
bash "$S" record-pid abc 2>/dev/null; ok $((! $?)) "record-pid of a non-number is refused"
printf 'wt\t\nwt\t%s\nwt\trelative/dir\npid\t\t\npid\t1\tx\n' "$R" >>"$PERUN_LEDGER"   # hostile rows: empty var, main checkout, relative, empty pid, pid 1

before=$(bash "$S" --count); sha=$(shasum "$PERUN_LEDGER"); tree=$(git -C "$R" worktree list)
rep=$(bash "$S"); echo "$rep"
ok $([ "$before" = 3 ]; echo $?) "count before = 3 (merged + dirty worktree + recorded pid), got $before"
ok $(grep -qF "worktree remove $T/wt-merged" <<<"$rep"; echo $?) "report prints the removal line for the recorded merged worktree"
ok $(grep -qF "kill $PA" <<<"$rep"; echo $?) "report prints the kill line for the recorded pid"
ok $(grep -q "kept (worktree $T/wt-dirty): dirty tree" <<<"$rep"; echo $?) "dirty recorded worktree is kept with a reason"
ok $([ "$(shasum "$PERUN_LEDGER")" = "$sha" ] && [ "$(git -C "$R" worktree list)" = "$tree" ] && kill -0 "$PA"; echo $?) "report mode changes nothing (ledger, worktrees, pid)"

bash "$S" --remove >/dev/null
ok $([ ! -d "$T/wt-merged" ]; echo $?) "recorded merged worktree removed"
ok $([ -d "$T/wt-unrecorded" ] && [ -d "$T/wt-dirty" ] && [ -d "$T/wt-active" ] && [ -d "$R" ]; echo $?) "unrecorded, dirty, active worktrees and the main checkout untouched"
ok $(kill -0 "$PB" 2>/dev/null; echo $?) "unrecorded pid never signalled"
sleep 0.3; ok $(! kill -0 "$PA" 2>/dev/null; echo $?) "recorded pid stopped"
after=$(bash "$S" --count)
ok $([ "$after" = 1 ]; echo $?) "count after = 1 (only the dirty worktree stays), got $after"
echo "leftover count at session start: before=$before after=$after"

# a recycled pid (same number, different start time) is not ours
printf 'pid\t%s\tMon Jan  1 00:00:00 2001|pcsleep n/x\n' "$PB" >"$PERUN_LEDGER"
bash "$S" --remove >/dev/null; ok $(kill -0 "$PB" 2>/dev/null; echo $?) "pid with a mismatched start time is never signalled"

# session_brief surfaces the count at session start (fresh ledger with one merged recorded worktree)
git -C "$R" worktree add -q -b b-sb "$T/wt-sb" 2>/dev/null; printf 'wt\t%s\n' "$T/wt-sb" >"$PERUN_LEDGER"
SB="$(dirname "$S")/session_brief.py"; out=$(cd "$R" && PERUN_SOURCE=/nonexistent python3 "$SB" </dev/null)
ok $(grep -q "1 leftover(s) this machine" <<<"$out"; echo $?) "session_brief reports the ledger leftover count: $out"
echo "Tests: $pass/$((pass+fail))"; [ "$fail" = 0 ]
