# Preregistration: growth-analytics round 3, one edit, held-out n=150 (2026-10-18)

This file, the harness and the frozen texts are hashed (`SHA256-prereg.txt`) after the tuning phase and before any held-out seed, scenario or answer exists. The scenario hashes follow in `SHA256-frozen.txt`; its hash is the first line of `ledger.jsonl`, before any held-out answer or judge call. Every model call goes to the PCSS endpoint ($0); no `claude -p`; all scenarios are fictional.

Scenarios file: scenarios-heldout.json

## Question

Rounds 1 and 2 (`docs/bench/growth-r1-1018`, `docs/bench/growth-r2-1018`) each tested one edit against the marketingskills analytics and ab-testing rival and did not ship: answer-first lost (paired -0.158 [-0.275, -0.033], n=60); the round-2 step "answer the requester's own questions" tied (paired +0.007 [-0.070, 0.083], n=150). The shipped text (v0) scored 0.430 [0.367, 0.497] on the round-2 held-out set. This round mines the round-2 judge reasons for why the rival wins, drafts at most three candidate edits, picks one on a fresh tune set by a rule fixed in advance, and tests it once on a fresh n=150 set. v0 is `.claude/skills/growth-analytics/SKILL.md` on origin/main at 14cb262f, byte-identical to the round-2 v0.

Does v1 beat v0 against the same rival, and does v1 beat the rival?

## Where the edits come from (prior losses)

