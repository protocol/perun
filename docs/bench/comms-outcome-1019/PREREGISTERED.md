# Preregistration: communication-structure outcome bench (2026-10-19)

Written and hashed (SHA256-frozen.txt, ledger event `preregistered`) before any scenario, seed or arm generation. Free PCSS models only; no `claude -p`; all data synthetic and fictional.

## Question
Earlier rounds (../comms-r4-1017, ../comms-r5-1017) measured communication-structure against humanizer by blind preference, a proxy: the judge picks the message it would rather receive. This bench measures an outcome instead: can a separate reader recover the decision, the action, its owner, its deadline and the key number from the message alone, and did the message keep the source facts without inventing any.

## Arms (each arm's whole text is the generator's system prompt, as in earlier rounds)
- V0: the shipped skill, `.claude/skills/communication-structure/SKILL.md` v1.2.4 at base commit 9b6fed2f (prompts/V0.txt).
- RIVAL: humanizer v3.1.0, MIT, the text vendored by `../comms-r5-1017/prompts/RIVAL.txt` (frozen there; this bench lists it in SHA256-frozen.txt and does not copy it).
- NONE: no skill (prompts/NONE.txt, "You are a helpful assistant.").
- E1..E5: at most five edited skill texts, written only after the tune result and only if the trigger below fires (prompts/E*.txt).

## Scenarios
Each scenario is a fictional set of raw notes (130 to 220 words) that asks an assistant to draft a message to a named reader, plus gold answers for five required items: decision, action, owner, deadline, key number. A scenario is kept only if every literal fact it lists (including the number, owner and deadline literals) occurs verbatim in its notes after normalisation, and the notes hold at least four numeric tokens or weekdays; otherwise it is regenerated (up to four attempts, then dropped). Kinds: decision request, status update, PR body, executive summary, incident handoff (balanced). Writer: DeepSeek-V4-Flash from prompts/writer_brief.txt; (kind, domain) pairs come from the fixed lists in bench.py, disjoint between tune and held. Tune n=40; held-out n=30, written after the selection is frozen. bench_check.py rule d (10-word shingle overlap with every other bench and with tune) applies.

## Measurement
- Generator: Qwen3.5-397B-A17B, `rival_eval.GEN_TASK` plus the notes, temperature 0.7, 3 samples per arm and scenario (the same task text for every arm).
- Readers (two models, different from the generator): GLM-5.1 and gpt-oss_120b. Each sees only the generated message and the five fixed questions in prompts/reader.txt (it is told who the recipient is) and answers "not stated" when the message does not say.
- Grader: GLM-5.2, prompts/grader.txt, blind to the arm, one call per (message, reader) marking each of the five answers true or false against gold.
- Primary metric, per scenario: accuracy = mean over 3 samples x 2 readers x 5 questions of the true marks. Per-reader and per-question accuracy are descriptive.
- Guardrails, deterministic (bench.py): dropped = share of messages missing at least one listed literal fact; invented = share of messages holding a numeric token or weekday absent from the notes (a derived figure such as a difference counts); words = mean length. A missing message counts as dropped and scores 0; missing grades score 0 and are counted in the report.
- Uncertainty: paired percentile bootstrap, 10,000 resamples, seed 1, over per-scenario differences.

## Procedure and rules
1. Freeze this file, bench.py, prompts/ and the RIVAL path (SHA256-frozen.txt, ledger `preregistered`) before any call.
2. Write the 40 tune scenarios; run V0, NONE, RIVAL on tune. Tune never yields a verdict.
3. Trigger: if V0's tune accuracy is below RIVAL's or below NONE's, try at most five edits (E1..E5) of the skill, each run on tune only. If the trigger does not fire, no edit is tried.
4. Selection: the edit with the highest tune paired difference over V0 whose tune dropped and invented rates are not above V0's and whose difference is above 0. None qualifies means no edit. The selected prompt, and the held-out scenarios once written, are hashed into SHA256-frozen.txt with a ledger event before any held-out generation.
5. Held-out: write the 30 scenarios, then run V0, NONE, RIVAL and the selected edit once. A record is never overwritten. Re-running only fills records lost to transport errors, before the first held-out report.
6. Outcome verdict for the shipped skill (V0 against RIVAL, and against NONE, held-out accuracy): win if the paired CI lower bound is above 0, loss if the upper bound is below 0, otherwise tie not separable from either.
7. KEEP the edit (and only then edit SKILL.md) only if all hold on held-out: the paired difference (edit minus V0) has a CI lower bound above 0; each reader's point difference is at least 0; the edit's dropped and invented rates are not above V0's; mean words is at most 1.25 times V0's. Otherwise REVERT: no SKILL.md edit ships, only this bench.

## Known limits
One generator and two reader families; scenarios written by a model; the grader shares a vendor with one reader; the invented check is regex-level and counts a correctly derived figure as invented in every arm alike; the skill is written for Claude and is run here on another model; the shared scripts/rival_eval.py (chat client, bootstrap, GEN_TASK) is not snapshotted here. A held-out result is evidence for this reader and judge set, not a general claim.
