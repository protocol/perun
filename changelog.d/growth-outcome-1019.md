### Added
- `docs/bench/growth-outcome-1019`: preregistered outcome bench for growth-analytics against the marketingskills analytics and ab-testing rival and no skill. 88 synthetic A/B readouts plant 0 to 3 of six analysis errors (sample ratio mismatch, peeking, underpowered, Simpson's paradox, wrong denominator, novelty effect) against an answer key hashed before generation; answers are scored by regex, no model grader. Result, run once: planted-error recall shipped 0.987 [0.967, 1.000], rival 0.988 [0.973, 1.000], no skill 0.979 [0.954, 1.000]; shipped minus rival -0.001 [-0.024, +0.019]. NOT A WIN by the preregistered rule (all arms near a recall ceiling); false alarms, benign pass and tokens were not worse. No SKILL.md change. Tests: `scripts/test_growth_outcome_1019.py`, registered in `scripts/ci-tests.d/growth-outcome-1019.sh`.

### Changed
- `docs/perun-vs-rivals.md`: one outcome-metric audit row for `growth-outcome-1019`.
