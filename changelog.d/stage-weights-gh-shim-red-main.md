Stage weights, a gh retry shim, a red-main owner alarm and a serial-test detector

- stage_run.py reads PERUN_STAGE_WEIGHTS (stage=weight) and records the weight on its heavy lease; the slot cap, and so heavy_gate.py, count it. A heavier stage waits until it fits, runs alone if it exceeds the cap, and frees its weight to waiting stages when it ends.
- scripts/gh-shim/gh is a PATH shim that retries idempotent gh reads with backoff on transient errors only; writes run exactly once.
- red_main.py reports the count of reds with no owner or fix past 1h and the oldest red age; policy keys red_uncovered_max and red_oldest_h (default 0 = off) make it exit nonzero.
- flake_ledger.py serial lists tests that fail only in the full parallel run and pass solo; the triage reference states the rule: move them to the serial project the same day.

size-budget-raise: .claude/skills/agentic-delivery/references/host-enforcement.md 43026→44133 stage weights and the gh retry shim
size-budget-raise: .claude/skills/agentic-delivery/references/red-gate-triage.md 23856→25405 green-main owner rule and the passes-alone/fails-parallel rule

Tests: test-stage-weights 4/4, test-gh-shim 12/12, test-red-main 10/10, test-flake-serial 6/6; all scripts/ci-tests.d pass
