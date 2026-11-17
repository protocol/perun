### Changed
- review_checks.sh: a ruff-security Snnn row is dropped when bandit reports Bnnn (same number, ruff's flake8-bandit port) on the same file:line; the kept bandit row is tagged "[corroborated: bandit+ruff]". Different lines, non-twin rules and the B101-summary row are untouched.
