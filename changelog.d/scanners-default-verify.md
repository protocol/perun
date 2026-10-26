### Added
- `review_checks.sh` runs trivy offline and a local `.semgrep.yml` by default when installed, adds `--history` for gitleaks over commit history, and prints an "N findings; analyzers ran; skipped" summary on stderr. `method-situational.md` adds a verify-or-drop step for scanner leads. Test: `scripts/test-review-checks-scan-summary.sh`.

size-budget-raise: .claude/skills/deep-code-review/references/method-situational.md 42574→43115 scanner verify-or-drop step
size-budget-raise: .claude/skills/deep-code-review/INDEX-scripts.md 4648→4660 new --history flag in the review_checks.sh usage row
