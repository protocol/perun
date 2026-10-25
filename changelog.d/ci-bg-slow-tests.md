### Changed
- The two slowest per-PR tests, `conflict-free-prs` (about 150 s locally) and `bench-check` (about 110 s), now run as background tests (`scripts/ci-tests.d/*.bg.sh`) alongside the gate steps, and the CI job timeout rises from 25 to 35 minutes. Green PR runs took about 23.5 minutes, so slower runners hit the 25-minute limit.
