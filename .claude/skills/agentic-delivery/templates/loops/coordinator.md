# Coordinator loop

Fill `<angle-bracket>` placeholders. Cadence: every 30 minutes, or on an event (a lane hand-back, a PR going
ready). Never faster than 20 minutes: a tighter tick burns tokens for no new information.

Token policy (`python3 perun_policy.py get tokens`): `efficient` (default) means: use the cheapest model tier that fits, no duplicate review passes, terse hand-backs (guidance, not enforced), and at most 2 parallel lanes (enforced: `perun_policy.py lanes` and `heavy-slots` apply the cap); `maximize` (maximum pace) lifts the cap; a number caps lanes at that many (it is not a token budget). Apply it when dispatching lanes. At maximum pace pick a stronger model only for a hard step and keep the waste filter (`templates/lane-preamble.md` **Drive to the goal**).

## /loop prompt (copy-paste)

```
/loop 30m Coordinator wake. Run this checklist once, in order, then stop; do not re-poll inside a wake.
0. WIP first: `python3 .claude/skills/agentic-delivery/scripts/landing_watchdog.py check`; a `WIP:` or `Landing stalled`
   line means drain (review, land) before spawning anything new.
1. Activity: list new issue/PR activity since the last wake. Match on issue number plus a keyword set
   (URGENT, regression, blocked), never by author: peers share one account.
2. Peers: read each machine's free-lane count from the coordination issue. Run
   `ROOT=<repo-root> bash .claude/skills/agentic-delivery/scripts/reap_own.sh --report`; an idle peer while
   `lane:<machine>` issues wait is a finding: label or assign, per the pull-queue doctrine
   (references/multi-session-coordination.md). Host: `python3 .claude/skills/agentic-delivery/scripts/host_probe.py
   --lane-type cpu --live-lanes "$(python3 .claude/skills/agentic-delivery/scripts/perun_policy.py heavy-load)" --max-lanes "$(python3 .claude/skills/agentic-delivery/scripts/perun_policy.py lanes)"` (add `--lane-type heavy` before a heavy local command: same verdicts; slots = `perun_policy.py heavy-slots`); `HOLD` or `COULD_NOT_CHECK` means start no new lane this wake, and say so on the board.
3. Trains: for the green, reviewed PRs on one base, run
   `bash .claude/skills/agentic-delivery/scripts/train_land.sh <tag> <pr> [pr...]`. One PR is a valid train; any
   wait for a second PR is launcher policy (deep-code-review references/merge-operations.md, "Merge-train fast path").
4. Cleanup: `ROOT=<repo-root> bash .claude/skills/agentic-delivery/scripts/reap_own.sh` then
   `ROOT=<repo-root> bash .claude/skills/agentic-delivery/scripts/clean_finished.sh`. Verify servers are dead
   (`reap_own.sh --report` prints orphans=0), worktrees removed, merged branches deleted.
5. Tracker (only if the repo has a work tracker, references/work-tracking.md): run
   `python3 .claude/skills/agentic-delivery/scripts/tracker_check.py` and fix or board-post each finding. Once a
   week, run `python3 .claude/skills/agentic-delivery/scripts/tracker_weekly_update.py` and hand the draft to the
   project DRI to post; never post it unread. A `NOT CHECKED` line is a finding, not a pass.
6. Board: post one status update (what landed, what is in flight, what is blocked, who owns each).
Idle only after `python3 .claude/skills/agentic-delivery/scripts/lane_liveness.py --worktree <lane-worktree>` reports no ALIVE or QUIET lane
(one call per lane worktree); a HOLD with live lanes is not idle: say "draining". Then say so in one line and end the wake.
```

## Scheduled-task template

```
name: coordinator-wake
schedule: every 30 minutes   # or trigger on lane hand-back; never under 20 minutes
prompt: <the text after "/loop 30m" above>
working_dir: <repo-root>
```
