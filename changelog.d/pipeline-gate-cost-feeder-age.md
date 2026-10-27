The delivery pipeline tooling gains three measurements. `landing_watchdog.py` warns when the p50 or p90 age of green waiting PRs passes policy `ready_age_p50_h` or `ready_age_p90_h`. `feeder_order.py` orders a work queue so a fix for a recurring ledgered failure class runs before features. `pipeline_profile.py tests --run` prices each test script before batch size or workers are tuned. The procedure is in `references/pipeline-optimizer.md`.

size-budget-raise: .claude/skills/agentic-delivery/references/pipeline-optimizer.md 17583→18717 one section for per-test gate cost, fix-before-feature order and ready-PR age
size-budget-raise: .claude/skills/INDEX.md 14021→14148 one generated index row for feeder_order.py
size-budget-raise: .claude/skills/agentic-delivery/INDEX-scripts.md 14140→14323 one generated index row for feeder_order.py
