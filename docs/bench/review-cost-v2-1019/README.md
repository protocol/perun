# review-cost-v2-1019

Preregistered held-out review-cost bench; method in `PREREGISTERED-V2.md`, result in `results-heldout.json`, deviations in `DEVIATIONS.md`.

## Harness caveat (added 2026-10-23, after the run)

`confirm.py` runs the TK arm and the V2 arm with `--system-prompt`, which replaces the whole Claude Code system prompt. The V2s and BASE arms run on the default harness plus a cold environment prefix (the skill sits in the workspace). Any cost ratio of V2s or BASE against TK therefore mixes method cost with harness cost.

Only V2 against TK is harness-matched, and V2 was reverted and never shipped, so no row below is the shipped `/review`. Mean dollars per review from `ledger.jsonl` (the 22 non-error calls per arm, tags `ARM/case/attempt`):

| Arm | Harness | Mean USD per review | Against TK |
|---|---|---|---|
| TK | `--system-prompt` | 0.01791 | 1.00 |
| V2 | `--system-prompt` | 0.01887 | 1.05 |
| V2s | default | 0.03339 | 1.86 |
| BASE | default | 0.07365 | 4.11 |

The shipped `/review` is unmeasured on a matched harness; that bench is preregistered in `../review-cost-matched-1023/PREREGISTERED.md` and has not been run.
