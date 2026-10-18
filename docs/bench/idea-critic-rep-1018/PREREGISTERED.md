# idea-critic replication: shipped SKILL.md against the rival, n=150 fresh held-out (2026-10-18)

Written before any seed, scenario, rival answer, arm answer or judge call of this round. `SHA256-frozen.txt` lists the hashes of this file, the driver, the prompts and the shared bench code; the first line of `ledger.jsonl` is the `preregistered` event whose `sha256` is the SHA-256 of `SHA256-frozen.txt`.

## 1. Question and rule

Round 9 (`../idea-critic-r9-1018`) reported one win for the edited idea-critic skill against the gstack plan-ceo-review rival: 0.570 [0.510, 0.630], 55 W / 61 T / 34 L at n=150, a lower bound only 0.010 above 0.5, and its own README asked for confirmation on a second fresh set. This round is that replication.

- Single arm: `SHIPPED`, the current `.claude/skills/idea-critic/SKILL.md` at origin/main cd9898f2, copied byte for byte from `git show origin/main:.claude/skills/idea-critic/SKILL.md` into `prompts/perun_idea-critic_SHIPPED.txt` (sha256 `8c71a0d32c52731a24db73a25d66162ef099f67bc196a6d00b8b86ac27f93817`, 15,931 bytes; equal to round 9's `prompts/perun_idea-critic_c9c.txt`). No skill edit, no second arm, no tune stage, no v0.
- Rule (fixed now): the round-9 win is replicated iff the SHIPPED-versus-rival score has a 95% bootstrap interval whose lower bound is above 0.5. Otherwise the win is not replicated and is reported as such, whatever the point estimate.
- Judged once. No rerun of a complete record, no second sample, no change of rule or data after unblinding. Only an unparsed judge reply (an incomplete record, never written) may be rerun, as in round 9, and is disclosed.

## 2. Set

150 fresh fictional scenarios `rp-001`..`rp-150`, written by gpt-oss_120b from 150 freshly invented company seeds (`bench9.py seeds`, `scen`), voice and phrasing of the ask drawn per scenario from a fixed RNG (`rep-<i>`), as in round 9. A scenario is kept only if its 6-word shingles overlap at most 0.10 (unrounded, share of its own shingles) with all text in every docs/bench directory present on current origin/main (this directory excluded), including every `outputs/` file, the eval fixtures and the idea-critic evals, and with the rest of the batch; ids, company names and exact texts are also disjoint (`bench9.py check`). `python3 scripts/bench_check.py --changed origin/main` must pass. The corpus includes round 9's scenarios, seeds and model outputs, so this set is disjoint from round 9's held-out set.

## 3. Method (mirrors round 9)

- Driver `bench9.py`: derived from `../idea-critic-r9-1018/bench9.py` with the tune stage, the v0 arm and the paired test removed; seeds, scenario writer, voice/ask lists, overlap check, generation, judging and bootstrap code are unchanged apart from names (ids `rp-`, RNG label `rep-`, file names).
- Rival: the same gstack plan-ceo-review text as rounds 5 to 9 (`../exec-1017/prompts/rival_idea-critic.txt`); answers generated once and hashed in `RIVAL-sha256-held.json` before the arm is generated or judged.
- Arm and rival generator: Qwen3.5-397B-A17B, skill as system prompt, temperature 0.7, under 500 words, task text `../exec-1017/prompts/gen_task.txt`.
- Judges: GLM-5.1, GLM-5.2, gpt-oss_120b; judge prompt v2 byte-identical (`prompts/judge_v2.txt`, hash in `SHA256-frozen.txt`); both answer orders per judge, strict agreement else tie, then majority of three, ties 0.5. Bootstrap 10,000 resamples, seed 1, percentile, over scenarios (`../exec-1017/bench.py`).
- PCSS only (free tier), no `claude -p`, no key printed.

## 4. Power and caveats stated in advance

At n=150 the half-width of a win-rate interval is about 0.06; a true rate of 0.57 clears the 0.5 bound only about half the time, so a miss would not show the win is absent, only that it is not confirmed. Open models on one cluster; system-prompt-only arm; one run per arm; the writer gpt-oss_120b also judges; scenarios are model-written; the skill text was written after reading earlier judge reasons and was selected on round-5/6 tune data, so round 9's estimate carries winner's-curse risk that this round does not.
