### Fixed
- scripts/ci-tests.d/low-context-index.sh now stops at its first failing test (`set -e`), so a bare `bash` run no longer reports only the last command's status and hides a failing size gate; scripts/test-ci-tests-d-masking.sh is the regression. security-review-mode.md is trimmed back under its size budget with no rule removed.
