# Preregistration: growth-analytics computed-error outcome bench, round 2 (2026-10-19)

Written and hashed (SHA256-frozen.txt, ledger event `preregistered`) after the tune-split calibration below and before the held-out scenarios exist and before any arm answers on them. Free PCSS models only; no `claude -p`; all data synthetic and fictional.

## Why a round 2
The first outcome bench (`growth-outcome-1019`, kept as a pilot) hit a ceiling: the no-skill arm recalled 0.979 of planted errors, so shipped, rival and no skill all scored about the same and the result says nothing about whether the skill helps. The cause was that every planted error was announced in a sentence of the readout (a model-written spec stated, for example, that a test was stopped at the first significant result), so the reviewer only had to notice a phrase. This round plants errors that must be computed from raw numbers.

## Question
Given an A/B readout built from raw counts, does the reviewer find the planted analysis errors by computing them, hold the rollout when one is present, and leave a sound readout alone? Guardrails: false alarms, benign pass and output length.

## Scenarios and answer key (key.py; no model writes anything)
key.py builds each readout from numbers: design inputs (alpha, power, baseline rate, target lift), start date, planned duration and final-readout date, arm session and order counts, a per-device table of users and orders for both arms, a reported conversion rate and lift, and a daily lift series. No sentence in the readout names or describes an error; the only text is a fixed template and the figures. 24 contexts x 4 strata (0, 1, 2, 3 planted errors of six) = 96 scenarios at one difficulty level; the 24 with no planted error are the benign controls. Which errors are planted is drawn from a fixed seed (held-out 3019, tune 2019) and never depends on a model output.

The planted set is recomputed from the numbers by `truth()` and a scenario is kept only if the recomputed set equals the planted set; `make()` stops otherwise, so the key cannot drift from the text. Gold rules (planted and sound values never sit between the two limits, so any reasonable threshold agrees with the gold):
- SRM: |treatment users - control users| / sqrt(treatment users + control users) at least 3.5 (planted); at most 1.5 (sound).
- POWER: smaller-arm users below 0.9 x the two-proportion sample size (alpha 0.05 two-sided, power 80%, baseline rate, target lift) (planted); at least 1.05 x (sound).
- PEEK: days from start to final readout below 0.8 x planned duration (planted); at least 1.0 x (sound).
- DENOM: the reported control rate equals orders / sessions rather than orders / users (planted); equals orders / users (sound).
- SIMPSON: pooled lift positive and negative (below -1%) in both device segments (planted); positive (at least +1%) in both segments and pooled (sound).
- NOVELTY: mean of the last three daily lifts below 0.5 x the first three (planted); between 0.65 x and 1.5 x (sound).
Gold: flag exactly the planted categories and decide HOLD when at least one is planted, SHIP when none is. Levels 0 to 3 move planted and sound values nearer their limits (key.py constants); level 2 additionally shows no per-arm user total (the users must be summed from the device table) and level 3 also states a planned end date instead of a duration.

## Calibration on a tune split (calibration.json, report_tune.txt)
A separate tune split (key_tune.json, seed 2019, 48 scenarios per level, levels 0 to 3, different scenarios from the held-out) was answered by the NONE arm only (2 samples, temperature 0.7); skill and rival never saw it. Rule, fixed before the final tune run: choose the lowest level whose no-skill recall is in [0.5, 0.7]; the held-out set is generated at that level and is not filtered, resampled or edited by any answer. Disclosed history: two earlier instrument versions were run on the tune split and discarded, both too easy (no-skill recall 1.000 at every level with numeric rules and formulas in the task text; 0.78 to 0.88 with definitions only and 400-word answers); their prompts, reports, outputs and ledgers are kept (`prompts/task_attempt*.txt`, `report_tune_attempt*.txt`, `outputs/tune_attempt*`, `tune_ledger_attempt*.jsonl`). The final version (150-word answers, level-dependent rendering) gave NONE recall 0.808, 0.708, 0.560, 0.655 at levels 0 to 3. Level 2 is the lowest in the band, so the held-out level is 2 (n = 96, seed 3019). At that level the no-skill arm also shows a benign correct-pass rate near 0 and a false-alarm rate near 0.33 on tune (it flags SRM and DENOM from session counts instead of summing users), so recall alone can be inflated by over-flagging; the guardrails below exist for that reason.

