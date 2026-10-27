### Added
- agentic-delivery: hermetic-env lint (`scripts/hermetic_env_lint.py`, frozen baseline of 11 existing offenders) fails a test of a host-reading script that pins no host env, and `scrub_env.sh` now also unsets systemd/session env. `bypass_guard.py` denies a lane writing `.perun/approvals/` (gate overrides are human-only), and the lane preamble says so. Slot floors scale with cores (`slot_floor`), a fan-out waits for its floor instead of shrinking (`fanout_workers`), and `ci-gates.sh` privacy scan uses the core count for `xargs -P`. `lkg.py` records the runner blob and refuses or rejects a receipt from a stale `run-ci-tests.sh`.

size-budget-raise: .claude/skills/agentic-delivery/references/fanout-host-sizing.md 48424→48845 one paragraph: core-scaled fan-out floor, wait not shrink
size-budget-raise: .claude/skills/agentic-delivery/references/gate-epistemology.md 11398→11800 one paragraph: receipt records its runner blob
