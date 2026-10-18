# Preregistration: product-output-safety round 2, one tuned edit, held-out n=300 (2026-10-18)

The first line of `ledger.jsonl` (event `preregistered`) holds the sha256 of `SHA256-frozen.txt` (seven lines), written after the tune phase and before any held-out seed, scenario, arm answer or judge call. Base: `origin/main` at bd8ea910; `prompts/v0.md` is the shipped `.claude/skills/product-output-safety/SKILL.md` at that commit (13,375 bytes, size budget 13,378).

## Question

The shipped text (the "Answer inside the stated constraint" edit) scored 0.533 [0.483, 0.585] against the promptfoo redteam-setup rival on `docs/bench/safety-c300-1018`, so no win. Can one small further edit, tuned on a fresh tune set, lift the win rate against the rival to a lower bound above 0.5 on a fresh held-out set of n=300?

## Tune phase (done, logged in `ledger-tune.jsonl`, never reused)

- Tune set: 100 fresh scenarios `sc4t001`..`sc4t100` (`scenarios-tune.json`, seeds `seeds-tune.txt`), written by the same writer brief as the held-out set, disjoint from `docs/bench` by the 6-word-shingle rule below.
- Loss reading used the tune set only: V0 lost to the rival on 24 of 100 tune scenarios; a free GLM-5.1 pass (outside the repo) summarised why the rival's answer was preferred. Recurring causes: no dated day-by-day schedule against a stated deadline, generic test categories instead of the feature's own concrete edge cases, and framework labels in the answer.
- Three candidate edits (full files in `prompts/e1.md`..`e3.md`, each at or below the 13,378-byte budget, each paid for by deleting duplicated text), cumulative: E1 = a day-by-day schedule ending before the deadline (in the existing "Answer inside the stated constraint" bullet); E2 = E1 plus concrete edge inputs and failure sequences in the test-row bullet; E3 = E2 plus "answer in the user's domain terms, no MAP/MEASURE/MANAGE labels".
- Selection rule fixed before the tune run: freeze the candidate with the highest tune win rate. Result: V0 0.650, E1 0.665, E2 0.660, E3 0.635 (paired E1 minus V0 +0.015 [-0.055, +0.085]); E1 is frozen as `prompts/edit.md`. The tune differences are inside noise; the held-out run is the test.

## What is frozen

`PREREGISTERED.md`, `bench.py`, `prompts/v0.md`, `prompts/edit.md` (= `prompts/e1.md`), `prompts/rival.txt`, `prompts/writer_brief.txt` and `scripts/rival_eval.py` (the seven lines of `SHA256-frozen.txt` at preregistration; the held-out seed and scenario hashes are appended after and logged in a `fixtures_frozen` event). Harness: `scripts/rival_eval.py` judge protocol v2 unchanged (reason-first JSON, neutral random labels, both orders, a scenario scores 1 or 0 only when both orders agree, else 0.5; judge chain GLM-5.1, GLM-5.2, gpt-oss_120b, the first whose slot-1 rate is inside 0.4 to 0.6). Generator Qwen3.5-397B-A17B (non-thinking, temperature 0.3), never a judge. Bootstrap 10,000 resamples, seed 1, percentile, over scenarios. PCSS only, spend $0, no `claude -p`.

## Held-out scenarios

300 fresh scenarios `sc4h001`..`sc4h300`, written after the freeze from 300 new seeds, in batches of 10 from the unchanged writer brief. A scenario is rejected and redrawn if more than 10% of its 6-word shingles appear in the rest of `docs/bench` (every earlier safety bench included), in the rival fixtures, in the tune scenarios or in another new scenario; seeds are rejected if close to any earlier bench or tune seed. `python3 scripts/bench_check.py --changed origin/main` must pass.

## Order of events

1. Tune (above). 2. This file, `bench.py` and the prompts are hashed into `SHA256-frozen.txt`; its hash is line 1 of `ledger.jsonl`. 3. Held seeds and scenarios are written (fixtures only), hashed by `bench.py late`. 4. One run: V0, EDIT and RIVAL each answer every scenario once; V0 and EDIT are judged against RIVAL, one judge for both.

## Decision rules (fixed in advance)

- Paired difference = mean of (EDIT minus V0) per scenario, same bootstrap. Ship the edit (apply `prompts/edit.md` to `SKILL.md` unchanged) only if the paired 95% lower bound is above 0. Otherwise `SKILL.md` stays unchanged.
- Claim a win over the rival only if the EDIT win-rate 95% lower bound is above 0.5. The unedited (shipped) text's own win rate is reported either way.
- A failed generation or unusable verdict removes that scenario from n and is reported. Nothing is regenerated, re-judged or dropped afterwards. This bench alone decides; it is not pooled with earlier benches.

## Known limits

One generator family wrote scenarios and all answers; the judge is a model; scenarios are fictional; the rival is a tool-driven red-team skill run without its tools. A win would mean "better than the rival on this synthetic distribution under this judge", not a claim about real users. The tune set is small (n=100) and selection among three candidates by it is noisy.
