# growth-analytics round 2, one edit, held-out n = 150, 2026-10-18

BLUF: DO NOT SHIP, NO WIN. The edit (v1) scored 0.437 [0.367, 0.503] against the marketingskills analytics and ab-testing rival (45 wins, 41 ties or splits, 64 losses), the shipped text (v0) 0.430 [0.367, 0.497] (41 / 47 / 62). Paired difference (v1 minus v0) +0.007, 95% bootstrap CI [-0.070, 0.083] (150 of 150 scored, judge GLM-5.1, slot-1 rate 0.600, which is the edge of the 0.4 to 0.6 gate). The preregistered keep rule (paired lower bound above 0) is not met, and superiority over the rival (win-rate lower bound above 0.5) is not shown: the upper bounds are 0.503 and 0.083. Spend $0.00 (PCSS only). `.claude/skills/growth-analytics/SKILL.md` is unchanged in this commit; only this bench record is committed.

- Rule, arms, scenario drawing, tuning log: `PREREGISTERED.md`. Hash lists: `SHA256-prereg.txt` (after the tuning phase, before any held-out seed) and `SHA256-frozen.txt` (after the held-out scenarios, before any held-out answer). `ledger.jsonl` records the hash of `SHA256-frozen.txt` first, then `run_start`, then the results hash. Tuning runs are in `ledger-tune.jsonl`, never in `ledger.jsonl`.
- Tested text: `frozen/growth-analytics.v1.md` (tune candidate K7): a new method step 7, "Answer the requester's own questions" (each stated hypothesis, unknown and constraint gets a named line: the cut, event or test that settles it and the result that would change the call), paid for by deleting the Stage-awareness section that restates method step 4; 10864 bytes against 10795. v0 is `frozen/growth-analytics.v0.md`, the SKILL.md on origin/main at b16413fa. The rival text is the committed `docs/bench/growth-analytics-rubricfree-1016/prompts/rival.txt`.
- Source of the edit: `losses.py` re-judged the spent round-1 held-out pairs and kept the judge analyses of the 64 orders the rival won; keyword counts are in `PREREGISTERED.md`. All six tune candidates (`prompts/candidates/`; the noise run K0 is v0 plus one trailing newline, not kept as a file because the whitespace gate rejects it, its hash is in `ledger-tune.jsonl`) were below zero against v0 on the 60-scenario tune set, and an identical-text re-run scored -0.092, so the tune set could not pick an edit; the highest-scoring candidate by the rule fixed before the runs went to the held-out set.
- Scenarios: `scenarios-heldout.json` (ids gw001 to gw150) from `prompts/seeds-heldout.txt`; at most 0.094 of any scenario's 6-word shingles appear in any text file of docs/bench on origin/main (including round 1 and the outputs and judge records), 0.056 against the tune scenarios, no id clash; `scripts/bench_check.py` passes.
- Raw outputs and verdicts: `results/outputs`, `results/judge-verdicts.json` (every verdict kept), `results/verdict.json`. Reproduce: `python3 docs/bench/growth-r2-1018/bench.py run <out>` then `fold <out>` (PCSS key from the repo `.env`).

| Judge | Slot-1 | v0 | v1 | Paired diff [95% CI] |
|---|---|---|---|---|
| GLM-5.1 (used) | 0.600 | 0.430 [0.367, 0.497] | 0.437 [0.367, 0.503] | +0.007 [-0.070, 0.083] |
| GLM-5.2 (sensitivity, outside the gate) | 0.618 | 0.400 | 0.423 | +0.023 [-0.043, 0.093] |
| gpt-oss_120b (sensitivity, outside the gate) | 0.640 | 0.347 | 0.387 | +0.040 [-0.020, 0.100] |

All three judges give a small positive point estimate for v1 minus v0 and every interval includes 0; under every judge both arms sit below the rival (point estimates 0.347 to 0.437).

## What this says

- A second, different edit on a fresh set did not move the win rate: +0.007 is inside the noise of the set (identical-text re-runs moved the tune estimate by about 0.09). With round 1 (answer first, -0.158) and the baseline, growth-analytics has been measured against this rival on three fresh sets at n = 60 to 150 (shipped text 0.442, 0.467 and 0.430; the round-2 edit 0.437 on the last) and sits near 0.43 to 0.47 each time; it is not shown to beat the rival.
- The tune phase was uninformative: no candidate beat v0 (-0.042 to -0.133) and the judge's slot-1 rate on the tune set was 0.62 to 0.67. Selecting the best of six short candidates on it carried no signal, which the held-out result is consistent with.
- Not tried: a prompt-only fix may not exist at this skill size; one untested reading of the judge reasons is that the rival's wins are breadth and audience-specific detail inside a 600-word answer cap, which the skill's rule vocabulary crowds out. A change to the skill's structure rather than one added paragraph would need its own preregistered round.

## Caveats

Qwen3.5-397B-A17B generates every arm (not necessarily the model the skill runs on); judges are PCSS models of other families; one rival; one run per arm; scenarios are fictional and written by one blind writer model. The slot-1 rate of the used judge is exactly at the gate edge (0.600). A FAIL means "not shown better under this judge on this synthetic distribution", not a claim about real users.
