### Fixed
- `handback_cap.py` no longer counts blank lines or markdown link URLs toward the cap and keeps the three-block release valve. Test: `scripts/test_hook_friction.py`.
- `lane_resume_nudge.py` and `operating-discipline.md` now say a resumed lane's tool-call cap does not reset and a fresh lane is better for a large remainder.
- `tier_gate.py` fail-closed on a missing tiers file is pinned by test (clear message, exit 2, no FAIL line).

### Added
- Policy `lockfile_skip_review` (default `off`): with `on`, `review_gate.py check --audit-clean` skips the review lane for a lockfile-only PR.
- `testing-situational.md`: reproduce a flake under CPU throttling before calling it a flake.
size-budget-raise: .claude/skills/agentic-delivery/references/merge-queue-worktrees.md 37292→37954 documents the lockfile_skip_review policy key and the --audit-clean caller contract
size-budget-raise: .claude/skills/agentic-delivery/references/operating-discipline.md 10585→10683 states that a resumed lane's tool-call cap does not reset
size-budget-raise: .claude/skills/deep-code-review/references/testing-situational.md 40607→41440 adds the reproduce-a-flake-under-CPU-throttling method
