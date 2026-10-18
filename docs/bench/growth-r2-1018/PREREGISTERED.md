# Preregistration: growth-analytics round 2, one edit, held-out n=150 (2026-10-18)

This file, the harness and the frozen texts are hashed (`SHA256-prereg.txt`) after the tuning phase and before any held-out seed, scenario or answer exists. The scenario hashes follow in `SHA256-frozen.txt`; its hash is the first line of `ledger.jsonl`, before any held-out answer or judge call. Every model call goes to the PCSS endpoint ($0); no `claude -p`; all scenarios are fictional.

Scenarios file: scenarios-heldout.json

## Question

Round 1 (`docs/bench/growth-r1-1018`) tested an answer-first paragraph and lost (paired difference -0.158 [-0.275, -0.033], n=60); the shipped text (v0) scored 0.467 [0.367, 0.567] against the marketingskills analytics and ab-testing rival there and 0.442 [0.333, 0.550] in the baseline (`docs/bench/baseline-gs-1018`). This round tests one different edit on a fresh n=150 set. v0 is `.claude/skills/growth-analytics/SKILL.md` on origin/main at b16413fa, byte-identical to the round-1 v0.

Does v1 beat v0 against the same rival, and does v1 beat the rival?

## Where the edit comes from (prior losses)

`losses.py` re-judged the v0-versus-rival pairs of the spent round-1 held-out set (GLM-5.1, protocol v2, both orders, analysis text kept; 120 orders, rival won 64, v0 won 55) and I read all 64 rival-won analyses. Recurring reasons, by keyword count over the 64 analyses (clusters overlap, deterministic rule in the author's scratch, not kept): "comprehensive" or "actionable" 53; "hypothes" or "unknown" 21 (the rival's answer addresses the requester's own named hypotheses and unknowns with the specific cut or event that tests them); "rigid", "prescriptive", "methodolog", "overly cautious" or "lecture" 13 (v0 is faulted for statistical method where the requester wanted a usable read). The edit therefore (a) adds one method step that names a line in the answer for every hypothesis, unknown and constraint the requester states, with the test that settles it and the result that changes the call, and (b) pays for it by deleting the Stage-awareness section, which restates method step 4 and the stage model in `deep-code-review` (net +69 bytes).

## Tuning phase (before this file; logged in `ledger-tune.jsonl`)

One fresh tune set of 60 scenarios (ids `gv01` to `gv60`, `scenarios-tune.json`), drawn like the held-out set. Tune runs used GLM-5.1 only, both orders, v2 protocol, and are exploratory; the judge's slot-1 rate was 0.62 to 0.67 on every tune run (outside the 0.4 to 0.6 gate that applies to the held-out run), so tune numbers are noisier than the held-out ones. Candidate texts are kept in `prompts/candidates/`. Paired difference against v0 (same rival answers), n = 60:

| Candidate | Change | Paired diff vs v0 [95% CI] |
|---|---|---|
| K1 | step 6: a peeked or conflicted read is a caveat on the call, not a refusal; keep rule names out | -0.092 [-0.200, 0.017] |
| K3 | step 3: a tracking plan lists every event with name, trigger, properties and question | -0.083 [-0.192, 0.025] |
| K2 | definition of done: identifier and PII note only when the request involves per-user ids | -0.058 [-0.183, 0.067] |
| K4 | K1 + K2 + K3 | -0.067 [-0.192, 0.058] |
| K5 | add the step "Answer the requester's own questions" | -0.133 [-0.233, -0.033] |
| K7 | K5's step, plus delete the Stage-awareness section | -0.042 [-0.150, 0.067] |
| K0 (noise) | v0 plus one trailing newline: identical text, new sample | -0.092 [-0.200, 0.017] |

Reading: no candidate beat v0 on the tune set, and the identical-text run scored -0.092, so v0's tune sample is lucky by about that much and the candidates are indistinguishable from noise. The candidate selection rule was stated before the runs (highest tune paired difference, size growth under 100 bytes preferred); it picks K7. K7 is shipped as v1 only if the held-out keep rule below holds; the tune data is no evidence for it. Candidates were not tuned further after seeing the noise run.

## Arms and data

- v0 = `frozen/growth-analytics.v0.md`. v1 = `frozen/growth-analytics.v1.md` (candidate K7), which will be byte-identical to the edited SKILL.md only if the keep rule holds. Both are final: no further tuning, no edit after the held-out result.
- Rival: the committed text `docs/bench/growth-analytics-rubricfree-1016/prompts/rival.txt`, hashed in the frozen list. Its answer to each scenario is generated once and shared by both skill arms, so (v1 minus v0) is paired on identical rival text.
- Scenarios: 150 fresh held-out scenarios (ids `gw001` to `gw150`), seeds drawn by the blind writer model (Qwen3.5-397B-A17B, temperature 0.9) and rejected if close to any seed in `docs/bench` (including the tune seeds); scenarios are written in batches of 10 from the existing writer brief `docs/bench/growth-analytics-rubricfree-1016/prompts/writer_brief.txt` (no skill text shown). Any scenario sharing more than 10% of its 6-word shingles with the `docs/bench` corpus on origin/main (every scenario, seed and record file, including round 1), with the tune scenarios, or with another held-out scenario is regenerated before freezing; ids are disjoint from every earlier id (prefixes `gv` and `gw` appear nowhere else). `scripts/bench_check.py` must pass.
- Generator for all arms: Qwen3.5-397B-A17B, thinking off, temperature 0.3, no tools, the harness GEN_TASK wrapper, never a judge.
- Judge: protocol v2 of `scripts/rival_eval.py` unchanged (random three-letter labels, analysis before verdict, both orders). The judge is the first of GLM-5.1, GLM-5.2, gpt-oss_120b whose slot-1 rate, pooled over both arms, is in 0.4 to 0.6; the same judge scores both arms. No healthy judge means no verdict, which means do not ship. A scenario scores 1 when the arm wins in both orders, 0 when it loses in both, else 0.5. Other judges are reported as sensitivity only.

## Decision rule (stated before any held-out call)

- KEEP (ship the SKILL.md edit) only if, with at least 135 of 150 scenarios scored by a healthy judge, the paired difference (v1 minus v0 win rate, mean of per-scenario score differences) has a 95% bootstrap CI (10,000 resamples over scenarios, percentile, seed 1) whose lower bound is above 0. Otherwise SKILL.md is not edited and only this bench record is committed.
- Superiority over the rival is claimed only if v1's win-rate CI (same bootstrap) has a lower bound above 0.5. A win claim requires the keep rule as well: an unshipped text is not claimed as a win.
- One run per arm; no re-runs, no judge swapping, no scenario edits after seeing a result. Records are never overwritten.

## Known limits

Single generator family writes the scenarios and all answers; judges are models; scenarios are fictional; one rival. Tune noise is large and the tune judge was position-biased, so the tune set cannot rank candidates. A FAIL means "not shown better under this judge on this synthetic distribution", not a claim about real users.
