#!/usr/bin/env bash
# Tests for run_ledger.sh: report-only teardown list of what earlier runs recorded creating (temp fixture only; nothing outside it is touched).
set -uo pipefail
SC="$(cd "$(dirname "$0")/.." && pwd)/.claude/skills/agentic-delivery/scripts"; S="$SC/run_ledger.sh"
T=$(mktemp -d "${TMPDIR:-/tmp}/run-ledger.XXXXXX"); T=$(cd "$T" && pwd -P)
pass=0 fail=0; PIDS=""
ok() { if [ "$1" = 0 ]; then pass=$((pass+1)); else fail=$((fail+1)); echo "FAIL: $2"; fi; }
cleanup() { for p in $PIDS; do kill "$p" 2>/dev/null; done; [ -d "$T/repo" ] && git -C "$T/repo" worktree prune; }
trap cleanup EXIT
export PERUN_LEDGER_DIR="$T/runs" GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
R="$T/repo"; git init -q -b main "$R"; git -C "$R" commit -q --allow-empty -m base; git -C "$R" update-ref refs/remotes/origin/main HEAD
# gh stub: branches b-merged*, b-dirty, b-held and b-mine have a merged PR at their current head; b-fresh and b-active have no PR
cat >"$T/gh" <<'GHEOF'
#!/usr/bin/env bash
echo "${REAP_OWN_SOURCE_ONLY:-unset}" >"$PROBE"; bash "$SCDIR/reap_own.sh" --report >"$PROBE.reap" 2>&1   # what a child sees while run_ledger.sh runs
case "$3" in b-merged*|b-dirty|b-held|b-mine) echo "MERGED $(git rev-parse "refs/heads/$3")" ;; esac
GHEOF
chmod +x "$T/gh"; export GH="$T/gh" PROBE="$T/probe" SCDIR="$SC"
for w in merged unrecorded dirty held fresh active mine; do git -C "$R" worktree add -q -b "b-$w" "$T/wt-$w" 2>&1 >/dev/null; done
git -C "$R" worktree add -q -b b-merged-b "$T/wt-merged-b" 2>&1 >/dev/null
echo x >"$T/wt-dirty/f"; git -C "$T/wt-active" commit -q --allow-empty -m wip
(cd "$T/wt-held" && exec sleep 300) & PH=$!; sleep 300 & PA=$!; sleep 300 & PB=$!; sleep 300 & PC=$!; sleep 300 & PD=$!; PIDS="$PH $PA $PB $PC $PD"

# recording: needs a run id; refuses empty / bad paths and pids
env -u PERUN_RUN_ID -u CLAUDE_SESSION_ID bash "$S" record-worktree "$T/wt-merged" 2>/dev/null; ok $((! $?)) "record without a run id is refused"
export PERUN_RUN_ID=runA
for w in merged dirty held fresh active; do bash "$S" record-worktree "$T/wt-$w"; done
bash "$S" record-pid "$PA"
PERUN_RUN_ID=runE bash "$S" record-pid "$PC"   # a concurrent run's live server
bash "$S" record-worktree "$T/nope" 2>/dev/null; ok $((! $?)) "record of a non-directory is refused"
bash "$S" record-worktree "" 2>/dev/null; ok $((! $?)) "record of an empty path is refused"
bash "$S" record-worktree "$R" 2>/dev/null; ok $((! $?)) "record of the main checkout is refused"
bash "$S" record-pid abc 2>/dev/null; ok $((! $?)) "record-pid of a non-number is refused"
PERUN_RUN_ID='../x' bash "$S" record-pid "$PA" 2>/dev/null; ok $((! $?)) "run id with a slash is refused"
printf 'wt\t\nwt\t%s\nwt\trelative/dir\npid\t\t\t\npid\t1\t0\tx\npid\t%s\t0\twrong command and cwd\n' "$R" "$PB" >>"$T/runs/runA.tsv"   # hostile rows: empty var, main checkout, relative, empty pid, pid 1, reused pid


