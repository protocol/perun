### Added
- agentic-delivery: `bypass_guard.py` PreToolUse(Bash) hook (wired in `operating-layer.settings.json`) denies `git commit|push|merge --no-verify`, `git commit -n`, `HUSKY=0`/`SKIP=` env prefixes and `-c core.hooksPath=`, with the fix "fix the failing hook; never bypass".
- agentic-delivery: shared `_dirty_guard.sh` (`require_clean_tree`); `train_land.sh` refuses a dirty tree up front with the exact fix, and a `test-ci-gates.sh` lint requires it in any skill shell script that runs `git checkout|switch|reset`.
- agentic-delivery: `merge_checkpoint.sh save|status` persists a stalled merge (`.git/perun-merge-state`); `session_brief.py` shows a one-line resume instruction.
- agentic-delivery: `train_land.sh` and `land_train.sh` print up front that the run lands to the base and that a host-classifier denial means stop and park for the owner, never retry or route around.
