### Added
- `repeat_poll_guard.py`: a PreToolUse(Bash) hook that nudges (never blocks) toward one detached job when the same command runs more than 3 times in a session. Test: `scripts/test_repeat_poll_and_brief_lint.py`.
- `subagent_brief_lint.py`: a PreToolUse(Agent|Task) hook that stops, once per distinct brief, a brief naming a tool the lane lacks (`Monitor`) or a lowercase built-in tool name (`bash tool`). Same test file. Both hooks are wired in the operating-layer template and `perun_doctor.py`.

### Fixed
- `destructive_guard.py` no longer blocks reviewed false positives found by replaying a heavy user's real blocks: `kill $(cat X.pid)` (pidfile in a lane-owned dir only), `pkill -P <pid>` (own process tree only) / bare `pkill -V`, `curl | python3 -c 'json.load(sys.stdin)'`, edit-script heredocs whose replacement text mentions `rm -rf`, `git worktree remove --force` of a clean tree and `git branch -D` of a pushed or merged branch. Each is pinned next to the true block it must keep (`scripts/test_destructive_fp.py`).
- `token_report.py --rollup` is one lean streaming pass per file (`rollup_session`): it parses only lines with usage and, under `--since`, skips files and lines older than the window. Output is identical to the old path (`scripts/test_token_report_rollup.py`).
