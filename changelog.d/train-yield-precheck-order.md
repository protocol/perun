Merge-train tooling now reports landing yield, not just merge rate. `train_land.sh` records each started train through the new `train_yield.py`, and `landing_watchdog.py` warns when fewer than half the recent trains landed a PR or one PR re-rode 5 or more trains, saying it points at infra (timebox or load) rather than the PR. `land_ready.py` logs the `feeder_order.py` priority order it would sweep in (shadow by default; `PERUN_PRECHECK_ORDER=on` applies it) so fixes are not starved of a receipt check. The procedure is in `references/pipeline-optimizer.md`.

size-budget-raise: .claude/skills/agentic-delivery/references/pipeline-optimizer.md 18717→19151 one bullet for train yield and receipt order
size-budget-raise: .claude/skills/INDEX.md 14148→14274 generated index row for train_yield.py
size-budget-raise: .claude/skills/agentic-delivery/INDEX-scripts.md 14323→14489 generated index row for train_yield.py
