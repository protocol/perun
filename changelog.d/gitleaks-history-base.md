### Fixed
- `review_checks.sh --history` reads `.gitleaks.toml` as of BASE, like `.gitleaksignore` and `.gitleaks-allow`, and always passes `--config`. Before, gitleaks auto-loaded the working-tree file, so a change could add an allowlist that hid secrets in its own commits.
