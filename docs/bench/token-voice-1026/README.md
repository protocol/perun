# Token-voice bench: does Perun beat caveman and ponytail on output tokens?

Answer (Haiku 5.5, one model, 60 hidden-test bug-fix tasks x 2 samples x 4 arms = 480 calls, $0.39 total): yes on this
setup. Perun's reply-budget text cut median completion tokens 39% vs no voice prompt, 30% vs caveman ultra and 59% vs
ponytail, with pass rate not lower. Paired 95% CIs exclude zero on all three comparisons.

| arm | median output tokens / task | mean | pass rate (95% CI) | total output tokens | total cost |
|---|---|---|---|---|---|
| none | 995 | 1396 | 0.958 (0.900-1.000) | 167,526 | $0.0962 |
| caveman (ultra) | 976 | 1296 | 0.975 (0.933-1.000) | 155,513 | $0.0917 |
| ponytail | 1647 | 1997 | 0.983 (0.958-1.000) | 239,615 | $0.1346 |
| perun | 667 | 920 | 0.983 (0.950-1.000) | 110,390 | $0.0699 |

Paired differences (per-task, over 60 tasks; bootstrap 10,000 resamples, seed 1; tokens = median, pass = mean):

| A vs B | median token diff (95% CI) | ratio | pass diff (95% CI) | frozen keep rule |
|---|---|---|---|---|
| perun vs none | -356 (-493 to -292) | 0.61 | +0.025 (0.000 to +0.067) | win |
| perun vs caveman | -292 (-355 to -245) | 0.70 | +0.008 (-0.025 to +0.050) | win |
| perun vs ponytail | -919 (-1088 to -852) | 0.41 | 0.000 (-0.025 to +0.025) | win |
| caveman vs none | -62 (-104 to -21) | 0.95 | +0.017 (0.000 to +0.042) | n/a |
| ponytail vs none | +583 (+470 to +676) | 1.57 | +0.025 (0.000 to +0.058) | n/a |

Keep rule (frozen): Perun wins iff the tokens CI upper bound is < 0 and the pass-rate CI lower bound is > -0.05.
Quality check: every arm passes 95.8-98.3% of the hidden tests, no truncations and no no-code replies, so the arms are
equal on task success within noise (all pass CIs overlap; no pass diff is below zero).

## Caveats (read before citing)

- One model (Haiku 5.5, thinking disabled), one task family (small Python bug fixes, no tools). Not a claim about agentic
  sessions, other models or long outputs.
- Perun arm is its shipped reply-budget line plus the zero-chat rule only; it is a hard length cap, so a token win
  against uncapped arms is expected. Ponytail's SKILL.md invites extra prose and tests, which inflates its tokens here.
- Cost is the CLI-reported list cost. It includes input: perun/caveman/ponytail system prompts are larger than none,
  and output tokens are still the main driver of the ordering.
- Ceiling: pass rates are near 100%, so the quality check has little power to see small regressions.
- Deviation from the preregistration: the frozen run targeted a free PCSS model; budget exhausted (HTTP 429). The frozen
  files are unchanged; `run_claude.py` and `cost.py` are new (not in `SHA256-frozen.txt`). Disclosed as a `deviation`
  event in `ledger.jsonl`. The model, so absolute numbers, differ from the PCSS design.

## Reproduce

`python3 results.py` and `python3 cost.py` regenerate `results.json` and `cost.json` from `runs.jsonl` offline.
`python3 run_claude.py --samples 2 --jobs 6 --cap 12` re-runs the paid calls (needs `claude` CLI auth; about $0.40).
Calls: `claude -p --model haiku --system-prompt <frozen prompt> --tools "" --setting-sources ""`, `MAX_THINKING_TOKENS=0`.
Spend: $0.39 of the $15 lane cap. The 5h plan-utilization gate was never approached at this volume.
