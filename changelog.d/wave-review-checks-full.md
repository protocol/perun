### Added
- deep-code-review `review_checks.sh --full`: scan every tracked file against git's empty tree (one batched gitleaks run over the working tree), with no synthetic base needed. gitleaks now drops fingerprints listed in the repo's `.gitleaksignore` (read as of BASE, HEAD under `--full`) in both modes, and a missing gitleaks lands as a `not-checked` row. `perun_policy.py` is now located from the script's resolved dir. Tests: `scripts/test-review-checks-full.sh`.

size-budget-raise: .claude/skills/deep-code-review/references/tool-hub.md 4994→5260 documents --full mode and .gitleaksignore handling
