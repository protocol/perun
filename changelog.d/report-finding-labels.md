### Added
- Whole-project security reports gain a `## Findings` format (`[<class>] <path>:<line> <severity>: <text>`, fixed class vocabulary, one primary cite per finding). `report_contract_lint.py` adds `finding-no-class` and `finding-multi-cite`, accepts `path:12,15,20` line lists and `-` (stdin) as REPORT; `security-review-mode.md` pipes the draft through it before emitting.

size-budget-raise: .claude/skills/deep-code-review/references/security-review-mode.md 11605→11809 step 5 names the Findings format and pipes the draft through the report linter
size-budget-raise: .claude/skills/deep-code-review/references/whole-project-report.md 1880→3386 adds the Findings line format, class vocabulary and the two new lint rules
