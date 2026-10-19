growth-analytics outcome bench, 2026-10-19. Cost: $0 (free PCSS models only; no claude -p). All data synthetic and fictional.

BLUF
- PILOT, CEILING, UNINFORMATIVE: the instrument failed, so this is not a tie and not a verdict on the skill. Every arm, including no skill, is near full recall (NONE 0.979) because each planted error was announced in a sentence of the readout; a follow-up (`docs/bench/growth-outcome-r2-1019`) plants errors that must be computed from raw numbers and was calibrated on a tune split. The preregistered rule printed NOT A WIN for this run, but with a ceiling that label carries no information. On planted-error recall the shipped skill is indistinguishable from the marketingskills analytics and ab-testing text and from no skill. 88 fresh A/B readouts (65 with 1 to 3 planted analysis errors, 23 sound controls), 2 samples per arm and readout, answers scored deterministically against an answer key written and hashed before any readout or answer existed. The growth-analytics rounds so far rest on judge preference alone; this pilot does not confirm a gain and cannot separate the arms.
- Outcomes (95% bootstrap CI over scenarios): planted-error recall V0 0.987 [0.967, 1.000], RIVAL 0.988 [0.973, 1.000], NONE 0.979 [0.954, 1.000]. Share of flawed readouts held: V0 0.992, RIVAL 0.985, NONE 1.000. Sound controls correctly shipped (n=23): 1.000 in every arm.
- Guardrails: false-alarm rate (sound categories flagged) V0 0.019 [0.008, 0.031], RIVAL 0.013 [0.005, 0.022], NONE 0.013 [0.004, 0.024]; mean output tokens V0 222, RIVAL 255, NONE 239 (words 149, 174, 165); unparsed answers 0 in every arm; 0 errors, 0 missing answers.
- Paired V0 minus RIVAL: recall -0.001 [-0.024, +0.019] (rule 1 needs a lower bound above 0: failed); false alarms +0.006 [-0.006, +0.019] (rule 2 met); benign pass +0.000 [+0.000, +0.000] (rule 3 met); tokens 222 against 255 (rule 4 met); completeness met. V0 minus NONE: recall +0.008 [-0.021, +0.038], false alarms +0.005 [-0.008, +0.019].
- What this does and does not say: with recall near 1.0 in all three arms the interval width is 0.02 to 0.04, so a true gain of that size or smaller is invisible here, and any gain on real readouts (errors buried in tables, no named checklist) is untested. The one measurable difference is length: the shipped skill answers in about 13% fewer tokens than the rival at the same recall.
- No SKILL.md edit ships here and none is proposed from this result.

Method (PREREGISTERED.md; hashes in SHA256-frozen.txt and ledger.jsonl)
- Key: key.py draws, with a fixed seed (1019), which of six analysis errors (SRM, PEEK, POWER, SIMPSON, DENOM, NOVELTY) each of 96 scenarios plants (0, 1, 2 or 3: 24 each) and states the rest as sound practice, each via one of two verbatim anchor phrases. Gold = flag exactly the planted categories; HOLD iff one is planted.
- Readouts: DeepSeek-V4-Flash wrote each from the anchors; a deterministic check kept it only if all anchors occur, no opposite anchor occurs, no stray category word or generic hedge occurs and length is 90 to 230 words. 88 of 96 were valid (23 benign); the preregistered floor was 80 and 20 benign. Two earlier writer-only pilots in a scratch copy (86, then 89 of 96 valid; no arm answered) are disclosed in PREREGISTERED.md. bench_check clean.
- Arms: V0 = shipped SKILL.md (byte-equal to the round-5 v0 text), RIVAL = the marketingskills text used by every earlier growth bench, NONE = "You are a helpful assistant."; identical user task (prompts/task.txt) with the category definitions and a closing ERRORS/DECISION protocol. Answers by Qwen3.5-397B-A17B at temperature 0.7. Scoring is regex parsing only; no model grades anything, so there is no grader to validate (the parser is tested on hand-written answers in scripts/test_growth_outcome_1019.py).
- Hand check of the key (one rater, a model, 10 randomly drawn readouts (shuffle seed 7) read against their keys before any arm answered): 10 of 10 matched the key cleanly.
- Run once; no re-run on the same scenarios.

Known limits
- The six categories are handed to every arm in the task text, so the test is applying a named list; a ceiling is present and visible (recall 0.98 to 0.99 in all arms).
- Readouts are explicit by construction (verbatim phrases). Real readouts hide errors; variant 1 anchors describe a mechanism without naming the error, which tests recognition only a little.
- Benign n is 23, so correct-pass intervals are degenerate at 1.000; paired CIs treat the 2 samples per scenario as one mean.
- One answering model, one writer, one parser; synthetic distribution. The skill is written for Claude and run here on another model; both skill texts run with no tools and no data.
- The 0.03 false-alarm margin, the -0.15 benign margin and the 1.25 token budget were set before any answer.

Reproduce (PCSS_KEY in the environment or the repo .env; run from this directory): `python3 key.py` (key.json unchanged), `python3 bench.py scen`, `python3 bench.py run V0 RIVAL NONE`, `python3 bench.py report`. Results: report_held.txt, per_scenario_held.json, outputs/<ARM>/<id>_<k>.txt (.tok = completion tokens).
Tests: scripts/test_growth_outcome_1019.py.
