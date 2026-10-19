# Preregistration: growth-analytics outcome bench (2026-10-19)

Written and hashed (SHA256-frozen.txt, ledger event `preregistered`) before any scenario is written for this bench and before any arm answers. Free PCSS models only; no `claude -p`; all data synthetic and fictional. Scenarios file: scenarios_held.json (written after this file is frozen, then hashed with its own ledger event).

## Question
The growth-analytics rounds (`baseline-gs-1018` to `growth-r5-1018`) compare the shipped `growth-analytics` skill with the marketingskills analytics and ab-testing text only by a blind judge's preference, and none of them showed a confirmed win. Preference is a proxy. This bench asks what a product analyst would feel instead: given an A/B test readout with known planted analysis errors and known sound practices, does the reviewer flag the real errors, hold the rollout, and leave a sound readout alone? Guardrails: false alarms and output length.

## Answer key (key.py, key.json; hashed before any scenario is written)
24 fictional experiment contexts x 4 strata = 96 scenarios. A scenario plants 0, 1, 2 or 3 of six analysis errors (SRM, PEEK, POWER, SIMPSON, DENOM, NOVELTY) and states the other categories as explicitly sound practice. Each category, planted or sound, is carried by one of two fixed verbatim anchor phrases that the readout writer must include (24 phrases in all, fixed in key.py; variant 0 states the error plainly, variant 1 describes only the mechanism). Gold: a reviewer should flag exactly the planted categories and decide HOLD when at least one is planted, SHIP when none is. The 24 scenarios with no planted error are the benign controls. Which categories are planted is drawn from a fixed seed (1019) in key.py; it does not depend on any model output.

## Scenarios
Written after this file is frozen, by `bench.py scen`: a writer model (DeepSeek-V4-Flash, temperature 0.9, up to 10 attempts per scenario) is told the experiment context and the anchors and nothing about the answer. A readout is valid only if every required anchor occurs verbatim (case, spacing and dash variants ignored), no anchor of the opposite polarity occurs, a fixed list of stray words that would plant or cancel a category outside its anchor (key.py STRAY) and a fixed list of generic hedges (key.py GENERIC) are absent once the anchors are removed, and its length is 90 to 230 words. The bench needs at least 80 valid scenarios of which at least 20 benign; otherwise it stops and reports no verdict. scenarios_held.json is hashed into SHA256-frozen.txt with a ledger event before any arm answers. The lane agent also reads 10 written readouts against the key by hand and records the result in README.txt (one rater, a model). `bench_check.py --changed origin/main` must pass.

Writer pilot, disclosed: before this freeze, two full runs of the writer step were made in a scratch copy outside the repository to check that the validity rule yields enough scenarios (86 of 96, then 89 of 96 after the GENERIC hedge list and a no-hedge line in the writer brief were added, because the first pilot showed a writer cancelling a planted denominator error with a "we also checked" clause). No arm answered in either pilot; their output is not committed or reused, and the committed run below writes fresh scenarios.

## Arms (each arm's text is the answering model's system prompt)
- V0: the shipped `growth-analytics` SKILL.md as on origin/main at freeze (prompts/V0.md; byte-equal to `docs/bench/growth-r5-1018/frozen/growth-analytics.v0.md`, the round-5 text that was not replaced).
- RIVAL: the marketingskills analytics and ab-testing text used by every earlier growth bench (prompts/RIVAL.txt, byte-equal to `docs/bench/growth-analytics-rubricfree-1016/prompts/rival.txt`, the file the round-5 preregistration names).
- NONE: no skill, the system prompt "You are a helpful assistant." (prompts/NONE.txt).
Every arm gets the same user message: prompts/task.txt (names the six categories with one-line definitions, tells the reviewer to flag a category only when the readout describes it as present, caps the answer at 250 words, and requires a closing `ERRORS:` line and a `DECISION: HOLD|SHIP` line) followed by the readout.

## Measurement
Answering model Qwen3.5-397B-A17B, temperature 0.7, 2 samples per arm and scenario, non-thinking mode. Scoring is deterministic (bench.py `parse`, `score_one`): the last `ERRORS:` and `DECISION:` lines are read; an answer lacking either, or whose `ERRORS:` line holds neither a category code nor NONE, is unparsed and scores as no flags and a wrong decision. No model grades anything, so there is no grader to validate; the parser and scorer are tested on hand-written answers (scripts/test_growth_outcome_1019.py).
- Recall (outcome): on scenarios with a planted error, the share of planted categories flagged; per scenario averaged over the 2 samples.
- Hold on flawed (outcome, descriptive): share of answers on those scenarios that decide HOLD.
- Correct pass (outcome): on the benign controls, the share of answers that decide SHIP.
- False-alarm rate (guardrail): share of the sound categories flagged, per scenario, over all scenarios.
- Output tokens (guardrail): mean completion tokens from the API usage field; words reported too.
- Unparsed rate (guardrail): share of answers that are unparsed.
Paired percentile bootstrap over scenarios, 10,000 resamples, seed 1, 95% interval; differences are V0 minus the other arm, paired per scenario.

## Keep rule: V0 against RIVAL (all must hold on this one run; the margins are set here, before any answer)
1. Recall, V0 minus RIVAL: CI lower bound above 0.
2. False-alarm rate, V0 minus RIVAL: CI upper bound at most +0.03 (non-inferiority; about one extra false flag in thirty-three sound categories).
3. Correct pass on benign controls, V0 minus RIVAL: CI lower bound at least -0.15 (non-inferiority; n is only about 23 controls, so a tighter bound would fail on width).
4. Mean output tokens, V0 at most 1.25 x RIVAL.
5. Completeness: unparsed rate at most 0.05 in both arms and no missing answer in either.
All five hold: WIN over the rival on this outcome. Otherwise, if the recall CI upper bound is below 0: LOSS. Otherwise NOT A WIN (a tie, or a win blocked by a guardrail or by width). The same rule is printed for V0 against NONE as a descriptive check of whether the skill helps at all; it carries no decision. There is no candidate edit to SKILL.md in this bench, so none ships whatever the result; a LOSS or a NOT A WIN is recorded as a finding for a separate, separately preregistered change. No re-run on the same scenarios.

## Known limits
- The six categories are a fixed list given to every arm in the task text, so the question is applying a named list to a readout, which every arm can do from the prompt alone; a ceiling effect (every arm near full recall) is possible and would read as a tie. Recall against the planted list says nothing about errors outside these six.
- Readouts are model-written from fixed phrases and so are explicit; real readouts bury errors in tables and charts. Variant 1 anchors describe a mechanism without naming the error, which tests recognition a little, not a lot.
- The shipped skill and the rival are long guidance texts used as a system prompt with no tools and no data; the rival is a tool-less run of a text written for an agent with a data connection.
- One answering model family, one writer; the skill is written for Claude and run here on another model.
- Parsing rewards following the closing-line protocol; the unparsed rate is reported per arm so a format loss is visible rather than hidden.
- Synthetic distribution; not a claim about real products or real tests.
