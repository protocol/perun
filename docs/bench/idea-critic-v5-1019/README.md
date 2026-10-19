# idea-critic V5: an explicit kill check before any GO (LOSS)

Date: 2026-10-19. Design and keep rule: `PREREGISTERED.md` (frozen before any held-out call; hashes in `SHA256-frozen.txt`, first line of `ledger.jsonl`). Two held-out cases were found not fresh after the first run and were replaced; the amendment section of `PREREGISTERED.md` and the `amended` ledger line record it.

**BLUF: V5 does not fix V4's false GOs. Pooled over three models V5 made false GOs on 14.1% of bad-decision calls (V4 11.1%, V0 1.5%, BASE 4.4%), so the frozen zero-false-GO guard fails and the verdict is LOSS. Its accuracy gain over V0 is real (+0.130, 95% CI 0.011 to 0.244) and about equal to V4's. `.claude/skills/idea-critic/SKILL.md` is unchanged.**

## What was tested

V5 is V4 plus a kill check in step 6 that reads each risk the proposal names for three conditions (core claim, own facts say it will happen, too big or irreversible to stop) and makes a risk a blocker only when all three hold (`prompts/skill_v5.txt`; the diff against V4 is `KC_B` in `dev/mk_variants5.py`). Five wordings were tried on a 118-case tune split with Qwen3.5-397B-A17B and the preregistered rule picked this one (table in `PREREGISTERED.md`, outputs in `tune/`). Held-out: 30 fresh cases (15 good, 15 bad decisions, Wikipedia-sourced, disjoint from every earlier corpus), arms V0, V4, V5, BASE, three PCSS models, 3 samples per case, thinking off.

## Held-out result (accuracy / false-GO / false-NO-GO)

| Scope | V0 | V4 | V5 | BASE |
|---|---|---|---|---|
| Pooled, 3 models (headline) | 0.589 / 0.015 / 0.807 | 0.737 / 0.111 / 0.415 | 0.719 / 0.141 / 0.422 | 0.715 / 0.044 / 0.519 |
| Qwen3.5-397B-A17B | 0.589 / 0 / 0.822 | 0.767 / 0.067 / 0.400 | 0.711 / 0.089 / 0.489 | 0.689 / 0.067 / 0.556 |
| DeepSeek-V4-Flash | 0.500 / 0 / 1.000 | 0.600 / 0.044 / 0.756 | 0.622 / 0.111 / 0.644 | 0.744 / 0.067 / 0.444 |
| GLM-5.2 | 0.678 / 0.044 / 0.600 | 0.844 / 0.222 / 0.089 | 0.822 / 0.222 / 0.133 | 0.711 / 0 / 0.556 |

Paired differences, pooled (95% CI, 10,000 bootstrap resamples over 30 cases):

| Difference | Accuracy | False-GO |
|---|---|---|
| V5 minus V0 | +0.130 (0.011 to 0.244) | +0.126 (0.037 to 0.230) |
| V5 minus V4 | -0.019 (-0.052 to 0.011) | +0.030 (-0.007 to 0.074) |
| V5 minus BASE | +0.004 (-0.078 to 0.081) | +0.096 (0.030 to 0.170) |

Verdict (frozen rule): pooled LOSS, because V5's false-GO mean is not 0 (135 bad-decision calls). Each model alone is also LOSS for the same reason (`results-<model>.json`). Invalid decisions (counted wrong): V0 1, BASE 2, V4 0, V5 0. Completion tokens per call (Qwen / DeepSeek / GLM): V5 482 / 191 / 388, V4 479 / 132 / 384.

## Why it fails

The kill check does not change decisions. On the tune split, 103 of 103 first-call GOs stayed GO after the steps below them, so the first call decides and any wording added after it is a note, not a gate. Moving the test into the first call (a stated-edge requirement, `v5d`, `v5e`) did remove every false GO on tune, at the cost of accuracy falling to V0's level (0.565 against 0.774 for V4, false-NO-GO 0.87). The held-out false GOs come from proposals whose stated facts read the same as a sound plan's; the evidence quotes are hindsight labels, and the proposal text does not always separate the two classes. On this evidence the accuracy gain and a zero false-GO rate are not both reachable by changing the wording of the step, and the frozen guard (zero false GOs in 135 calls) is hard for any arm that ever says GO: even BASE made false GOs.

## What would change this

A mechanism that is not prose after the first call: for example a second independent pass that sees only the first call's reasoning and is asked to find the fact that falsifies it, with its verdict allowed to flip a GO. That is a new design with its own preregistration; it is not run here. Nothing here changes the shipped skill.

## Files

`PREREGISTERED.md`, `SHA256-frozen.txt`, `ledger.jsonl` (prereg line first, then every held-out call), `corpus.json`, `prompts/skill_v5.txt`, `bench_v5.py`, `dev/` (variant builder and the five tune wordings), `tune/<variant>/` (tune outputs, ledger and results), `outputs/<model>/<arm>/` (held-out outputs), `results-<model>.json`, `results-pooled.json`. Rebuild reports offline with `python3 bench_v5.py heldout report MODEL` and `python3 bench_v5.py heldout pooled`; tests: `scripts/test_idea_critic_v5.py`.

## Frozen-file note

`SHA256-frozen.txt` is append-only. Lines 1-9 are exactly what the preregistration line in `ledger.jsonl` hashed. Lines 10-12 supersede `PREREGISTERED.md`, `corpus.json` and `bench_v5.py` after the amendment. The `amended` event's sha is the hash of the list of latest hashes per path, in the original order; the `amendment_files` event lists the three appended hashes.
