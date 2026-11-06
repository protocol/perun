### Added
- Whole-app audit report route inventory rows gain a `csrf=<none|token|origin|samesite|n/a>` field. `report_contract_lint.py` now fails a cookie or session POST, PUT, PATCH or DELETE row without it (`inventory-no-csrf`) and a `csrf=none` row with no matching `[csrf]` finding (`csrf-unfiled`).
- size-budget-raise: .claude/skills/deep-code-review/references/whole-project-report.md 6651→7053 csrf field in the inventory row and two linter-rule bullets
