### Added
- `templates/gitleaks.toml` for the review skill: default gitleaks rules plus a skip list for `.history/`, test-fixture dirs and registry JSON. `review_checks.sh` passes it with `--config` only when the target repo has no `.gitleaks.toml`.
- `install.sh` treats the first host's skill copy as canonical and fails, naming the copy, if any other host's vendored copy differs.
size-budget-raise: .claude/skills/deep-code-review/references/method-situational.md 42574→42794 one-line pointer to the gitleaks allowlist template
