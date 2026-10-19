# Preregistration: idea-critic V4 on two other models, frozen before any call

Date: 2026-10-19. Everything in this file is frozen by `SHA256-frozen.txt` and by the first line of `ledger.jsonl` (a `preregistered` event carrying the hash of `SHA256-frozen.txt`) before the first scored call. No call to a bench prompt has been made on these models when this file is written.

## Question

The V4 bench (`../idea-critic-v4-1019/`) tested one model, Qwen3.5-397B-A17B: V4 accuracy 0.778 against V0 0.544 and no-skill 0.644, but 3 false GOs in 45 bad-decision calls, so the zero-false-GO rule made it a LOSS. Does that pattern (V4 clearly beats V0 on accuracy, false-GO guard is the weak point) hold on other free models, or is it a Qwen quirk?

## Design

- Same frozen held-out set, prompts and arms as the V4 bench, unchanged and not copied: `../idea-critic-v4-1019/corpus.json` (30 cases, 15 good, 15 bad), `prompts/skill_v4.txt`, V0 = `../idea-critic-v2-1019/prompts/skill_v0.txt`, BASE = no system prompt, the task wrapper, parser and scoring of `../../idea-critic-outcome-1019/bench_outcome.py` and the report code of `../idea-critic-v4-1019/bench_v4.py`. Their hashes are in `SHA256-frozen.txt`.
- Models, chosen before any call from the PCSS endpoint list (queried 2026-10-19) as two other families already used elsewhere in this repo's benches: `DeepSeek-V4-Flash` and `GLM-5.2`. No model was tried and dropped.
- A smoke test on one non-corpus bakery question (before this file) showed both models honor `chat_template_kwargs.enable_thinking=false` and return a parseable last line, so they run exactly as Qwen did: thinking off, max_tokens 3000, temperature 0.7, 3 samples per case and arm, one run, no retries beyond the transport retries in `bench.call`. No prompt, parameter or parser is tuned per model.
- Free PCSS endpoint only, public data only, no Anthropic or paid calls.
- Metrics per model and arm: accuracy, false-GO (GO on a bad decision, over the 15 bad cases), false-NO-GO (NO-GO on a good decision, over the 15 good cases), invalid decisions (counted wrong), completion tokens per call. Paired per-case bootstrap, 10,000 resamples, seed 1 (`boot` in `scripts/rival_eval.py`).

## Frozen keep rule (unchanged from the V4 bench)

Per model: WIN iff the paired accuracy difference V4 minus V0 has a 95% CI lower bound above 0 and V4's false-GO mean is exactly 0 over its 45 bad-decision calls. LOSS if the CI upper bound is below 0 or the guard fails. Otherwise TIE.

Pooled across the two new models: per case, each arm's accuracy, GO rate and the V4-minus-V0 difference are averaged over the two models, then bootstrapped over the 30 cases (15 bad cases for false-GO), same seed and resamples. The same rule applies: WIN iff pooled V4-minus-V0 accuracy CI lower bound is above 0 and pooled V4 false-GO is exactly 0 over 90 bad-decision calls; LOSS if the CI upper bound is below 0 or the guard fails; otherwise TIE. The pooled verdict is the headline; the two per-model verdicts are reported beside it.

A second, descriptive pool adds the existing Qwen result (read from `../idea-critic-v4-1019/outputs/`, not re-run) for three models. It decides nothing.

`.claude/skills/idea-critic/SKILL.md` is not touched by this bench under any outcome. A pooled WIN would only be evidence for the owner that the V4 loss was a guardrail-luck Qwen result; the owner decides whether to reopen it.

## Expectation stated in advance

I expect V4 minus V0 to be positive on both models, because on Qwen the gain came from removing the dissent-becomes-verdict conversion, which is model-independent in wording. I expect the false-GO guard to fail in the pool (V4 had 0.067 on Qwen and BASE-like behavior makes occasional false GOs ordinary), so the likeliest pooled verdict is LOSS by the guard, with TIE or WIN only if both models happen to make zero false GOs in 45 calls each. A model that mostly says GO would score high false-GO and low false-NO-GO under every arm; that would be reported as is.

## Limits

Thirty cases and two models give wide intervals. The three-sample design means a "zero false-GO" over 90 calls is partly luck at a 1 to 3% rate. Both models are non-Claude; the skill ships for a Claude host. The corpus may be partly memorized by any model. Thinking is off for all arms, so reasoning-model strength is not tested.
