# Preregistration: product-output-safety second forward-only confirmation, n=300 (2026-10-18)

This is the second look at one edit. The `SHA256-frozen.txt` first-line hash is written to `ledger.jsonl` (event `preregistered`) before any seed, scenario or answer is generated. Base: `origin/main` at 18801f12 (`.claude/skills/product-output-safety/SKILL.md`, sha256 `a9af445df326cebc6bac20347250523d7b211ca30db94690dca1646619782a28`).

## Question

`docs/bench/safety-r1-1018` froze one edit to `.claude/skills/product-output-safety/SKILL.md` ("Answer inside the stated constraint", paid for by de-duplication)
and measured paired (edit minus unedited) +0.083 [-0.017, +0.183] on n=60. `docs/bench/safety-c120-1018` replicated it forward-only on n=120 fresh scenarios:
edit 0.600 [0.521, 0.679] against the promptfoo redteam-setup rival, unedited skill 0.550 [0.467, 0.633], paired +0.050 [-0.004, +0.104]. The keep rule failed by 0.004
and the edit was not shipped. This bench is the second look at the same edit on a fresh, larger set: n=300, so the paired interval is about 0.6 times as wide as at n=120.

## What is frozen

- The edit: `prompts/edit.md`, byte-identical to `docs/bench/safety-r1-1018/prompts/edit.md` and `docs/bench/safety-c120-1018/prompts/edit.md` (sha256 `0f828a844dbe8c4e648a1a89c03bf06480da557f6e39942f78ef9205fd8e03f6`); `bench.py run` asserts the hash. No retuning, no variants, no tune phase.
- V0: `prompts/v0.md`, the unedited skill as shipped on `origin/main`, identical to `.claude/skills/product-output-safety/SKILL.md` at the base (asserted by `bench.py run`).
- RIVAL: `prompts/rival.txt`, identical to the rival text of `safety-c120-1018`. Harness: `scripts/rival_eval.py` unchanged (judge protocol v2: reason-first JSON, neutral random labels, both
  orders, a scenario scores 1 or 0 only when both orders agree, else 0.5; judge chain GLM-5.1, GLM-5.2, gpt-oss_120b, the first whose slot-1 rate is inside 0.4 to 0.6). Generator
  Qwen3.5-397B-A17B (non-thinking, temperature 0.3), never a judge. Bootstrap 10,000 resamples, seed 1, percentile, over scenarios. PCSS only, spend $0, no `claude -p`.
- `bench.py` is the `safety-c120-1018` driver with three changes: N_SC=300, scenario ids `sc3h001`..`sc3h300`, and a `late` step that appends the seed and scenario hashes to
  `SHA256-frozen.txt` and logs them in a `fixtures_frozen` ledger event (see Order of events). The arm, judge and scoring code is unchanged.

## Scenarios

300 fresh scenarios, written from the skill's own writer brief (`prompts/writer_brief.txt`, unchanged) in batches of 10 from 300 new seeds. A scenario is rejected and redrawn if more than 10%
of its 6-word shingles (unrounded fraction) appear in the rest of `docs/bench` (every `safety-r1-1018` and `safety-c120-1018` scenario included) or in another new scenario; seeds are rejected if close to
any earlier bench seed. After writing, disjointness from every scenario file in the repo by id, exact normalized text and 6-word shingles (at most 0.10, unrounded) is checked and reported in `README.md`,
and `python3 scripts/bench_check.py --changed origin/main` must pass.

## Order of events

1. This file, `bench.py` and the prompts are hashed into `SHA256-frozen.txt`; its sha256 is the first line of `ledger.jsonl` (`preregistered`), before any generation.
2. Seeds and scenarios are written (fixtures only; no arm answer and no judge call exists). `bench.py late` appends their hashes to `SHA256-frozen.txt` and logs a `fixtures_frozen` event.
3. One run: every arm answers every scenario once; EDIT and V0 are each judged against RIVAL (both orders, one judge for both comparisons). The judge is run once.

## Analysis and decision rule

- Win rate = mean per-scenario score against the rival, bootstrap CI above. Paired difference = mean of (EDIT minus V0) per scenario, same bootstrap.
- Ship the edit only if the paired (EDIT minus V0) 95% CI lower bound is above 0. If it ships, `prompts/edit.md` is applied to `SKILL.md` unchanged. Claim superiority over the rival only if the
  EDIT win-rate CI lower bound is above 0.5. Otherwise `SKILL.md` stays unchanged and the bench is published as is.
- A failed generation or unusable verdict removes that scenario from n and is reported. Nothing is regenerated, re-judged or dropped afterwards. The result of this bench, not a pool with earlier ones, decides.

## Known limits

One generator family wrote scenarios and all answers; judges are other models; scenarios are fictional; the rival is a tool-driven red-team skill run without its tools. A win means "better than the
unedited skill on this synthetic distribution under this judge", not a claim about real users. This is the third bench of one edit, so a pass here is read together with the two earlier results.
