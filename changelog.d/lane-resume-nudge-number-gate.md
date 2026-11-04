### Fixed
- `lane_resume_nudge.py` no longer advises resuming an earlier lane when both lane descriptions contain 3+-digit numbers and the two number sets are disjoint (for example "Lint sweep PR 9900" versus "Lint sweep PR 9919"), which scored a 0.5 word overlap despite being different tasks.
