### Changed
- The real-hub CI job now also installs pinned, checksum-verified real pmd, solhint, hadolint, bandit, ruff and actionlint and asserts each is reported as ran with its expected rule id on a fictional canary file, extending the tfsec, ansible-lint, rubocop and cfn-lint smoke so a changed flag or report shape in these six scanners fails CI instead of passing on stubs alone.
