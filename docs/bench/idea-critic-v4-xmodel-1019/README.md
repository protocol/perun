# idea-critic V4 on two other models

BLUF: on the same frozen 30-case held-out set, V4 beats the shipped skill (V0) on accuracy in the pool (+0.128 [0.022, 0.239]) but makes false GOs on both new models (pooled 0.156 against V0's 0.067), so the frozen zero-false-GO rule gives a pooled LOSS, as on Qwen. The pooled accuracy gain is not a Qwen quirk, but it is carried by GLM-5.2 (+0.222 [0.100, 0.356]); on DeepSeek-V4-Flash it is not significant (+0.033 [-0.100, 0.167]). The false-GO guard fails on both. `SKILL.md` is unchanged. Preregistration: `PREREG.md` (frozen by `SHA256-frozen.txt` and the first ledger line, before any scored call).

Run 2026-10-19 on the free PCSS endpoint (thinking off, temperature 0.7, 3 samples per case and arm, 30 cases, 15 good and 15 bad). Corpus, prompts, scorer and report code are the V4 bench's, referenced by hash and not copied. Reproduce: `PCSS_ENV=<file with PCSS_KEY> python3 bench_xmodel.py run|report MODEL`, then `pooled`.

| Model | Arm | Accuracy | False-GO | False-NO-GO | Completion tokens per call |
|---|---|---|---|---|---|
| DeepSeek-V4-Flash | V0 | 0.533 | 0.000 | 0.933 | 37 |
| DeepSeek-V4-Flash | V4 | 0.567 | 0.200 | 0.667 | 102 |
| DeepSeek-V4-Flash | BASE | 0.656 | 0.178 | 0.511 | 302 |
| GLM-5.2 | V0 | 0.689 | 0.133 | 0.489 | 373 |
| GLM-5.2 | V4 | 0.911 | 0.111 | 0.067 | 401 |
| GLM-5.2 | BASE | 0.722 | 0.022 | 0.533 | 327 |
| Pooled (2 new) | V0 | 0.611 | 0.067 | 0.711 | |
| Pooled (2 new) | V4 | 0.739 | 0.156 | 0.367 | |
| Pooled (2 new) | BASE | 0.689 | 0.100 | 0.522 | |
| Qwen3.5-397B-A17B (V4 bench, not re-run) | V0 | 0.544 | 0.000 | 0.911 | |
| Qwen3.5-397B-A17B (V4 bench, not re-run) | V4 | 0.778 | 0.067 | 0.378 | |
| Qwen3.5-397B-A17B (V4 bench, not re-run) | BASE | 0.644 | 0.000 | 0.711 | |
| Pooled (3, descriptive) | V0 | 0.589 | 0.044 | 0.778 | |
| Pooled (3, descriptive) | V4 | 0.752 | 0.126 | 0.370 | |
| Pooled (3, descriptive) | BASE | 0.674 | 0.067 | 0.585 | |

Frozen keep rule (V4 minus V0 accuracy CI lower bound above 0 and V4 false-GO exactly 0):

| Scope | V4 minus V0 accuracy [95% CI] | V4 false-GO | Verdict |
|---|---|---|---|
| DeepSeek-V4-Flash | +0.033 [-0.100, 0.167] | 0.200 | LOSS (guard) |
| GLM-5.2 | +0.222 [0.100, 0.356] | 0.111 | LOSS (guard) |
| Pooled, 2 new models (headline) | +0.128 [0.022, 0.239] | 0.156 | LOSS (guard) |
| Pooled, 3 models (descriptive) | +0.163 [0.056, 0.278] | 0.126 | no verdict |

Reading, with the caveats the numbers allow:

- The accuracy gain over V0 repeats on GLM-5.2 and in the pool, and is not distinguishable from zero on DeepSeek-V4-Flash alone (its V0 answers are about 37 tokens, so V0 mostly says NO-GO without reasoning).
- V4 minus BASE is a tie on the two new models (+0.050 [-0.044, 0.144]); V4 is no better than the model's own judgment on average, and it is worse than BASE on false-GO on GLM-5.2 (0.111 against 0.022). Both of those are descriptive, not part of the rule.
- V4's false-GO is higher on both new models (0.200, 0.111) than on Qwen (0.067), and GLM-5.2 also makes false GOs under V0 (0.133) and BASE (0.022), so the guard failure is partly the model and partly the corpus. V0 scores zero false-GO on two of three models (Qwen, DeepSeek-V4-Flash) by saying NO-GO most of the time (false-NO-GO 0.911 and 0.933).
- Per-call false-GO counts are small (45 bad-decision calls per model and arm), so each rate has a wide interval; `results-*.json` carry the bootstrap intervals.
- Limits as in `PREREG.md`: two non-Claude models, thinking off, 30 cases, corpus possibly memorized. Not run on the Claude host the skill ships for.
