# idea-critic V6 (default no-go gate): NOT RUN, no verdict (2026-10-26)

**BLUF: both free and paid backends were unavailable, so V6 has no measured false-GO rate and no evil-twin recall. The keep rule was never evaluated. `.claude/skills/idea-critic/SKILL.md` is unchanged; V5's loss (false-GO 14.1% against 4.4% for no skill, `docs/bench/idea-critic-v5-1019/README.md`) stands.**

## What was planned

V6 = revert V5's kill check, add one hard rule to the slim `SKILL.md`: "Default is no-go. Say `go` only when the proposal's own stated facts, a figure you recomputed or a cited source show it works and its named risks have an answer; a missing fact is a no-go (revise first), never an assumed go." Rerun the frozen 30-case outcome corpus (`docs/bench/idea-critic-v5-1019/corpus.json`) and the 24-flaw evil-twin R2 corpus (`docs/bench/evil-twin-r2-1021/cases.txt`) with the V5 and R2 harnesses. Keep rule: false-GO must not exceed BASE (95% CI upper bound) and evil-twin recall must not regress; otherwise REVERT.

## What blocked it

1. Free PCSS endpoint (the harness of both earlier benches): every call returned HTTP 429, `Budget has been exceeded! Team=... Max budget: 0.0` (`type: budget_exceeded`). A first attempt wrote 500 failed ledger lines and no outputs.
2. Paid fallback (`claude -p --model haiku --tools ""`, approved budget, $20 lane cap, stop at 5h plan utilization 0.8): the `rate_limit_event` already read `five_hour.utilization = 1` (`status: rejected`) and `seven_day.utilization = 0.97`. The harness's quota gate (`scripts/rival_eval.py`, `QUOTA_STOP = 0.8`) correctly stopped the run after 4 calls. About $0.02 was spent; the 4 outputs were not scored.

## What to do next

Rerun after the 5-hour window resets (the reset time is in the `rate_limit_event`), or after PCSS budget is restored. Both arms must be regenerated on one backend, because the committed V5 outputs came from three PCSS models and are not comparable to a `claude -p` run. Include the shipped slim `SKILL.md` as an arm: it, not V5, is what V6 actually changes.
