# Preregistration: idea-critic V2 blocker test, held-out run (frozen 2026-10-19, before any held-out call)

## Question

Does replacing the idea-critic's go/no-go close with a blocker test (V2) stop it from saying NO-GO to good decisions, without approving more bad ones, on fresh cases it was never tuned on?

## Why V2 (diagnosis, read on the training cases only)

The two earlier exploratory benches (`../../idea-critic-outcome-1019`, `../../idea-critic-calibration-1019`; neither is a valid preregistered run, so both live outside `docs/bench/`) show the current skill (V0) saying NO-GO to 46 of 54 good-decision calls on the first bench and 21 of 36 on the second, while it approves no bad decision (false-go 0.000 on both). Reading those V0 transcripts, almost every wrong NO-GO cites one of three things: a cheaper, smaller or staged alternative (step 2 says the claim "must beat all three" options), a forward-looking claim that is "unproven" or "assumed" (step 5), or a pre-mortem failure story (step 4). None of these is a fact showing the plan fails; each is a risk. The skill never says how a risk differs from a reason to stop, so every listed risk counts against the plan and uncertainty itself becomes the blocker. The earlier V1 edit added a sentence on what is not fatal but kept the rest of the method unchanged, and it tied.

V2 (`prompts/skill_v2.txt`) makes these structural changes to `prompts/skill_v0.txt`:

- Step 2: the claim must beat *do nothing*; a cheaper, smaller, staged or safer alternative blocks only if it reaches the same upside on the stated facts, otherwise it shapes the first step.
- Step 6: the decision comes from a blocker test. Every objection is sorted into a *blocker* (a fact already in hand that shows the plan fails as proposed: its numbers do not work, its own evidence contradicts its core claim, an alternative reaches the same upside cheaper, or the stated facts already show the target users do not want it) or a *risk* (anything not yet shown: unproven demand, no experience, high price, incumbents, execution, the requester's own listed risks, a pre-mortem story, a one-way door). Risks become kill criteria and never decide the call. No blocker means go; no-go needs a named blocker. The answer must write the sort before the decision, as a `Blockers:` line (each with the fact it rests on, or NONE) and a `Risks:` line.
- Prime directive: surviving means no blocker was found; open risks become kill criteria, not counts against the claim.
- Step 3: only a *stated* north star can turn a sound idea into a no; an assumed one never blocks.

## History that limits the claim (stated before the run)

- Training set: the 60 cases of the two earlier benches. Their V0 and no-skill outputs were read to diagnose the failure, and two V2 wordings were run on them, once each; those dev numbers are optimistic and are not evidence. V2a (`dev/skill_v2a.txt`: the step 2 and step 6 changes, without the written sort) tied V0 on dev: accuracy 0.656 vs 0.628, paired +0.028 [-0.028, 0.078], false-go 0.000 vs 0.000 (`dev/v2a/`). Its transcripts showed the model naming a risk and then blocking on it anyway, so V2b added the written `Blockers:`/`Risks:` sort, the prime-directive line and the step 3 change. V2b is the frozen V2. On dev it scored accuracy 0.761 vs V0 0.628 and BASE 0.783, paired V2 minus V0 +0.133 [0.061, 0.211], but false-go 0.022 (2 of 90 calls) vs V0 0.000, so on dev it already breaks the guardrail below (`dev/`). The guardrail was written before any V2 output existed and is kept unchanged. No other wording was tried.
- Held-out set: 28 fresh cases in `corpus.json` (14 key `good`, 14 key `bad`), written by the same author in the same genre after the diagnosis and before any V2 output was read, hashed at 2026-10-19T09:11:13Z (sha256 `8abea857...`). No held-out output exists before the `preregistered` line of `ledger.jsonl`. None overlaps either earlier bench by id or source page. This tests new cases, not a new author or domain.
- Each case has an English Wikipedia source and a verbatim evidence quote taken from the page text fetched 2026-10-19; names are removed from every prompt; models may still partly recall famous outcomes.

## Design

- Arms: V0 (current `.claude/skills/idea-critic/SKILL.md`, identical to `prompts/skill_v0.txt`), V2 (`prompts/skill_v2.txt`), BASE (no system prompt).
- Same user message, parser and last-line contract as `../../idea-critic-outcome-1019/bench_outcome.py` (`DECISION: GO` or `DECISION: NO-GO`; revise or hold counts as NO-GO). An unparseable call counts as wrong.
- 3 samples per case and arm at temperature 0.7; a case score is the mean of its 3 samples.
- One model: Qwen3.5-397B-A17B on the free PCSS endpoint, thinking off. No secondary model.
- Intervals: 10,000-resample percentile bootstrap over cases, seed 1 (`boot` in `scripts/rival_eval.py`); paired differences are per case.
- The held-out run is executed once. A missing output (generation failure) is regenerated; no output is discarded or resampled.

## Outcomes and decision rule

- Primary outcome: accuracy, decision matches the key.
- Guardrail: V2's false-go rate (GO on a `bad` case, point estimate over 14 cases x 3 samples) must not exceed V0's.
- WIN: paired accuracy V2 minus V0 has a 95% CI lower bound above 0 and the guardrail holds. Only a WIN ships V2 into `SKILL.md`.
- LOSS: that CI upper bound is below 0, or the guardrail is broken.
- TIE: anything else; `SKILL.md` stays unchanged.
- Reported but not decisive: V2 minus BASE (paired), false-no-go rate, invalid decisions, completion tokens per call.
- `bench_v2.py heldout report` computes the verdict with this rule (`verdict()`).

## Frozen files

`SHA256-frozen.txt` lists the sha256 of this file, `corpus.json`, `prompts/skill_v0.txt`, `prompts/skill_v2.txt`, `bench_v2.py` and `../../idea-critic-outcome-1019/bench_outcome.py`. Any change to these after the freeze voids the run.
