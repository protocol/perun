# Preregistration: idea-critic V4 (decide first, then attack), frozen before any held-out call

Date: 2026-10-19. Everything in this file is frozen by `SHA256-frozen.txt` and by the first line of `ledger.jsonl` (a `preregistered` event carrying the hash of that file) before the first held-out call. Dev numbers below were produced before the held-out corpus was written.

## Question

The shipped skill (V0) approves too few good decisions. In the V3 bench (held-out, 30 cases) V0 said NO-GO on 0.867 of good decisions, against 0.311 for the same model with no skill (BASE). V2 and V3 added blocker/risk rules to step 6 and both lost their held-out runs on the zero-false-GO guardrail, with BASE beating every wording. V4 asks a different question: can the skill keep the model's own judgment and add the attack on top, instead of replacing the judgment with the attack?

## Diagnosis (dev cases only; V3's held-out is spent and is not used as dev)

Dev set: the 88 cases of the three earlier idea-critic benches (outcome, calibration and V2 held-out corpora; 44 good, 44 bad), 3 samples each, Qwen3.5-397B-A17B, thinking off. V0 scores accuracy 0.621, false-GO 0.000, false-NO-GO 0.758. BASE scores 0.795, false-GO 0.008, false-NO-GO 0.402.

Of the 132 V0 calls on good decisions, 100 ended in NO-GO. Keyword counts over the verdict section of those 100 (a call can match several): price or cost 85, unproven or assumed or missing evidence 65, cheaper or staged or partner alternative or pilot 57, north star or stage fit 48, missing kill criterion or metric 45, recomputed figures 4. The reasons are not facts that show the plan fails; they are the generic objections the attack steps (steelman, then attack; do nothing; better way; pre-mortem; kill criteria) are designed to produce. The model writes the dissent and then treats it as the verdict. Three skill passages convert dissent into a block: the prime directive ("surviving the attack" with no definition of a blocker), step 2 ("it must beat all three" of do nothing, cheaper alternatives and reversibility), and step 6's mapping of go-if and a missing cap or kill criterion to NO-GO.

## Dev wordings tried (3 of the allowed 4)

All three start from V0 with the same edits: a blocker definition in the prime directive and step 6 (a blocker is a fact already in hand that shows the plan fails; risks, a missing pilot, cap, metric or kill criterion, and cheaper alternatives that do not reach the same upside never decide the call), step 2 reduced to "must beat do nothing", and step 3 limited to a stated north star. They differ in how the first call is made. Texts are in `dev/skill_<name>.txt`, built from V0 by `dev/mk_variants.py`.

| Wording | Change | Dev accuracy | False-GO | False-NO-GO | V4 minus V0 paired accuracy [95% CI] | V4 minus BASE |
|---|---|---|---|---|---|---|
| v4a | adds step 0: write `First call: GO` or `NO-GO` before attacking; the attack may only flip GO to NO-GO through a blocker | 0.614 | 0.000 | 0.773 | -0.008 [-0.057, 0.042] | -0.182 [-0.258, -0.114] |
| v4b | v4a plus a preamble "Decide like an operator, then attack" saying the attack adds to judgment and never raises the bar above it, and that a missing pilot, cap, metric or fallback is never a blocker | 0.773 | 0.008 | 0.447 | +0.152 [0.083, 0.220] | -0.023 [-0.072, 0.023] |
| v4c | v4b with a symmetric step 0: a first-call NO-GO stands only if it rests on a blocker | 0.727 | 0.023 | 0.523 | +0.106 [0.034, 0.178] | -0.068 [-0.129, -0.011] |

Findings: in v4a the first call was NO-GO on 102 of 132 good-decision calls and the attack never changed any call (first call equalled final decision in all 264 calls), so the framing in the skill's first lines sets the answer; v4b's preamble moved first-call GO on good decisions from 30 to 73 of 132 and again never changed a call. v4c let the attack reverse first-call NO-GO and made false GOs worse (3 of 132). **v4b is frozen as V4** (`prompts/skill_v4.txt`, identical to `dev/skill_v4b.txt`). Its one dev false GO is `cheapest-car-2008` (1 of 132 bad-decision calls); BASE also has one on the dev set. V4 costs about 484 completion tokens per call against V0's 405 in the V3 bench.

Honest reading of the design: V4 works by making the model's gut call explicit and protected, so on this model it is close to BASE with the attack and kill criteria appended to the answer. The attack never changed a decision in dev. If V4 wins, the claim is only that the skill no longer hurts the call, not that the attack improves it.

## Held-out design

- 30 new cases (15 good, 15 bad) in `corpus.json`: real-world decisions with a documented outcome, names removed, same genre as earlier sets ("situation, Proposal (year), Risks raised"). Each cites one English Wikipedia page and a verbatim `evidence_quote` that was checked against the page text fetched on 2026-10-19. The key is the documented real-world outcome, not proof the decision was wrong or right at the time.
- Disjoint by id and by source URL from the outcome, calibration, V2 and V3 corpora and from every Wikipedia URL elsewhere in tracked files. `prior-v3-ids.json` records V3's ids and URLs, since that corpus is not on the base branch; `scripts/test_idea_critic_v4.py` checks all of it.
- Arms: V0 (the shipped `SKILL.md`, as `../idea-critic-v2-1019/prompts/skill_v0.txt`), V4 (`prompts/skill_v4.txt`), BASE (no system prompt). Qwen3.5-397B-A17B on the free PCSS endpoint, thinking off, temperature 0.7, 3 samples per case and arm, one run, no retries beyond transport errors.
- Parsing and scoring: `../../idea-critic-outcome-1019/bench_outcome.py` (the last line `DECISION: GO` or `DECISION: NO-GO`; revise or hold counts as NO-GO; unparseable counts as wrong). Per-case mean accuracy, paired per-case bootstrap, 10,000 resamples, seed 1 (`boot` in `scripts/rival_eval.py`).

## Frozen keep rule

WIN if and only if the paired accuracy difference V4 minus V0 has a 95% CI lower bound above 0 and V4's false-GO mean is exactly 0 over its 45 bad-decision calls. LOSS if the CI upper bound is below 0 or the guard fails. Otherwise TIE. `.claude/skills/idea-critic/SKILL.md` changes only on WIN, together with an evals mechanism. The difference from BASE and V4's false-GO against BASE's are reported as descriptive only and do not decide.

## Expectation stated in advance

V4's dev false-GO rate is 1 of 132 (0.008). With that rate the chance of no false GO in 45 calls is about 0.71, and BASE's own rate on earlier sets (about 1 to 2%) means a single false GO would be ordinary sampling noise and would still be a LOSS under this rule. I expect V4 minus V0 to be positive with a lower bound above 0, because dev showed +0.152 and V0's accuracy on the V3 held-out was 0.567; the guard is the likelier failure.

## Limits

Thirty cases give wide intervals. One non-Claude model, not the Claude host the skill ships for. Cases are written by the same author as the dev set in the same genre. The model may partly recall famous outcomes. Dev was tuned on 88 cases and is optimistic. The V4 attack never changed a dev decision. Zero false GO in 45 calls is partly luck at these rates.
