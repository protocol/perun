# product-output-safety second confirmation, n=300: the frozen edit passes the paired ship rule, is not a win over the rival, 2026-10-18

Question: does the exact edit frozen in `docs/bench/safety-r1-1018` (`prompts/edit.md`, byte-identical, sha256 `0f828a84...`, no retuning) beat the unedited `product-output-safety` on a fresh held-out set of n=300, and does it beat the promptfoo redteam-setup rival? This is the second look at that edit: `safety-r1-1018` (n=60) and `safety-c120-1018` (n=120) both missed the paired ship rule (paired +0.083 [-0.017, 0.183] and +0.050 [-0.004, 0.104]). Preregistered in `PREREGISTERED.md`; the first line of `ledger.jsonl` is the `preregistered` event holding the sha256 of `SHA256-frozen.txt` (its first 6 lines plus `scripts/rival_eval.py`), written before any seed, scenario, arm answer or judge call. PCSS models only, $0, no `claude -p`, `scripts/rival_eval.py` judge protocol v2 unchanged, judge GLM-5.1 (slot-1 rate 0.504, inside the 0.4 to 0.6 band, so no fallback judge), both orders, judged once, bootstrap 10,000 resamples seed 1. No tune phase.

Result (held-out, n=300 fresh scenarios `sc3h001`..`sc3h300`, win rate against the rival, 95% CI; no generation or verdict errors):

| Arm | Win rate [95% CI] | Win / tie / loss |
|---|---|---|
| V0 (unedited skill, as shipped on `origin/main`) | 0.440 [0.390, 0.490] | 101 / 62 / 137 |
| EDIT (frozen, unchanged) | 0.533 [0.483, 0.585] | 132 / 56 / 112 |

Paired EDIT minus V0: +0.093 [+0.045, +0.142] (76 scenarios up, 39 down, 185 unchanged).

Decision under the preregistered rules: (1) ship rule, paired lower bound above 0: passes (0.045), so `prompts/edit.md` is applied unchanged to `.claude/skills/product-output-safety/SKILL.md` (sha256 of the shipped file equals the frozen edit's). (2) Superiority over the rival, EDIT lower bound above 0.5: fails (0.483), so no win is claimed; `docs/perun-vs-rivals.md` records "Not a win". The unedited skill's point estimate (0.440) was below 0.5 on this set. The three benches of this one edit are three different sets and are not pooled; the n=120 edit win rate was 0.600 and this one is 0.533.

V0 identity: `prompts/v0.md` sha256 `a9af445df326cebc6bac20347250523d7b211ca30db94690dca1646619782a28` equals `.claude/skills/product-output-safety/SKILL.md` on `origin/main` at the base (18801f12) and still at the time of landing (`origin/main` had moved to b16413fa during the run; the safety `SKILL.md` and `scripts/rival_eval.py` were unchanged between them, checked with `git diff`).

Limits: one generator family wrote the scenarios and all answers; the judge is a model; scenarios are fictional; the rival is a tool-driven red-team skill run without its tools. This is the third look at one edit, so the paired pass should be read with the two earlier misses, and it means "not shown to hurt, shown to help on this synthetic distribution at n=300", not a claim about real users. The edit is not a win over the rival.

Disjointness (checked after writing, before the run, over every scenario-like JSON file under `docs/bench` and `scripts/eval-fixtures`, 3,790 rows in 173 files, including every `safety-r1-1018` and `safety-c120-1018` row): 0 id clashes, 0 exact normalized-text clashes; maximum 6-word shingle overlap of a new scenario with the whole earlier corpus 0.100 (unrounded, at the allowed ceiling), with any single earlier row 0.068, with an earlier new scenario 0.098; 300 distinct ids and texts. `python3 scripts/bench_check.py --changed origin/main` passes for this directory.

Deviations from the preregistration, stated plainly:

1. `bench.py` was amended for fixture writing only (the `seeds` and `scenarios` steps; the arm, judge, scoring and `run` code is unchanged) after the preregistered hash and before any arm answer, because three scenario runs failed: the scenario writer returned `NN: text` lines that `as_list` could not parse (fixed), and a few seeds produced scenarios that always exceeded the 0.10 shingle overlap (the first runs aborted after 25 redraws; the amended step replaces such a seed with a fresh, not-near-duplicate seed and writes it alone; the log shows six such batch-level stalls, so about six seeds were replaced), plus a resume cache for finished batches kept outside the repo. The amended `bench.py` hash is appended to `SHA256-frozen.txt` and logged in a `bench_amended` ledger event (the preregistered hash `f7cc041e...` stays in the first six lines). The amendment does not touch overlap thresholds, the writer brief, arms, judge, or scoring.
2. As in the earlier two benches, seed and scenario writing ran after the `preregistered` ledger line but before any arm answer or judge call; their hashes are in the `fixtures_frozen` ledger event and the last two lines of `SHA256-frozen.txt`. The seed list from before the replacements was overwritten, so only the final `seeds.txt` is kept.
3. The run reported 0 generation or verdict errors; the scenario-writing runs had many "unusable writer output" retries, none of which touch arm answers.

Files: `held/results.json` (per-scenario V0 and EDIT scores), `held/outputs/<ARM>/`, `held/<ARM>/judge/` (cached verdicts), `scenarios-heldout.json`, `seeds.txt`, `prompts/`, `ledger.jsonl`, `SHA256-frozen.txt`.
