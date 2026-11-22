### Fixed
- `templates/pre-push-verify.sh` refreshes the index (`git update-index -q --refresh`) before its dirty-tree check, so a tracked file whose mtime changed but whose content did not (a checkout, a copy, an editor save with no edit) no longer refuses the push. A real edit is still refused. New test: `scripts/test-prepush-stale-index.sh`.
- `scripts/test-provision-tools.sh` strips a trailing `/` from `TMPDIR`, so its "DIR argument" check no longer fails under the macOS default `TMPDIR`.
