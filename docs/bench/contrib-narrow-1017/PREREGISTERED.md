# Preregistration: narrowing the contribution skill to the privacy-safe upstream-PR flow (2026-10-17)

Written and hashed (SHA256-frozen.txt) before any scenario was drawn and before any generation or judge call. Every model call goes to the PCSS endpoint ($0); no `claude -p`.

## Question

The owner decided to narrow `.claude/skills/contribution` to one flow: generalize the lesson, strip third-party identifiers, run the privacy gate, hand a human the upstream PR to open. Does the narrowed text (edit) beat the current text (v0) against the same rival (daymade github-contributor, text fetched from the URL in `scripts/eval-fixtures/rival/contribution/rival.json`)?

Prior (docs/bench/contrib-safety-1017): v0 scored 0.317 to 0.333 against this rival on 30 held-out scenarios; no edit then helped.

## Arms and data

- v0 = the SKILL.md on origin/main at 3d9a30ff (frozen copy `frozen/contribution.v0.md`). Edit = the narrowed SKILL.md (hashed in an addendum after tuning, before held-out generation).
- Scenarios: `prompts/seeds.txt` holds 70 new seeds, none reused from earlier benches. Seeds 01-10 give the tune set (n = 10, `tune10.json`, ids t01-t10); seeds 11-70 give a fresh held-out set (n = 60, `heldout60.json`, ids h01-h60), drawn by the blind writer (Qwen3.5-397B-A17B, temperature 0.7, `prompts/brief.txt`, no skill text shown), fictional names only. The held-out file is hashed right after drawing and before any arm output. Disjointness from every earlier set (tune.json, heldout.json, heldout30.json, tune10.json) is checked by 6-word shingle overlap (none above 0.3 of the smaller set).
- Generator for all arms: Qwen3.5-397B-A17B, thinking off, temperature 0.3, no tools, the harness's GEN_TASK wrapper. The rival's answer to each scenario is generated once and shared by both arms, so (edit - v0) is paired on identical rival text.
- Judge: the v2 protocol in `scripts/rival_eval.py` (random three-letter labels, short analysis before the verdict, both orders). The judge is the first of GLM-5.1, GLM-5.2, gpt-oss_120b whose slot-1 rate, pooled over both arms, lies in 0.4 to 0.6; the same judge scores both arms. No healthy judge means no verdict, which means REVERT. A scenario scores 1 when the arm wins in both orders, 0 when it loses in both, else 0.5. The generator is never a judge. Other judges are reported as sensitivity only.
- Tune: n = 10, run as needed (at most three edit iterations), never a verdict. The edit is frozen and hashed before the held-out set is drawn.

## Decision rule (stated before any call)

- SHIP the edit only if, on the held-out set with at least 54 of 60 scenarios scored by a healthy judge, the paired difference (edit minus v0 win rate, mean of per-scenario score differences) has a 95% bootstrap CI (10,000 resamples over scenarios, percentile, seed 1) whose lower bound is above 0. Otherwise REVERT: the SKILL.md, references, evals and changelog edit are dropped and only the bench ships.
- Superiority over the rival is claimed only if the edit's win-rate CI (same bootstrap) has a lower bound above 0.5.
- One held-out run per arm; no re-runs, no judge swapping, no scenario edits after seeing a result. Records are never overwritten.
