### Fixed
- `train_land.sh` bisect no longer lands regressions or blames flakes: each real browser failure is re-run in isolation through `train_flake.sh` (`FLAKE_RUNS`/`FLAKE_REAL_AT`); a PR is dropped only when it fails the id alone, flaky-only bisects print `FLAKY` with no blame, and any failure that is pre-existing on the base or not pinned to a culprit prints `CANT` and lands nothing (exit 3).
- `reap_own.sh --report` prints `orphans=COULD_NOT_CHECK` (exit 2) when pgrep or lsof fail, never a false `orphans=0`; `session_brief.py` prints `NOT CHECKED` lines for unreadable versions, merged-worktree lists and dev-server scans instead of staying silent.
- `handback_cap.py` blocks a hand-back while a `git push` (pre-push hook) from the lane's worktree is still running; the lane preamble states a lane owns its background work until it completes.

size-budget-raise: .claude/skills/agentic-delivery/references/merge-queue-worktrees.md 69576→69952 document the CANT rule for the train bisect
