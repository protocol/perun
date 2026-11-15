### Changed
- review_checks.sh folds findings from several tools on the same file and line into one row that names every tool ("corroborated by: ..."), keeping the highest severity named in the message prefix. Different lines, one tool's own rows, not-checked rows and summary rows never fold. scripts/test-review-checks-hub-dedup.sh covers it.
