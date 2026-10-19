### Added
- `premise_check.py N [N ...]` (tests: `scripts/test_premise_check.py`, registered in `scripts/ci-tests.d/premise-check.sh`): run before handing PRs or issues to a lane or peer, and on receipt. One `gh api repos/<slug>/issues/N` read per number prints `#N PR MERGED|CLOSED|OPEN` or `#N ISSUE OPEN|CLOSED`; an open issue also lists the backticked file paths and `name()` / snake_case symbols its body cites that the checkout's HEAD does not contain (`absent at HEAD: ...`). Exit 1 when any number is merged, closed, drifted or unreadable. Reads only. Field cause: 5 of 5 PRs sent to a peer had already merged and 2 of 3 handed issues cited things that had drifted from HEAD. `multi-session-coordination.md` names it in its script list and in the peer-handed work-partition rule.

### Verified, no change
- `heavy_gate.py` already holds only commands matching a heavy pattern (test runners and builds, quote- and heredoc-aware; `--version`, `--help`, `--collect-only` and `playwright install` are never heavy), so a light command is not held by the host-load gate; a heavy-classified command on a busy host is still held by design.

size-budget-raise: .claude/skills/INDEX.md 11307→11429 premise_check.py added to the script and No-documented-CLI index
size-budget-raise: .claude/skills/agentic-delivery/references/multi-session-coordination.md 71643→72082 premise_check.py script entry and partition-rule pointer
