### Added
- review_checks.sh routes two more installed tools, each NOT CHECKED when missing and not run on a crash, empty output, wrong-shape output or an exit that disagrees with the report, never a silent clean: mobsfscan (Android and iOS source, only in a repo with a mobile marker) and psalm (PHP taint analysis, only with a root psalm.xml that the diff did not change). Non-JSON log lines around the report are skipped. tool-hub.md and standards-index.md document the rows and log the sources fetched 2026-11-12.

size-budget-raise: .claude/skills/deep-code-review/references/tool-hub.md 37939→40570 hub rows for mobsfscan and psalm
