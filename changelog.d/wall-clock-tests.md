### Added
- agentic-delivery: `clock_lint.py` now prints an advisory finding for day/week-relative text asserted in a py/js test with no fixed clock (for example "No demos yet this week"); Playwright `setFixedTime` / `clock.install` / `clock.pauseAt` silence only that advisory. Test: `scripts/test_clock_lint_reltext.py`.
size-budget-raise: .claude/skills/deep-code-review/references/testing-situational.md 41440→41728 clock_lint day/week-relative text advisory routed from the wall-clock bullet
