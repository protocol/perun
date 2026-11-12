### Added
- review_checks.sh routes flawfinder (C/C++, SARIF), cppcheck (C/C++ without a project build, XML read from its stderr) and devskim (multi-language, one file per run, SARIF) through the tool hub. Each is NOT CHECKED with an install hint when missing, counts as wired only once installed, and is not run on a crash, empty output, wrong-shape output or a non-zero exit; changed files only, no network flags needed. Licenses (GPLv2+, GPLv3, MIT) and flags were checked against sources fetched 2026-11-12 and logged in standards-index.md; tool-hub.md records what could not be verified.

size-budget-raise: .claude/skills/deep-code-review/references/tool-hub.md 43180→   45474 hub rows for flawfinder, cppcheck, devskim
