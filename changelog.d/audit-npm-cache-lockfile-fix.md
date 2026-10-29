### Fixed
- `review_checks.sh`: the dependency-scan fallback sets `npm_config_cache` to a per-run temp dir when it is unset, so `npm audit` no longer fails with EPERM when `~/.npm` holds root-owned files; an exported value is left alone. New cases in `scripts/test-review-checks-dep-fallback.sh`.
- `full-audit.md`: lockfile-only dependency fix recipe (`npm audit fix --package-lock-only --ignore-scripts`, a range bump via `npm install <pkg>@<range> --package-lock-only --ignore-scripts`, re-run `npm audit --package-lock-only`), and a PR-body rule: claim "CI will run X" only when a workflow runs it, else ask reviewers to run the exact test command. New eval `audit-pr-body-ci-claim`.

size-budget-raise: .claude/skills/deep-code-review/references/full-audit.md 7635→8092 lockfile-only fix recipe and PR-body CI-claim rule
