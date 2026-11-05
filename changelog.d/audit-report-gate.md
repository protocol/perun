### Added
- Plugin Stop hook (`hooks/hooks.json` -> `scripts/audit_report_gate.py`) lints a whole-app security audit's final report with `report_contract_lint.py` and blocks delivery once when it fails, because about half of agentic audits ignored the template prose and hand-wrote a free-form table. It allows the stop when the message has fewer than 5 `path:line` cites, the session did not Read (or run Bash on) `security-review-mode.md` since the last human prompt (a PostToolUse marker stands in when the transcript file is never written), stdin is malformed, or the hook already fired once. Tests in `scripts/test_audit_report_gate.py`.
- size-budget-raise: .claude/skills/deep-code-review/references/security-review-mode.md 13449→13589 one sentence naming the Stop hook
- size-budget-raise: .claude/skills/INDEX.md 17503→17629 regenerated index rows for audit_report_gate.py
- size-budget-raise: .claude/skills/deep-code-review/INDEX-scripts.md 8259→8523 index row for audit_report_gate.py
