### Added
- review_checks.sh gitleaks pass: optional repo-root `.gitleaks-allow` (`rule path-glob sha256-of-secret` per line) drops known false positives by content hash, read from the base ref only (a change cannot approve its own secret), so it survives history rewrites that break baseline fingerprints. The default allowlist template now also skips lockfiles. Test: `scripts/test-review-checks-gitleaks-allow.sh`.

size-budget-raise: .claude/skills/deep-code-review/references/method-situational.md 43585→43869 one sentence routing the .gitleaks-allow format
