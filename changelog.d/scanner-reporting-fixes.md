### Fixed
- `review_checks.sh` keeps every temp file (raw rows, scanner output, gitleaks config/report, semgrep HOME, audit dirs) in one private `mktemp -d` dir per run, removed on exit, so concurrent runs sharing `$TMPDIR` cannot touch each other's files.
- `review_checks.sh` no longer reports semgrep as "not run (partial scan)" while emitting its findings: a partial scan prints `partial: semgrep ran but reported errors` and keeps the findings.
- `review_checks.sh` finds `tsc` in `node_modules/.bin/tsc` (cwd or git toplevel only; run only when REVIEW_TEST_CMD is set, since it executes project code) when it is not on PATH, instead of reporting it not installed.
- `supply_chain_check.sh` reports zizmor/actionlint as `n/a` when the repo has no workflow files; INCOMPLETE only when workflows exist and the tool is missing.
New test `scripts/test-scanner-reporting-fixes.sh`; `test-supply-chain-check.sh` and `test-review-checks-security-folds.sh` updated to the new wording.
