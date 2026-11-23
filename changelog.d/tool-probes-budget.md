### Fixed
- `test-tool-probes.sh` no longer stalls past the 900 s per-test bound on a loaded workstation. A probe that exceeds `PROBE_TIMEOUT`, or starts after the new `PROBE_BUDGET` (default 780 s) is spent, prints `NOT RUN <tool> (timeout)` or `NOT RUN <tool> (budget)` instead of a zero-row FAIL.
