### Added
- Whole-project security reports gain a `## Findings` format (`[<class>] <path>:<line> <severity>: <text>`, fixed class vocabulary, one primary cite per finding). `report_contract_lint.py` adds `finding-no-class` and `finding-multi-cite`, accepts `path:12,15,20` line lists and `-` (stdin) as REPORT; `security-review-mode.md` pipes the draft through it before emitting.
