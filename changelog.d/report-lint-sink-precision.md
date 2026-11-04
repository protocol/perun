### Added
- `report_contract_lint.py` rules `finding-not-on-sink` (a `ssrf`, `tls-off`, `outbound-timeout`, `secret-in-url`, `secret-in-log`, `pii-in-log` or `cookie-flags` finding whose cited line +-2 shows no matching sink) and `class-mismatch` (`pii-in-log` that logs a credential should be `secret-in-log`; one with an outbound call and no log call should be `pii-data`). Tests in `scripts/test_report_contract_lint_sink.py`.

### Changed
- `whole-project-report.md` tells the author to cite the sink, file one finding per issue, rate-limit only brute-forceable or costly handlers, and never cite token generators or limiter definitions.

size-budget-raise: .claude/skills/deep-code-review/references/whole-project-report.md 4772→5593 sink-citation and false-positive guidance for the class vocabulary