snap() { { cat "$T"/runs/*.tsv; git -C "$R" worktree list; (cd "$T" && find . -path ./repo -prune -o -print | sort); for p in $PH $PA $PB; do kill -0 "$p" 2>/dev/null && echo "$p alive"; done; } | shasum; }
export PERUN_RUN_ID=runC   # the running session: its own finished-looking worktree must never be listed
bash "$S" record-worktree "$T/wt-mine"; bash "$S" record-pid "$PD"   # the running session's own server
before=$(bash "$S" --count); s0=$(snap); rep=$(bash "$S"); s1=$(snap); echo "$rep"
ok $([ "$s0" = "$s1" ]; echo $?) "report mode changes nothing (ledgers, worktrees, files, processes)"
ok $([ "$before" = 3 ]; echo $?) "count before = 3 (merged worktree + 2 recorded pids), got $before"
ok $(grep -qE "kill $PC +# run runE" <<<"$rep"; echo $?) "a concurrent run's live pid is listed, labelled with its run id"
ok $(! grep -qE "kill $PD " <<<"$rep"; echo $?) "the current run's own pid is never listed"
ok $([ "$(cat "$T/probe")" = unset ] && grep -q "orphans=" "$T/probe.reap"; echo $?) "REAP_OWN_SOURCE_ONLY does not leak: a child reap_own.sh run during the report works"
ok $(grep -qF "worktree remove $T/wt-merged" <<<"$rep"; echo $?) "merged clean recorded worktree gets a removal line"
ok $(grep -qF "kill $PA " <<<"$rep"; echo $?) "recorded live pid gets a kill line"
for w in unrecorded dirty held fresh active mine; do ok $(! grep -qF "$T/wt-$w" <<<"$rep"; echo $?) "wt-$w is never listed as removable"; done
ok $(! grep -qE "kill ($PB|$PH)" <<<"$rep"; echo $?) "unrecorded pid and reused-pid row are never listed"
ok $(! grep -qF "$T/wt-merged-b" <<<"$rep"; echo $?) "a worktree no ledger recorded is never listed"

ok $(PERUN_RUN_ID=runZ bash "$S" 2>/dev/null | grep -qF "$T/wt-mine"; echo $?) "control: wt-mine IS listed to any other run, so the exclusion above is real"

# REPORT unset or 0 in the environment never turns the report into a removal; clean_finished.sh refuses ONLY without REPORT=1
printf '%s\n' "$T/wt-merged" >"$T/only"
REPORT=0 bash "$S" >/dev/null 2>&1; env -u REPORT bash "$S" >/dev/null 2>&1
ONLY="$T/only" bash "$SC/clean_finished.sh" >/dev/null 2>&1; rc1=$?; ONLY="$T/only" REPORT=0 bash "$SC/clean_finished.sh" >/dev/null 2>&1; rc2=$?
ok $([ -d "$T/wt-merged" ] && [ "$rc1" = 2 ] && [ "$rc2" = 2 ]; echo $?) "planted merged worktree survives with REPORT unset/0 (rc $rc1 $rc2)"

# the owner applies the printed lines; the count at session start drops
while read -r l; do case "$l" in "#"*|leftover=*|"") ;; kill*) kill "$(awk '{print $2}' <<<"$l")" ;; *) eval "$l" ;; esac; done <<<"$rep"
sleep 0.3; after=$(bash "$S" --count)
ok $([ "$after" = 0 ]; echo $?) "count after applying the lines = 0, got $after"
ok $([ -d "$T/wt-unrecorded" ] && [ -d "$T/wt-dirty" ] && [ -d "$T/wt-fresh" ] && kill -0 "$PB"; echo $?) "everything not listed survived"
echo "leftover count at session start: before=$before after=$after"

# session_brief surfaces the count at session start
git -C "$R" worktree add -q -b b-merged-sb "$T/wt-merged-sb" 2>/dev/null; PERUN_RUN_ID=runD bash "$S" record-worktree "$T/wt-merged-sb"
out=$(cd "$R" && PERUN_BRIEF_BUDGET=60 PERUN_SOURCE=/nonexistent python3 "$SC/session_brief.py" </dev/null)
ok $(grep -q "1 leftover(s) this machine" <<<"$out"; echo $?) "session_brief reports the ledger leftover count: $out"
echo "Tests: $pass/$((pass+fail))"; [ "$fail" = 0 ]
