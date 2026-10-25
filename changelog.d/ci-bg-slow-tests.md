### Changed
- The two slowest per-PR tests, `conflict-free-prs` (about 150 s locally) and `bench-check` (about 110 s), now run as background tests (`scripts/ci-tests.d/*.bg.sh`) alongside the gate steps, so they add no serial time. PR runs had reached the 25-minute job limit.
