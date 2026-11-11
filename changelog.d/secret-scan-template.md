### Added
- templates/secret-scan.yml: opt-in free secret-scan workflow (pinned gitleaks with sha256, SHA-pinned checkout, PR base..head scan, full-history on push/weekly/dispatch, `.gitleaksignore` for false positives), routed from references/review-config.md and pinned by scripts/test-secret-scan-template.sh.

size-budget-raise: .claude/skills/deep-code-review/references/review-config.md 6472→6888 secret-scan template route
