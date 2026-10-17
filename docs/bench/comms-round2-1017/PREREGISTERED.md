# Preregistration: communication-structure round 2 against humanizer, free PCSS models only (2026-10-17)

Written and hashed (SHA256-frozen.txt) before any held-out scenario, generation or judge call. No Claude call is made; every call goes to the PCSS endpoint at no cost (ledger.jsonl records each call's token usage).

## Why

Round 1 (../loss-fix-1017) scored communication-structure 0.175 [0.075, 0.275] against humanizer v3.1.0; its length-release edit changed nothing (the unedited skill scored 0.150). Judge reasons for the 13 clear losses name three things the rival's answer gives the reader that ours dropped:

1. A send-ready email (subject line, greeting, connected prose, sign-off) where the request says "ready to send to <person>". Ours returned a headed memo with bullet fragments and status emoji ("fragmented", "less formal", "emojis").
2. A stated lean before the ask ("clear recommendation", "proposed path forward"). The skill banned any recommendation the author did not give, so ours listed options and asked the reader to choose ("merely presents options without a suggested course of action").
3. Option costs spelled out in full sentences.

Answer length was not the cause: tune-split outputs from the edited skill average the same word count as the rival's (4,513 vs 4,618 words over 20 scenarios).

## The edit under test (arm PERUN = prompts/PERUN.txt = SKILL.md plus references/artifact-templates.md of the candidate edit, same joining as the earlier runs)

- A status update or reply to a named person is written as an email (Subject, greeting, connected prose, ask last, sign-off); PR bodies, tracker comments, executive summaries and docs are not emails.
- A decision message states a lean before the ask: the author's at its stated strength, else one derived from the source's own facts, flagged to the author as derived. No invented facts. This relaxes the old "no recommendation the author did not give" rule only for decision messages, and only for a flagged, derived lean.

## Tune split (already seen, used to choose among four candidate wordings V1 to V4)

The 20 scenarios of round 1 (scenarios_tune.json). Primary judge only (DeepSeek-V4-Flash, both orders). Tune results are in README.txt and are not evidence for the keep rule; the selected wording is V4, the last candidate, and selection on the same judge that is used later biases the held-out result upward, if anything.

## Held-out set (fresh)

40 scenarios, seeds in prompts/held_seeds.txt (different topics from the tune seeds; 16 notes, 12 diff, 12 report), written by GLM-5.1 in four batches of 10 from the same writer brief used in round 1 (writer never sees a skill; it is neither generator nor judge). Used unedited, none dropped. Public, fictional data only.

## Arms and generator

Generator for every arm: Qwen3.5-397B-A17B, temperature 0.7, max_tokens 3000, thinking off, identical task wrapper (prompts/gen_task.txt). PERUN (candidate), RIVAL (humanizer v3.1.0, MIT, as in round 1), BASE (origin/main skill before the edit; descriptive only). The generator is never a judge.

## Judging

Rubric-free, blind, both orders per pair (prompts/judge.txt). Strict agreement: a scenario scores 1 only if both orders pick PERUN, 0 only if both pick RIVAL, and 0.5 for a split or any tie. Primary judge (decides): DeepSeek-V4-Flash. Corroborating judge: GLM-5.2 (slow; partial coverage is allowed and reported, it does not decide). Each judge's slot-1 rate (share of verdicts that picked Response 1, counted with and without ties) is reported for the held-out run.

## Keep rule

KEEP the SKILL.md edit only if, on the 40 held-out scenarios with the primary judge, PERUN vs RIVAL has a bootstrap 95% CI (10,000 resamples over scenarios, seed 1, percentile) whose lower bound is above 0.5, with all 40 scenarios scored. Otherwise REVERT the SKILL.md, templates and eval edits and commit the bench only. One held-out run: no re-runs, no arm edits and no scenario edits after this freeze, no multiple-comparison correction.

## Caveats (state with any outcome)

Non-Claude generator and judges; both skills were written against Claude. A pass here does not show a Claude win and a fail does not show a Claude loss. n=40, one scenario set, sampling not seeded, no lint-and-rewrite loop. DeepSeek-V4-Flash picked Response 1 in about 0.66 of tune verdicts, so it favors slot 1; both-order strict scoring cancels this for the win rate.
