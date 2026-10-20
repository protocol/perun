### Changed
- CI: a slow per-PR test can register as `scripts/ci-tests.d/<slug>.bg.sh`; it starts right after checkout and runs alongside the gate steps, and the "Per-PR tests" step waits for it and fails on its exit code. The pre-push CI-parity test (about 500 of the step's 700 seconds) moves there, taking the job back under its 25-minute ceiling instead of timing out.
