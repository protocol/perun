### Fixed
- agentic-delivery: the train's test-id comparisons share one normalizer (`train_flake.sh --norm`: strips trailing whitespace and CR, nothing else). An id printed with a trailing space or CRLF used to miss its clean twin, so the culprit bisect read every PR as clean and landed nothing.

### Added
- agentic-delivery: `merge_train.py merge --apply` posts commit status `perun/train-gate`=success on a member head right before merging it, and overwrites it with `error` if that merge fails (`verify` and dry-run post nothing; a failed post is a loud `WARN`, never claimed posted; `--no-status` opts out), and `operating_selfcheck.py` warns when the base branch does not require that status (unknown reads `COULD_NOT_CHECK`). Requiring the context makes the train the only thing that can vouch for a merge.

size-budget-raise: .claude/skills/agentic-delivery/references/merge-queue-worktrees.md 36379→37121 documents the one-time perun/train-gate required-check step
