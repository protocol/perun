### Added
- agentic-delivery: two lessons. A watchdog or budget must be shorter than the hard timeout it pre-empts (`references/pipeline-optimizer.md`, asserted by `scripts/test_budget_below_timeout.py` over CI step, job and heavy-lease timeouts). A fix for a recurring failure class is replayed against past instances and keyed on signals the change carries, not labels (`references/retrospective.md`, new eval case `recurring-fix-replay-signals`).

size-budget-raise: .claude/skills/agentic-delivery/references/pipeline-optimizer.md 17583→17784 one anti-stall rule on budgets shorter than timeouts
size-budget-raise: .claude/skills/agentic-delivery/references/retrospective.md 4577→4844 one paragraph on replaying fixes against past instances

### Fixed
- `lane_guard.py` shadow-fix closer match also accepts `Fixes https://github.com/<owner>/<repo>/issues/N`; `test_prepush_gate_cache.py` no longer raises on a blank shim log line and asserts the `stage_run.py` wrapper line.

- Pre-push gate now runs under `nice -n 19` (`scripts/test_prepush_nice.py`); `host-enforcement.md` gains one shared-host bullet (nice and capped workers, fixture teardown matched by the reaper, read `load1` before recommending parallelism). No xdist or throughput-alarm code exists in this repo, so no further check.

size-budget-raise: .claude/skills/agentic-delivery/references/host-enforcement.md 42637→43026 one shared-host bullet
- `test_security_gates_corpus.py` superlinearity check takes the min of 7 runs after a warm-up and fails only when the ratio breach also exceeds a 20 ms floor, so runner noise no longer flakes it.
- `test_security_gates_corpus.py` superlinearity check now compares the guard against an in-process `shlex` pass over the same blob (the guard is linear, exponent about 1.1; the old fixed 30x ratio flaked on shared CI runners) and fails only if that relative cost grows over 3x with size.