Round 2 committed verdicts but not judge reasons, so `losses.py` re-judged the 150 spent round-2 held-out v0-versus-rival pairs (GLM-5.1, protocol v2, both orders, analysis text kept; 300 orders, rival won 182, v0 won 116, 2 ties) and kept the 182 rival-won analyses (not committed; the reasons are summarised here). I read a random sample of 70 of them. Recurring reasons, by keyword count over all 182 (clusters overlap; a deterministic regex in the author's scratch, so the counts are approximate leads, not measurements): breadth, specific segments, events, formulas or thresholds in the rival 85; a decision matrix, if-then reading or next step 85; the rival is tailored to the audience or format the requester named (director, VP, investor deck, hand to dev) 72; financial framing (revenue per visitor, margin, unit economics) 46; the skill's answer is faulted as dismissive, premature or presuming a decision the requester reserved for someone else 53 (the regex also matches "assumes" used of either side, so this is an upper bound); a statistical-rigor, peeking or methodology lecture the requester did not need 39; the skill refuses, withholds, strips down or substitutes a smaller deliverable (an event list cut to a few events, a requested spec replaced by a critique of the premise) 13; the rival uses data the requester already has instead of asking for new tracking 20. In the sample read, v0's losses fall in four groups: (1) it applies its own rules (instrument only what answers a named question, UNVERIFIED, no invented numbers) in place of the deliverable asked; (2) it lectures on rigor when the request was a read or a summary; (3) it concludes or decides a point the requester reserved; (4) it lists cuts without saying what each result would mean or what the money consequence is, where the rival writes if-then scenarios and an AOV or revenue check.

## Tuning phase (before this file; logged in `ledger-tune.jsonl`)

One fresh tune set of 60 scenarios (ids `gv01` to `gv60`, `scenarios-tune.json`; the ids repeat the round-2 tune ids but the seeds and text are new: seeds were rejected when close to any earlier seed, including round 2's). All three candidates share one de-duplication that keeps the skill inside its byte budget: the Stage-awareness section (it restates method step 4) is deleted, the Standards tail that restates the identifier-seam line in step 3 is cut, and the Verification bullets that restate the anti-rationalization table and the Definition of done collapse to the eval-id list (every eval id stays, which the enumeration gate checks). Candidate texts are in `prompts/candidates/`. Tune runs used GLM-5.1 only, both orders, v2 protocol, are exploratory, and the judge's slot-1 rate was 0.61 to 0.64 (outside the 0.4 to 0.6 gate that applies to the held-out run). Paired difference against v0 (same rival answers; v0 scored 0.275 against the rival on this tune set), n = 60:

| Candidate | Change (plus the shared de-duplication) | Bytes | Paired diff vs v0 [95% CI] |
|---|---|---|---|
| C1 | step 7 "Deliver what was asked, then apply the rules": the named artifact first, in the stated format and audience; rules shape it and never replace it with a refusal or a lecture; pick among the requester's options; leave reserved decisions; existing data before new tracking; identifier and benchmark notes only when relevant | 10070 | +0.067 [-0.050, 0.183] |
| C2 | step 7 "Make every cut decide something": each segment, metric or test comes with what each result means, the next action, and the money consequence for the decision-maker | 9840 | +0.017 [-0.067, 0.100] |
| C3 | C1 plus C2 (as steps 7 and 8) plus one sentence in step 5: raise peeking, power or multiple-comparison points only when the requester's own read has that flaw | 10656 | +0.125 [0.033, 0.217] |

The candidate selection rule was stated before the runs (highest tune paired difference; ties to the smaller text); it picks C3. The tune judge was position-biased (slot-1 above 0.6) and round 2 showed an identical-text re-run moving the tune estimate by about 0.09, so the tune result is a lead, not evidence: C3 is shipped only if the held-out keep rule below holds. No identical-text noise run was made this round. Candidates were not tuned further after seeing the tune result.

## Arms and data

- v0 = `frozen/growth-analytics.v0.md`. v1 = `frozen/growth-analytics.v1.md` (candidate C3), which will be byte-identical to the edited SKILL.md only if the keep rule holds (plus the one eval entry and its Verification id that a shipped edit needs, which change no text the arms see). Both are final: no further tuning, no edit after the held-out result.
- Rival: the committed text `docs/bench/growth-analytics-rubricfree-1016/prompts/rival.txt`, hashed in the frozen list. Its answer to each scenario is generated once and shared by both skill arms, so (v1 minus v0) is paired on identical rival text.
- Scenarios: 150 fresh held-out scenarios (ids `gx001` to `gx150`, a prefix no earlier bench uses), seeds drawn by the blind writer model (Qwen3.5-397B-A17B, temperature 0.9) and rejected if close to any seed in `docs/bench` (including round 2 and the tune seeds); scenarios are written in batches of 10 from the existing writer brief `docs/bench/growth-analytics-rubricfree-1016/prompts/writer_brief.txt` (no skill text shown). Any scenario sharing more than 10% of its 6-word shingles with the `docs/bench` corpus on origin/main (every scenario, seed and record file, including rounds 1 and 2), with the tune scenarios, or with another held-out scenario is regenerated before freezing. `scripts/bench_check.py --changed origin/main` must pass.
- Generator for all arms: Qwen3.5-397B-A17B, thinking off, temperature 0.3, no tools, the harness GEN_TASK wrapper, never a judge.
- Judge: protocol v2 of `scripts/rival_eval.py` unchanged (random three-letter labels, analysis before verdict, both orders). The judge is the first of GLM-5.1, GLM-5.2, gpt-oss_120b whose slot-1 rate, pooled over both arms, is in 0.4 to 0.6; the same judge scores both arms. No healthy judge means no verdict, which means do not ship. A scenario scores 1 when the arm wins in both orders, 0 when it loses in both, else 0.5. Other judges are reported as sensitivity only.

## Decision rule (stated before any held-out call)

- KEEP (ship the SKILL.md edit) only if, with at least 135 of 150 scenarios scored by a healthy judge, the paired difference (v1 minus v0 win rate, mean of per-scenario score differences) has a 95% bootstrap CI (10,000 resamples over scenarios, percentile, seed 1) whose lower bound is above 0. Otherwise SKILL.md is not edited and only this bench record is committed.
- Superiority over the rival is claimed only if v1's win-rate CI (same bootstrap) has a lower bound above 0.5. A win claim requires the keep rule as well: an unshipped text is not claimed as a win.
- One run per arm; no re-runs, no judge swapping, no scenario edits after seeing a result. Records are never overwritten.

## Known limits

Single generator family writes the scenarios and all answers; judges are models; scenarios are fictional; one rival. Tune noise is large and the tune judge was position-biased, so the tune set cannot rank candidates reliably. The rival-won reasons come from a single re-judge pass and are keyword-counted. A FAIL means "not shown better under this judge on this synthetic distribution", not a claim about real users.
