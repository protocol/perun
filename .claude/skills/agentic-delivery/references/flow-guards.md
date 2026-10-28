# Flow guards: finding_guard, fitness_tick, flow_alarm (canonical)

Read this when: wiring or tuning the issue-dedupe hook, the per-fix fitness check, or the delivery-flow alarms. Other files link here; they do not restate it.

**Search before you file (`finding_guard.py`).** A hit on a closed issue or PR is a regression to reopen, not a new filing. The operating-layer PreToolUse hook runs `file_finding.py` on every `gh issue create --title` and denies a match. Override with `# finding-force: <reason>` in the command; a failed search fails open.

**Every fix ships one executable fitness check (`fitness_tick.py`).** Put it in `.perun/fitness/` (exit 1 plus a one-line reason on failure). The loop runs `python3 .claude/skills/agentic-delivery/scripts/fitness_tick.py` each tick and prints `ALARM name: reason`. Close the fix only when `fitness_tick.py closable NAME` passes: 2 consecutive real passing ticks and a real caller, meaning a hook/settings/package JSON, CI workflow, shell script or Makefile line that runs the tick, or a loop entry (`loop.md`, a `routines/` file) whose line starts with the command. A prose or comment mention is not a caller.

**One symptom alarm, not a monitor per invariant (`flow_alarm.py`).** Each tick run `flow_alarm.py symptom`: ready PRs but nothing merged in 2h, or `--red-since` trunk red over 1h. **Stop starting:** the same script is a PreToolUse hook that denies `gh pr create` while 5 or more PRs sit ready-but-unmerged (`PERUN_STOP_STARTING_READY`; override `# priority: <reason>`), because waiting work is queue. **Measure before optimizing agents:** `flow_alarm.py split export.json` prints median waiting-to-start, coding and ready-to-merged hours and the largest stage.

**Freeze (`freeze_gate.py`, `freeze_hook.py`).** A freeze is a file (`.perun-freeze`, `<git-common-dir>/PERUN_FREEZE` or `$PERUN_FREEZE`). Pre-push runs `freeze_gate.py BASE HEAD` (deletions and `Red-Trunk-Fix:` commits only); the fail-closed PreToolUse hook `freeze_hook.py` also denies `git push` and `gh pr merge` while the file exists. Lift the freeze by removing the file.
