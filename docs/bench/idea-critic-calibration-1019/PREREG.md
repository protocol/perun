# Preregistration: idea-critic calibration fix, held-out run (frozen 2026-10-19, before any held-out call)

## Question

Does the SKILL.md change (V1) cut the idea-critic's over-blocking of good decisions, without raising the rate of approving bad ones, on cases it was not tuned on?

## What is being tested

- V0: `.claude/skills/idea-critic/SKILL.md` at commit 81bc93bd (`prompts/skill_v0.txt`). The skill that scored 0.574 accuracy on the first outcome bench.
- V1: the calibration edit (`prompts/skill_v1.txt`): step 2 no longer requires the claim to beat two alternatives (it must beat do-nothing; a safer, smaller or staged alternative is a note), and step 6 says no fatal flaw means GO, defines what is not fatal alone, and says a wrongly blocked sound plan costs as much as a wrongly passed one.
- BASE: no system prompt.
- RIVAL: the rival skill text used by the r9 bench, reference only.

## History that limits the claim (stated before the run)

- The failing cases and the rules that drove them were read on the 36 first-bench cases (the tune set). Three V1 wordings were run on that set; the one reported here is the one that scored best there (dev accuracy 0.676 and 0.639 on two samples, against V0 0.574 and BASE 0.694). Dev numbers are therefore optimistic and are not evidence.
- The 24 held-out cases (`corpus.json`) were written and hashed before the first V1 edit. No held-out case or output has been read by anyone before this freeze. They are drawn from the same genre and by the same author as the tune set, so this tests generalisation to new cases, not to a new author or domain.
- Both models may partly recall these well-known outcomes; names are removed from every prompt, as in the first bench.

- A first held-out run of the Qwen arms was started before `ledger.jsonl` carried its `preregistered` line (the driver wrote its ledger to a subfolder). Its outputs were never opened or scored; they were set aside, the driver was changed to write the ledger at the bench root and to skip the event line when summing tokens, the frozen hashes were regenerated, and every held-out call was then made again after the `preregistered` event. The corpus and both skill prompts are unchanged from the first run.

## Design

- 24 cases: 12 key `good`, 12 key `bad`, all public, each with an English Wikipedia source and a verbatim evidence quote fetched 2026-10-19. None overlaps the tune set.
- Same user message and the same last-line contract as `../idea-critic-outcome-1019/bench_outcome.py` (`DECISION: GO` or `DECISION: NO-GO`; revise or hold counts as NO-GO). An unparseable call counts as wrong.
- 3 samples per case and arm at temperature 0.7; a case score is the mean of its 3 samples.
- Primary model: Qwen3.5-397B-A17B on PCSS (thinking off). Secondary model, reported separately and not part of the verdict: gpt-oss_120b (reasoning on, 6000-token budget).
- Intervals: 10,000-resample percentile bootstrap over cases, seed 1 (`boot` in `scripts/rival_eval.py`); paired differences are per case.
- The held-out run is executed once per model. A missing output (generation failure) is regenerated; no output is discarded or resampled.

## Outcomes and decision rule (primary model)

- Primary outcome: accuracy, decision matches the key.
- Guardrail: false-go rate (GO on a `bad` case) of V1 must not exceed the BASE false-go rate (point estimates over the 12 bad cases x 3 samples).
- WIN: paired accuracy V1 minus V0 has 95% CI lower bound above 0, and the guardrail holds.
- LOSS: that CI upper bound is below 0, or the guardrail is broken.
- TIE: anything else.
- Reported but not decisive: V1 minus BASE and V1 minus RIVAL accuracy (paired), false-no-go rate, invalid decisions, completion tokens per call.

## Frozen files

`SHA256-frozen.txt` lists the sha256 of `corpus.json`, `prompts/skill_v0.txt`, `prompts/skill_v1.txt`, `bench_calibration.py` and `../idea-critic-outcome-1019/bench_outcome.py`. Any change to these after the freeze voids the run.

## Amendment after the run (2026-10-19)

The first outcome bench was moved from `docs/bench/idea-critic-outcome-1019/` to `docs/idea-critic-outcome-1019/` because it was never preregistered. That required editing only path constants in `bench_calibration.py` and `bench_outcome.py`. The two edited files are re-hashed as lines 6 and 7 of `SHA256-frozen.txt` and listed in a later `prereg_frozen` event of `ledger.jsonl`. No result, output or decision rule changed. Outcome: TIE, so the V1 edit was not shipped.
