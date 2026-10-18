# Preregistration: narrowed contribution skill, round 2 (2026-10-18)

Written and hashed (`SHA256-frozen.txt`, hash in `ledger.jsonl`) before any scenario was drawn and before any generation or judge call. Every model call goes to the PCSS endpoint ($0); no `claude -p`.

Scenarios file: scenarios-heldout60.json

## Question

Round 1 (`contrib-narrow-1017`, kept out of this repository) narrowed `.claude/skills/contribution` to one flow: generalize the lesson, strip third-party identifiers, run the privacy gate, draft the PR, hand a human the upstream PR to open. It could not land as shipped: it had no `ledger.jsonl`, its shipped text differed from the tested text, and it dropped the "Opt-in exception: issues only" paragraph that `scripts/share_learning.py` (`share_learnings: auto`) relies on. This round tests the text that would actually ship (`frozen/contribution.v1.md`): round 1's shipped text, with the issues-only exception restored, the untested "imprint it in AGENTS.md" clause removed, and two safety rules kept (never delete an existing instrument; no unsupervised consolidation loop). Does it beat the current text (v0) against the same rival (daymade github-contributor, text frozen in `frozen/rival.md`, sha256 prefix 98e03b82, byte-identical to round 1's rival)?

## Arms and data

- v0 = `.claude/skills/contribution/SKILL.md` on origin/main at eef753b1 (`frozen/contribution.v0.md`). v1 = `frozen/contribution.v1.md`. Both are final: there is no tuning phase and no later edit, and the shipped SKILL.md is byte-identical to v1 if the keep rule passes.
- Scenarios: `prompts/seeds.txt` holds 60 new seeds, none reused from an earlier bench. They give a fresh held-out set (n = 60, ids r2h01 to r2h60, from seeds 01 to 60), drawn by the blind writer (Qwen3.5-397B-A17B, temperature 0.7, `prompts/brief.txt`, no skill text shown), fictional names only. Round 1's preregistration says its held-out ids were h01 to h60; its driver actually produced h11 to h70. This round's ids are exactly the seed number plus the `r2h` prefix.
- Disjointness: ids are disjoint from every earlier contribution set (tune, heldout, heldout30, round 1's tune10 and heldout60) by the `r2h` prefix. Text disjointness is checked by 6-word shingle overlap against all five sets, after drawing and before any arm output; any scenario sharing more than 0.3 of its shingles with one earlier set is redrawn (writer only, no arm output exists yet) and the redraw is logged. The set is hashed in `ledger.jsonl` right after drawing.
- Generator for all arms: Qwen3.5-397B-A17B, thinking off, temperature 0.3, no tools, the harness's GEN_TASK wrapper. The rival's answer to each scenario is generated once and shared by both arms, so (v1 minus v0) is paired on identical rival text.
- Judge: the v2 protocol in `scripts/rival_eval.py` (random three-letter labels, short analysis before the verdict, both orders). The judge is the first of GLM-5.1, GLM-5.2, gpt-oss_120b whose slot-1 rate, pooled over both arms, lies in 0.4 to 0.6; the same judge scores both arms. No healthy judge means no verdict, which means do not ship. A scenario scores 1 when the arm wins in both orders, 0 when it loses in both, else 0.5. The generator is never a judge. Other judges are reported as sensitivity only.

## Decision rule (stated before any call)

- KEEP (ship SKILL.md and evals) only if, with at least 54 of 60 scenarios scored by a healthy judge, the paired difference (v1 minus v0 win rate, mean of per-scenario score differences) has a 95% bootstrap CI (10,000 resamples over scenarios, percentile, seed 1) whose lower bound is above 0. Otherwise only this bench record is committed.
- Superiority over the rival is claimed only if v1's win-rate CI (same bootstrap) has a lower bound above 0.5.
- One run per arm; no re-runs, no judge swapping, no scenario edits after seeing a result. Records are never overwritten.
