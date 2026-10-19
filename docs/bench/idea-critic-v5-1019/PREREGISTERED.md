# Preregistration: idea-critic V5, frozen before any held-out call

Date: 2026-10-19. Everything in this file is frozen by `SHA256-frozen.txt` and by the first line of `ledger.jsonl` (a `preregistered` event carrying the hash of `SHA256-frozen.txt`) before the first held-out call. No call has been made on the 30 held-out cases when this file is written.

## Question

V4 (`../idea-critic-v4-1019/`) cut false-NO-GO on Qwen3.5-397B-A17B from 0.911 (V0) to 0.378 but made 3 false GOs in 45 bad-decision calls, so the frozen zero-false-GO rule made it a LOSS; on two other models V4's false-GO rate was higher still (`../idea-critic-v4-xmodel-1019/`). Can a variant that adds an explicit kill-criteria check before any GO keep V4's accuracy gain with zero false GOs?

## Tuning (done, on the tune split only)

Tune split: 118 cases, the 88 of the three earlier idea-critic benches plus the 30 V4 held-out cases (spent for V4, which was never tuned on them, so they are free for V5). Qwen3.5-397B-A17B only, 3 samples per case, thinking off, temperature 0.7, max_tokens 3000. V0, V4 and BASE are read from the committed outputs of the benches that made them. Selection rule fixed before any tune call (it is in the `bench_v5.py` docstring): among variants with tune false-GO <= 0.03, pick the highest tune accuracy (a gap under 0.01 goes to lower false-GO, then fewer completion tokens); if none is eligible, the lowest false-GO.

Five variants, all V4 plus one change (`dev/mk_variants5.py` rebuilds them from V4 by asserted replacements). Round 1: `v5a`, `v5b`, `v5c`, three wordings of a kill-criteria check before any go in step 6. Round 2, written after round 1: `v5d`, `v5e`, a stated-edge requirement in the first call (`v5e` adds the `v5c` check). Results on the 118 tune cases (accuracy / false-GO / false-NO-GO); V0 0.602 / 0 / 0.797, V4 0.774 / 0.023 / 0.429, BASE 0.757 / 0.006 / 0.480:

| Variant | Accuracy | False-GO | False-NO-GO | On the 30 V4 held-out cases |
|---|---|---|---|---|
| v5a | 0.766 | 0.045 | 0.424 | 0.733 / 0.111 / 0.422 |
| v5b | 0.766 | 0.028 | 0.441 | 0.722 / 0.067 / 0.489 |
| v5c | 0.771 | 0.040 | 0.418 | 0.722 / 0.089 / 0.467 |
| v5d | 0.565 | 0 | 0.870 | 0.544 / 0 / 0.911 |
| v5e | 0.562 | 0 | 0.876 | 0.544 / 0 / 0.911 |

Selected by the rule: `v5b` (eligible: v5b, v5d, v5e; highest accuracy of those). It is `prompts/skill_v5.txt`, and it is the only V5 wording that is run on the held-out set.

What the tuning showed: in `v5b`, 103 of 103 first-call GOs stayed GO after the steps below them (the kill check never changed a decision, the first call decides), and 5 of its 177 bad-decision calls were GO, from three cases whose proposals named concerns (reliability, buyer perception of the product) that the model judged to be risks rather than blockers. Requiring a stated edge removed every false GO but also most true GOs. I do not expect V5 to pass the zero-false-GO guard.

## Held-out design

- Corpus: `corpus.json`, 30 fresh cases (15 good, 15 bad decisions), each from a Wikipedia page fetched 2026-10-19 whose verbatim `evidence_quote` supports the label. The prompt states the situation, the proposal and the risks raised, with no names or hindsight. Disjoint by id and source URL from every earlier idea-critic corpus (including V4's and V3's recorded ids) and from every Wikipedia page cited elsewhere in the repo (`scripts/test_idea_critic_v5.py`).
- Arms: V0 (`../idea-critic-v2-1019/prompts/skill_v0.txt`, the shipped skill text), V4 (`../idea-critic-v4-1019/prompts/skill_v4.txt`), V5 (`prompts/skill_v5.txt`), BASE (no system prompt). All four are generated here, on these cases.
- Models: Qwen3.5-397B-A17B, DeepSeek-V4-Flash, GLM-5.2, the three models of the V4 benches. Thinking off, max_tokens 3000, temperature 0.7, 3 samples per case and arm, one run, no retries beyond the transport retries in `bench.call`. No prompt, parameter or parser is tuned per model.
- Free PCSS endpoint only, public data only, no Anthropic or paid calls.
- Metrics: accuracy, false-GO (GO on a bad decision, over the 15 bad cases), false-NO-GO (NO-GO on a good decision, over the 15 good cases), invalid decisions (counted wrong), completion tokens per call. Paired per-case bootstrap, 10,000 resamples, seed 1 (`boot` in `scripts/rival_eval.py`).

## Frozen keep rule (unchanged from V4)

Headline, pooled over the three models: per case, each arm's accuracy and GO rate are averaged over the models, then bootstrapped over the 30 cases (15 bad cases for false-GO). WIN iff the V5-minus-V0 paired accuracy CI lower bound is above 0 and V5's false-GO mean is exactly 0 over its 135 bad-decision calls. LOSS if the CI upper bound is below 0 or the guard fails. Otherwise TIE. The same rule applied to each model alone (45 bad-decision calls) is reported beside the headline and decides nothing.

V5-minus-V4 and V5-minus-BASE differences are reported, not decisive.

`.claude/skills/idea-critic/SKILL.md` is not touched by this bench under any outcome; a WIN would only be evidence for the owner, who decides whether to reopen it.

## Expectation stated in advance

I expect V5 minus V0 to be positive on accuracy, close to V4's, and at least one false GO somewhere in 135 bad-decision calls, so the likeliest verdict is LOSS by the guard. A model that mostly says GO would show high false-GO under every arm and would be reported as is.

## Limits

Thirty cases and three models give wide intervals. At a 2 to 3% false-GO rate a zero over 135 calls is partly luck. The held-out labels are hindsight labels from Wikipedia and several cases carry the failure in their own risk lists, so the proposal text may not separate good from bad. The models are non-Claude; the skill ships for a Claude host. Thinking is off, so reasoning-model strength is not tested. The tune set overlaps the data V4 was designed on (88 of 118 cases), which favors V4 and V5 over V0 on those cases; the 30 V4 held-out cases are the unbiased tune subset.

## Amendment, 2026-10-19: two held-out cases replaced

After the first held-out run, `scripts/test_idea_critic_v5.py` showed that two of the 30 cases (`phone-maker-entry-2014`, `short-video-service-2018`) cite Wikipedia pages already used by the earlier outcome bench, so they were not fresh: they belong to the 88 cases V4 was designed on and V5 was tuned on. My own pre-run disjointness check had a bug (it scanned only 26 of the repo's page URLs). The two cases were replaced by `personal-transporter-2001` and `social-site-acquisition-2005`, chosen from pages checked unused (the test passes) and without looking at any output; nothing else in the design changed. The calls already made on the two voided cases stay in `ledger.jsonl` and `outputs/` but no report, token count or test uses them. The replacement cases are scored for the first time after the `amended` ledger line; the other 28 cases keep their first-run outputs, so no case was sampled twice. `bench_v5.py` changed in one place only, so that token counts skip voided cases. The original `preregistered` line (first in the ledger) carries the hash of the first `SHA256-frozen.txt`; the `amended` line carries the hash of the current one. The verdict was computed after the amendment. The decision to replace did not depend on any result, but I had seen the first-run results of the 30 cases when I made it.
