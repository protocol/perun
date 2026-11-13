### Added
- review_checks.sh routes bundler-audit (a changed `Gemfile.lock` against the local ruby-advisory-db only: with no local db it is NOT CHECKED because the tool would otherwise download one) and cfn-lint (changed CloudFormation templates, JSON, Error and Warning rows) through the tool hub. Each is NOT CHECKED with an install hint when missing, counts as wired only once installed, and is not run on a crash, empty output, wrong-shape output or an unexpected exit. Flags, exit codes and the JSON shape were read from the upstream README, CLI and formatter source fetched 2026-11-13; stub-tested only, no real tool output was run.

size-budget-raise: .claude/skills/deep-code-review/references/tool-hub.md 53056→54797 two hub rows with their verification evidence
