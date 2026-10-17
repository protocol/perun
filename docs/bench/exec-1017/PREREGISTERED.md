# Preregistration: exec-skill superiority bench (2026-10-17)

Written and hashed (`SHA256-frozen.txt`: prompts, scenarios, driver) before the first generation or judge call. Paid Anthropic calls are not used (quota exhausted); every model call runs on the PCSS endpoint (`https://llm.hpc.psnc.pl/v1`).

## Question

Do the Perun skills `agentic-ceo`, `idea-critic`, `business-ops`, `growth-analytics` and `positioning` beat their strongest named rival on fresh executive decision cases, and, where they do not, does a root-cause edit to the skill text fix that on held-out scenarios?

## Arms (system prompt only, no tools, same generator, same task wrapper)

- PERUN_v0: the skill's `SKILL.md` at base commit 3d69f4cd (frontmatter included), `prompts/perun_<skill>_v0.txt`. PERUN_v1: the edited text, written only after reading tune-set judge reasons (below). References and scripts are unavailable to every arm (no tools), so a fix must live in `SKILL.md` itself.
- RIVAL per skill (unmodified text; every arm of a skill sees the same rival output per scenario, generated once):

| Skill | Rival | Source |
|---|---|---|
| idea-critic | garrytan/gstack `plan-ceo-review/SKILL.md` | commit 47d639ab, MIT; reused from `docs/bench/idea-critic-rubricfree-1016/prompts/rival.txt` (symlink) |
| agentic-ceo | same gstack `plan-ceo-review` | named in `docs/perun-vs-rivals.md` as the strongest CEO-altitude rival; agentic-ceo has no rival measured elsewhere (the Superpowers routing run showed no skill invocation, so it is not a content rival) |
| growth-analytics | coreyhaines31/marketingskills `analytics` + `ab-testing` | commit 365b4121, MIT; reused from `docs/bench/growth-analytics-rubricfree-1016/prompts/rival.txt` (symlink) |
| business-ops | coreyhaines31/marketingskills `skills/pricing/SKILL.md` (SKILL.md only, no references) | commit 365b4121, MIT; fetched 2026-10-17 into `prompts/rival_business-ops.txt`; license text in `docs/bench/growth-analytics-rubricfree-1016/LICENSE.rival.txt` (same repository and commit) |
| positioning | deanpeters/Product-Manager-Skills `positioning-statement` + `positioning-workshop` SKILL.md files | tarball of `main` fetched 2026-10-17; CC BY-NC-SA 4.0, so its text is NOT committed (`prompts/rival_positioning.txt` is local only); SHA-256 of the two files: `44d46a65fa95871cf978f6863650c95be92f135f635f0197866344087b374909` (positioning-statement), `81554cbf6a1a932a2e8e8ddf36995758e822f805bcb58c7078b735fc5d51b58b` (positioning-workshop) |

- Generator: `Qwen3.5-397B-A17B`, thinking disabled (`enable_thinking: false`), temperature 0.7, max 3000 tokens, arm file as system prompt, wrapper `prompts/gen_task.txt` (under 500 words, same for all arms).

## Scenarios

30 per skill, 150 in total, fictional companies and people only. Written one per call by `gpt-oss_120b` (not a judge, not the generator) from `prompts/writer_common.txt`, the per-skill brief `prompts/writer_<skill>.txt` and one setting from `prompts/seeds.txt` (rotated by 6 per skill so settings differ across skills). The writer never sees any skill or rival text. Used unedited; none dropped. Each asks for one recommendation, the main ways it could fail, and the stop condition for a named fictional executive, and contains a catchable flaw in the numbers or assumptions. First 10 scenarios per skill = tune; last 20 = held-out. The split is fixed by id before any generation.

## Judge

`DeepSeek-V4-Flash`, rubric-free (`prompts/judge.txt`, no criteria), blind. Per scenario two calls with randomized order (seeded by skill, arm and scenario id; second call swaps). Both agree on one arm: that arm wins. A split, a tie or a parse failure goes to one `GLM-5.2` tiebreak call (independently randomized order); a GLM tie or failure counts 0.5. Score per scenario: 1 Perun, 0.5 tie, 0 rival. Win rate = mean over scenarios; bootstrap 10,000 resamples, seed 1, percentile, over scenarios.

## Procedure and keep rule

1. Baseline: PERUN_v0 vs RIVAL on tune and on held-out. The held-out judge reasons are NOT read until the keep decision; fixes are driven by tune-set reasons only.
2. For each skill, read the tune-set reasons that favour the rival, find the root cause in the skill text (not a scenario-specific patch), and write PERUN_v1 once per skill. Re-test PERUN_v1 vs RIVAL on held-out once. No second edit round, no re-runs after seeing results.
3. Keep PERUN_v1 only if held-out v1 win rate has a 95% CI lower bound above 0.5 with n=20 AND the v1 win rate is not below v0's. Otherwise revert the `SKILL.md` edit (artifacts stay). A skill whose v0 already passes the bar is still edited only if a tune-set root cause is found; it is then kept only under the same rule.
4. Report plainly: PASS means held-out CI lower bound > 0.5; FAIL means not shown superior.

## Caveats declared in advance

Generator, scenario writer and both judges are open models on one cluster, not the models users run; this is a different-vendor judge from the generator (Qwen) but the judges are small relative to Opus-class judges. Sampling is not seeded, so a re-run will differ. n=20 binary-ish outcomes: a win rate of 0.70 has a CI lower bound near 0.5, so only roughly 15 or more wins of 20 pass. Rival arms run without their tools and references, as do Perun arms. Scenario flaws are written by a model and are not verified by hand. A tune-set fix may overfit the writer's style; held-out is the check.
