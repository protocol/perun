### Added
- idea-critic: `veche.py` returns `default_action` (proceed when `--reversibility easy`, else hold) and a `COUNCIL_BLOCKING_WORK` alarm when a council cannot decide or runs past `--alarm-s`; seats of each round run in parallel with atomic cap accounting and a failed seat is dropped; critique rounds add an anonymized Borda `peer_ranking`; a malformed `--criteria` error shows the `name:weight` format.

size-budget-raise: .claude/skills/idea-critic/references/council.md 6098→8433 timebox and alarm section, peer ranking and parallel seats notes, and a compact gap table versus the fetched open-source councils