## Arms (each arm's text is the answering model's system prompt)
- V0: the shipped `growth-analytics` SKILL.md as on origin/main at freeze (prompts/V0.md; byte-equal to the pilot's copy and to `docs/bench/growth-r5-1018/frozen/growth-analytics.v0.md`).
- RIVAL: the marketingskills analytics and ab-testing text used by every earlier growth bench (prompts/RIVAL.txt, byte-equal to the pilot's copy).
- NONE: no skill, system prompt "You are a helpful assistant." (prompts/NONE.txt).
Every arm gets the same user message: prompts/task.txt (names the six categories with one-line definitions and no thresholds, caps the answer at 150 words, requires closing `ERRORS:` and `DECISION: HOLD|SHIP` lines) followed by the readout.

## Measurement
Answering model Qwen3.5-397B-A17B, temperature 0.7, 2 samples per arm and scenario, non-thinking mode. Scoring is deterministic (bench.py `parse`, `score_one`): the last `ERRORS:` and `DECISION:` lines are read; an answer lacking either, or whose `ERRORS:` line holds neither a category code nor NONE, is unparsed and scores as no flags and a wrong decision. No model grades anything.
- Recall (primary outcome): on scenarios with a planted error, the share of planted categories flagged; per scenario averaged over the 2 samples.
- Hold on flawed (descriptive) and correct pass on the benign controls (outcome): share of answers that decide HOLD, respectively SHIP.
- False-alarm rate (guardrail): share of the sound categories flagged, per scenario, over all scenarios.
- Output tokens (guardrail): mean completion tokens from the API usage field.
- Unparsed rate (guardrail).
Paired percentile bootstrap over scenarios, 10,000 resamples, seed 1, 95% interval; differences are V0 minus the other arm, paired per scenario.

## Keep rule: V0 against RIVAL (all must hold; the margins are set here, before any held-out answer)
1. Recall, V0 minus RIVAL: CI lower bound above 0.
2. False-alarm rate, V0 minus RIVAL: CI upper bound at most +0.03.
3. Correct pass on benign controls, V0 minus RIVAL: CI lower bound at least -0.15.
4. Mean output tokens, V0 at most 1.25 x RIVAL.
5. Completeness: unparsed rate at most 0.05 in both arms and no missing answer in either.
All five hold: WIN. Otherwise, if the recall CI upper bound is below 0: LOSS. Otherwise NOT A WIN. Instrument check: if the held-out no-skill recall is outside [0.4, 0.8] the label is UNINFORMATIVE (instrument failed, the verdict it would have given is printed but carries no decision), because a ceiling or a floor cannot rank arms. The same rule is printed for V0 against NONE as a descriptive check. There is no candidate edit to SKILL.md in this bench, so none ships whatever the result. No re-run on the same held-out scenarios.

## Known limits
- Gold thresholds are this bench's definitions of each error; a reviewer using a different but reasonable threshold agrees with the gold because no scenario lies between the limits. Errors outside the six categories are not scored.
- The numbers are synthetic and templated; real readouts carry more noise and layouts. Computation is by a tool-less model with a 150-word answer, which tests whether the reviewer computes at all; a skill written for an agent with a data connection is run here without it.
- Level 2 floors the no-skill benign pass rate; benign controls (24) then separate arms weakly.
- One answering model family; the skill is written for Claude and run on another model.
- Parsing rewards following the closing-line protocol; unparsed rate is reported per arm.
- Held-out and tune readouts share a template; the shared template phrases are listed in overlap-allow.txt for the shingle-overlap check, the numbers differ.
