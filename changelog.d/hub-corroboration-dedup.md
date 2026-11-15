### Changed
- review_checks.sh marks findings that several tools report on the same file and line: every such row gets a `tools` list and a "[corroborated by: ...]" message suffix. No row is dropped or merged, so per-tool row consumers are unaffected. scripts/test-review-checks-hub-dedup.sh covers it.
