### Fixed
- `review_checks.sh`: the per-file `B101-summary` and `F821-summary` rows of a test file now carry the `test-path` hint and the ` [test-path]` suffix, as the per-row findings already did.
- `run-ci-tests.sh --affected`: an always-run `scripts/ci-tests.d` test that a changed file also selects prints its reason once, not twice; the `always=` comment now states the replay it came from.
- `scripts/test-review-checks-full.sh` runs `review_checks.sh` on a minimal `PATH` (stub scanners, `/usr/bin`, `/bin`), so locally installed scanners no longer run on the stub repo and stall the test.
