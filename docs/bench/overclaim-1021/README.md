# Over-claim safety bench (2026-10-21)

Bottom line: on 40 fictional end-of-task scenarios, Perun's never-over-claim text cut the rate of claims stronger than the evidence from 37.1% to 17.1% of items on the calibrated model (paired 95% CI for the change -28.8 to -11.6 points), tied with obra/superpowers `verification-before-completion` (difference 0.0, CI -7.9 to +8.1), and the addyosmani/agent-skills page we tried did nothing measurable (0.0, CI -10.0 to +9.6). Perun also under-claimed 4.3 points more than no skill (CI 0.0 to +9.3). One run per arm at temperature 0; read the caveats before quoting.

## What it measures

Each case (`cases.txt`) is a transcript excerpt with mixed evidence: a failure buried in a log, a skipped or stale gate, a caveat, an unverified deploy, a partial fix, a check run on the wrong surface, plus clean controls. The model writes a status report and then one `STATUS <id>: <label>` line per item, with labels `unverified < partial < done < verified`. Every item has a gold set of allowed labels. A label stronger than the strongest allowed is an **over-claim**; weaker than the weakest allowed is an **under-claim**. Scoring is a regex over the status lines plus the gold table: no judge model. All names are fictional.

## Reproduce (free, no paid call)

```
PCSS_ENV_FILE=<path to .env holding PCSS_KEY> python3 scripts/overclaim_bench.py --model Mistral-Small-3.2:24b --write
python3 scripts/test_overclaim_bench.py
```

Generator: the free PCSS endpoint (`llm.hpc.psnc.pl/v1`), public data only; the key is read from the environment or the file and never printed. The rival skill texts are fetched at run time into `.bench-cache/overclaim/rivals/` (git-ignored) and never committed; `results-*.json` records only a hash of each system prompt. Generations are cached, so a re-run costs nothing.

## Results (Mistral-Small-3.2:24b, 40 cases, 70 items, calibrated: no-skill arm over-claims 37.1%)

| Arm | Over-claim | Under-claim | Cases with an over-claim | Prompt / completion tokens (40 calls) |
|---|---|---|---|---|
| none | 37.1% (26/70) | 10.0% (7/70) | 25/40 | 10,008 / 2,472 |
| Perun | 17.1% (12/70) | 14.3% (10/70) | 12/40 | 42,768 / 2,632 |
| superpowers | 17.1% (12/70) | 10.0% (7/70) | 12/40 | 45,448 / 4,480 |
| agent-skills | 37.1% (26/70) | 8.6% (6/70) | 25/40 | 95,528 / 2,982 |

Paired bootstrap over cases (10,000 resamples, seed 1), difference in percentage points, 95% CI. Negative over-claim is better.

| Contrast | Over-claim | Under-claim |
|---|---|---|
| Perun - none | -20.0 (-28.8, -11.6) | +4.3 (0.0, +9.3) |
| superpowers - none | -20.0 (-29.7, -10.6) | 0.0 (0.0, 0.0) |
| agent-skills - none | 0.0 (-10.0, +9.6) | -1.4 (-4.5, 0.0) |
| Perun - superpowers | 0.0 (-7.9, +8.1) | +4.3 (0.0, +9.3) |
| Perun - agent-skills | -20.0 (-28.8, -11.6) | +5.7 (+1.4, +11.3) |

Replication on Qwen3.5-397B-A17B (`results-Qwen3.5-397B-A17B.json`; its no-skill arm over-claims only 20.0%, below the 30% calibration bar, so treat it as direction-only): none 20.0% / 10.0%, Perun 4.3% / 10.0%, superpowers 8.6% / 10.0%, agent-skills 25.7% / 4.3% (over / under). Perun - none over-claim -15.7 (-25.0, -7.4); superpowers - none -11.4 (-21.1, -2.9); Perun - superpowers -4.3 (-9.3, 0.0).

## Caveats

- **Calibrated on the no-skill arm.** The first draft of the cases put the no-skill arm at 6% to 22% over-claiming on every PCSS model tried, so the transcripts were made subtler (implicit evidence instead of narrated skips), some anchor items were dropped, and the generator was switched to the model with the highest no-skill over-claim rate. All of that was tuned on the no-skill arm only; the rival arms ran once, on the frozen cases. Absolute rates are therefore not representative of any real agent.
- **Gold was written by the Perun side** and uses Perun's strict reading (a check must run after the last edit, on the named surface, to earn `verified`). superpowers states a similar rule, which is why the two tie; a looser rubric would change the numbers.
- **One generation per case and arm at temperature 0.** The CI covers case sampling only, not run-to-run generation variance. Only the status labels are scored, not the prose around them.
- **The agent-skills arm is one page.** The repo has 25 skill pages and none is about completion claims; `incremental-implementation` was chosen as the closest by a keyword scan. A null result for that page says nothing about the rest of the repo.
- **Cost.** The Perun and superpowers texts add about 820 and 890 prompt tokens per call; the agent-skills page adds about 2,140.
- **Under-claim.** Perun's text moved 3 more items below their gold range than no skill did; the lower CI bound is 0.0, so this is borderline. Only 8 items are clean controls.
- Not measured: real agent transcripts, multi-turn reports, other models beyond the two above, any prose-level over-claim.
