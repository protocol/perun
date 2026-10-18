# growth-analytics round 3, one edit, held-out n = 150, 2026-10-18

BLUF: SHIPPED, NOT A WIN. The edit (v1, candidate C3) scored 0.513 [0.450, 0.577] against the marketingskills analytics and ab-testing rival (52 wins, 50 ties or splits, 48 losses), the previous shipped text (v0) 0.423 [0.357, 0.490] (44 / 39 / 67). Paired difference (v1 minus v0) +0.090, 95% bootstrap CI [0.017, 0.163] (150 of 150 scored, judge GLM-5.1, slot-1 rate 0.598, inside the 0.4 to 0.6 gate). The preregistered keep rule (paired lower bound above 0) is met, so the edit is shipped in `.claude/skills/growth-analytics/SKILL.md`. Superiority over the rival (win-rate lower bound above 0.5) is not shown: the lower bound is 0.450. Spend $0.00 (PCSS only).

- Rule, arms, scenario drawing, tuning log: `PREREGISTERED.md`. Hash lists: `SHA256-prereg.txt` (after the tuning phase, before any held-out seed) and `SHA256-frozen.txt` (after the held-out scenarios, before any held-out answer). `ledger.jsonl` records the hash of `SHA256-frozen.txt` first, then `run_start`, then the results hash. Tuning runs are in `ledger-tune.jsonl`, never in `ledger.jsonl`.
- Tested text: `frozen/growth-analytics.v1.md` (candidate C3). Against v0 it adds method step 7 "Deliver what was asked, then apply the rules" (produce the named artifact in the stated format and audience before any caveat; pick among the requester's own options; leave reserved decisions; use existing data before proposing tracking; identifier and benchmark notes only when relevant), step 8 "Make every cut decide something" (each segment, metric or test says what each result means, the next action and the money consequence), and one sentence in step 5 (raise peeking, power or multiple-comparison points only when the requester's own read has that flaw). The Stage-awareness section (it restated step 4), the Standards sentence that restated the identifier seam and the Verification bullets that restated other sections are removed; 10706 bytes against 10795 for v0. v0 is `frozen/growth-analytics.v0.md`, the SKILL.md on origin/main at 14cb262f. The rival text is the committed `docs/bench/growth-analytics-rubricfree-1016/prompts/rival.txt`.
- Source of the edit: `losses.py` re-judged the 150 spent round-2 held-out v0-versus-rival pairs and kept the judge analyses of the 182 orders the rival won; the reasons and keyword counts are in `PREREGISTERED.md`. Four groups recur in the sample read: v0 applies its own rules in place of the deliverable asked, lectures on rigor when a read was asked, concludes a point the requester reserved, and lists cuts without saying what each result would mean or what it costs. C1 targets the first three, C2 the fourth, C3 is both plus the step-5 sentence. Tune paired differences against v0 (n=60, exploratory, slot-1 above the gate): C1 +0.067, C2 +0.017, C3 +0.125; C3 was picked by the rule fixed before the runs (highest, ties to the smaller text).
- Scenarios: `scenarios-heldout.json` (ids gx001 to gx150) from `prompts/seeds-heldout.txt`; the largest 6-word shingle overlap of any scenario is 0.094 against every text file of docs/bench on origin/main (including rounds 1 and 2 and their outputs and judge records), 0.055 against the tune scenarios and 0.086 against another held-out scenario; 150 distinct ids; `scripts/bench_check.py --changed origin/main` passes.
- Raw outputs and verdicts: `results/outputs`, `results/judge-verdicts.json` (every verdict kept), `results/verdict.json`. Reproduce: `python3 docs/bench/growth-r3-1018/bench.py run <out>` then `fold <out>` (PCSS key from the repo `.env`).

| Judge | Slot-1 | v0 | v1 | Paired diff [95% CI] |
|---|---|---|---|---|
| GLM-5.1 (used, healthy) | 0.598 | 0.423 [0.357, 0.490] (44 / 39 / 67) | 0.513 [0.450, 0.577] (52 / 50 / 48) | +0.090 [0.017, 0.163] |
| GLM-5.2 (sensitivity, outside the gate) | 0.640 | 0.433 | 0.463 | +0.030 [-0.047, 0.107] |
| gpt-oss_120b (sensitivity, outside the gate) | 0.648 | 0.357 | 0.453 | +0.097 [0.027, 0.167] |

All three judges give a positive point estimate for v1 minus v0 (two of three with a lower bound above 0); under the two position-biased sensitivity judges v1 stays below 0.5 with an upper bound near 0.52. Only the used judge puts the v1 point estimate above 0.5.

## What this says

- The edit helps against this rival under this judge on this synthetic distribution: +0.090, lower bound 0.017, which is above 0 by a small margin. It moves v1 from the 0.42 to 0.47 band that three earlier fresh sets put the shipped text in to about parity with the rival, and not past it: the win-rate interval [0.450, 0.577] includes 0.5, so no win is claimed. The confirmed-win count in `docs/perun-vs-rivals.md` is unchanged.
- The two earlier non-shipped rounds changed what a reader is told to do (answer first, name a line per hypothesis); this one removes the places where the skill's own rules displaced the requested deliverable and adds a reading rule per cut. That is a consistent direction with the loss reasons, but this run cannot say which of the three parts carries the gain.

## Disclosures

- The scenario writer rejected whole batches of ten when one scenario overlapped the corpus (overlap 0.14 to 0.16). `write_batch` in `bench.py` was changed to keep accepted scenarios and rewrite only the rejected one (16 tries), and `SHA256-prereg.txt` was regenerated after the held-out seeds were drawn but before any held-out scenario, answer or judge call existed; the order of events is in `ledger.jsonl`.
- The tune ids gv01 to gv60 repeat round 2's tune ids but the seeds and text are new. The held-out prefix gx is used by no earlier bench.
- The shipped SKILL.md differs from `frozen/growth-analytics.v1.md` by one eval id in the Verification list (`delivers-the-asked-artifact-with-reading-rules`, the eval added with the edit); the text the arms saw is otherwise the shipped text.
- The tune judge's slot-1 rate was above the gate (0.61 to 0.64); no identical-text noise run was made this round, and round 2 showed such a run moving the tune estimate by about 0.09. The tune result was treated as a lead only.
- One of the sensitivity judges is also outside the gate; they are not used for the decision.

## Caveats

Qwen3.5-397B-A17B generates every arm (not necessarily the model the skill runs on); judges are PCSS models of other families; one rival; one run per arm; scenarios are fictional and written by one blind writer model. The used judge's slot-1 rate 0.598 is at the edge of the gate. The paired lower bound (0.017) is small and rests on one run. "Shipped" means the preregistered paired rule was met on this synthetic distribution, not a claim about real users.
