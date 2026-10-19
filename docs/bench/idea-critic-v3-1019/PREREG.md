# Preregistration: idea-critic V3 blocker test plus edge gate, held-out run (frozen 2026-10-19, before any held-out call)

## Question

Can a small change to the V2 blocker test keep the idea-critic's false-go rate at zero, like the current skill (V0), while raising its accuracy above V0 on fresh cases it was never tuned on?

## Why V3 (diagnosis, read on the training cases only)

V2 (`../idea-critic-v2-1019`) raised accuracy over V0 but lost its preregistered run on the guardrail: one false GO in 42 bad-case calls where V0 made none. Across all V2 outputs on the 88 earlier cases, V2 said GO to a bad decision in 3 calls (blog-platform-buy-2013, tablet-launch-2011, head-worn-display-2013). In each, the model wrote `Blockers: NONE` and filed as a risk a fact the proposal states as already true and that removes the plan's own route to its upside (users already dislike the ads the plan sells; a small app catalog at price parity; no everyday use for a product positioned as everyday). V2 invites this because it lists "the requester's own listed risks" as risks. On good cases, V2's remaining wrong NO-GOs mostly cite a missing clause, earn-out, pilot or kill criterion, or a price or value doubt; those are risks, not blockers. The no-skill arm (BASE) beats V0 by approving more good plans while making almost no false GO (1 of 132 calls on these cases).

V3 (`prompts/skill_v3.txt`) changes only step 6 of `../idea-critic-v2-1019/prompts/skill_v2.txt`:

- Blocker list: adds "a negative the proposal states as already true (not *may* or *could*) that removes its own route to the upside and that the plan does not answer".
- Risk list: adds "a missing term, clause, pilot or metric (add it yourself as a kill criterion)".
- Edge gate: GO now also needs a named *edge*, a stated fact showing why this plan, from this proposer, can win its upside (an asset, cost or product advantage rivals lack, or demand already shown). Size, brand, money, distribution, publicity, being first, fear of falling behind, a rival's move, the cost of doing nothing and "strategic necessity" are not an edge on their own; if the only edge leans on one of those or on a fix planned after launch, the answer writes `Edge: NONE`. No edge means no-go.
- The written sort gains an `Edge:` line next to `Blockers:` and `Risks:`.

## History that limits the claim (stated before the run)

- Training (dev) set: the 88 cases of the three earlier idea-critic benches (outcome, calibration, V2 held-out; 44 good, 44 bad, so 132 bad-case calls). Their V0, V2 and BASE outputs were read for the diagnosis. Four V3 wordings were run on dev, once each; every one is reported here, and dev numbers are optimistic and not evidence. V0 on dev: accuracy 0.621, false-go 0.000, false-no-go 0.758. BASE on dev: accuracy 0.795, false-go 0.008.
  - V3a (`dev/skill_v3a.txt`, `dev/v3a/`): V2 plus a contradiction check before writing `Blockers: NONE`, risks narrowed to *may*/*could* phrasing, and the missing-term risk. Accuracy 0.682, false-go 0.015 (2 calls), V3a minus V0 +0.061 [0.019, 0.106]. The model rationalized new GOs as "strategic necessity" and approved fewer good plans than V2.
  - V3b (`dev/skill_v3b.txt`, `dev/v3b/`): V2 plus the edge gate (fear, rival moves, doing nothing and strategic necessity excluded) and the missing-term risk, no contradiction check. Accuracy 0.826, false-go 0.098 (13 calls), V3b minus V0 +0.205 [0.117, 0.295]. The model named brand, scale, publicity or first-mover status as the edge.
  - V3c (`dev/skill_v3c.txt`, `dev/v3c/`): V3b plus the stated-negative blocker and size, brand, money, distribution, publicity and being first excluded as edges. Accuracy 0.826, false-go 0.061 (8 calls), V3c minus V0 +0.205 [0.129, 0.284]. Remaining false GOs built the edge from those excluded items anyway or from a fix planned after launch.
  - V3d (the frozen V3; its dev outputs are in `dev/outputs/`): V3c plus the `Edge: NONE` rule. Accuracy 0.780, false-go 0.023 (3 calls), false-no-go 0.417, V3 minus V0 +0.159 [0.102, 0.223], V3 minus BASE -0.015 [-0.068, 0.038].
- No dev wording reached zero false GOs while beating V0. V3d was frozen as the best trade-off: if its dev false-go rate held and calls were independent, the chance of no false GO in 45 held-out bad-case calls would be about 0.977^45, roughly 0.35. A LOSS on the guardrail is therefore the likely outcome and is stated here before the run.
- Held-out set: 30 fresh cases in `corpus.json` (15 key `good`, 15 key `bad`), written by the same author in the same genre after reading the V2 results and before any V3 output existed. None overlaps any earlier idea-critic set by id or by source URL; disjointness was checked against every English Wikipedia URL in the repository's `docs/`, `scripts/`, `.claude/` and `evals/` files. Each case has an English Wikipedia source page and verbatim evidence quotes checked against that page's text fetched 2026-10-19. Names are removed from every prompt; models may still partly recall famous outcomes.
- The held-out risk lists were written with a mix of present-fact and *may* phrasing on both keys before V3 keyed a rule on that phrasing; the author still knows the cases, so this tests new cases, not a new author or domain.

## Design

- Arms: V0 (current `.claude/skills/idea-critic/SKILL.md`, identical to `../idea-critic-v2-1019/prompts/skill_v0.txt`), V3 (`prompts/skill_v3.txt`), BASE (no system prompt).
- Same user message, parser and last-line contract as `../../idea-critic-outcome-1019/bench_outcome.py` (`DECISION: GO` or `DECISION: NO-GO`; revise or hold counts as NO-GO). An unparseable call counts as wrong.
- 3 samples per case and arm at temperature 0.7; a case score is the mean of its 3 samples.
- One model: Qwen3.5-397B-A17B on the free PCSS endpoint, thinking off. No secondary model.
- Intervals: 10,000-resample percentile bootstrap over cases, seed 1 (`boot` in `scripts/rival_eval.py`); paired differences are per case.
- The held-out run is executed once. A missing output (generation failure) is regenerated; no output is discarded or resampled.

## Outcomes and decision rule

- Primary outcome: accuracy, decision matches the key.
- Guardrail: V3 makes no false GO at all (GO on a `bad` case, 0 of 15 cases x 3 samples).
- WIN: paired accuracy V3 minus V0 has a 95% CI lower bound above 0 and the guardrail holds. Only a WIN ships V3 into `SKILL.md`.
- LOSS: that CI upper bound is below 0, or the guardrail is broken.
- TIE: anything else; `SKILL.md` stays unchanged.
- Reported but not decisive: V3 minus BASE (paired), false-no-go rate, invalid decisions, completion tokens per call.
- `bench_v3.py heldout report` computes the verdict with this rule (`verdict()`).

## Frozen files

`SHA256-frozen.txt` lists the sha256 of this file, `corpus.json`, `prompts/skill_v3.txt`, `bench_v3.py`, `../idea-critic-v2-1019/prompts/skill_v0.txt` and `../../idea-critic-outcome-1019/bench_outcome.py`. Any change to these after the freeze voids the run.
