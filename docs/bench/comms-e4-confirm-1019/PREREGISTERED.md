# Preregistration: confirmation of edit E4 for communication-structure (2026-10-19)

Written and hashed (SHA256-frozen.txt, ledger event `preregistered`) before any scenario is written and before any arm call. Free PCSS models only; no `claude -p`; all data synthetic and fictional. This is a powered confirmation of one frozen edit, with the r2 harness and the r2-validated judge reused byte-for-byte (fabjudge.py, run_held.py, report.py and every file under prompts/ are copies of `../comms-outcome-r2-1019`; only gen.py differs).

## Question
`../comms-outcome-r2-1019` tested edit E4 (name the options in the ask; a `Key figure:` line) against the shipped skill V0 (v1.2.4) on 80 fresh scenarios. E4 beat V0 on reader accuracy (+0.046, 95% CI [+0.026, +0.066]) and the humanizer (0.712 against 0.662), and the real-fabrication rate difference was 0.000 [-0.033, +0.033]. It was reverted only because n=80 could not show an upper bound of at most +0.02. This bench re-tests E4 once, on enough fresh scenarios for that bound to be reachable.

## Sample size (computed from r2's per_scenario_held.json, not assumed)
- Observed real-fab rate: V0 0.0708 and E4 0.0708 (17 of 240 messages each). The per-scenario paired difference (E4 minus V0) has mean 0.000 and standard deviation 0.159 over 80 scenarios, so the 95% half-width is 1.96 x 0.159 / sqrt(n) (0.035 at n=80 by the normal approximation; r2's bootstrap gave 0.033).
- Upper bound at most +0.02 at a zero point difference needs 1.96 x 0.159 / sqrt(n) <= 0.02, so n >= 243. At n=243 a true tie passes about half the time; 80% power at a true tie needs (1.96 + 0.84) x 0.159 / 0.02 squared, n of about 497.
- Cap: r2 ran 80 scenarios x 3 arms (generate, 2 readers, 2 grades, judge) in 28 minutes of arm calls plus 4 minutes of scenario writing at 6 parallel jobs, free PCSS models, so 500 scenarios is a few hours today. Target n = 500 (at the 80% point). Floor: n >= 243; fewer valid scenarios than 243 means the bench stops and reports no verdict.

## Scenarios
Written after this file is frozen, by gen.py, with r2's writer brief and r1's validity checks. r2's design (pairs of kind and domain disjoint from earlier benches) cannot reach this n: only 25 of the 175 (kind, domain) pairs are unused by r1 and r2. So the 25 unused pairs come first, then every pair again with a new variant seed (up to 6 passes), and a scenario is kept only when at most 20% of its 10-word shingles occur in any r1 or r2 scenario or in a scenario already kept. Scenarios are therefore fresh in content, not in (kind, domain) pair; this is a stated weakening of r2's pair-level disjointness, accepted because the arms see only the notes. The first 500 valid scenarios in the fixed order are kept. scenarios_held.json is hashed into SHA256-frozen.txt with a ledger event before any arm generation. `bench_check.py --changed origin/main` must pass.

## Arms (each arm's whole text is the generator's system prompt)
- V0: the shipped skill v1.2.4 (prompts/V0.txt, byte-identical to `.claude/skills/communication-structure/SKILL.md` at freeze and to r2's).
- E4: the frozen r2 text (prompts/E4.txt, byte-identical to r2's); no tuning.
- RIVAL: humanizer v3.1.0 (`../comms-r5-1017/prompts/RIVAL.txt`, as r1 and r2). It enters no keep rule.

## Measurement
Unchanged from r2: generator Qwen3.5-397B-A17B (temperature 0.7, 3 samples per arm and scenario), readers GLM-5.1 and gpt-oss_120b, grader GLM-5.2, five questions, accuracy per scenario averaged over samples x readers x questions; real fabrication judged by GLM-5.2 (prompts/fab_judge.txt, validated in r2 on 91 hand-labelled figures: test agreement 39 of 40, recall 7 of 8, precision 7 of 7); paired percentile bootstrap, 10,000 resamples, seed 1. Words and the dropped-fact rate are reported as before.

The rule below is copied from `../comms-outcome-r2-1019/PREREGISTERED.md` without a changed character. "r2 held-out set" and "about 80 scenarios" are r2's words; they read here as this confirmation set and as n of about 500. The margin and thresholds do not change, and neither does the clause that REVERT ships no SKILL.md edit.

## Keep rule for E4 (all must hold on the r2 held-out set; otherwise REVERT and no SKILL.md edit ships)
1. Accuracy, E4 minus V0, paired 95% CI lower bound above 0.
2. Real-fab rate, E4 minus V0 (per-scenario paired): the 95% CI upper bound is at most +0.02. The margin is 0.02, about one message in fifty. It is strict by design: with about 80 scenarios the interval will usually be wider than 0.02, so an E4 with a truly equal rate often fails; a pass needs E4 to be measurably no worse. This is the owner-specified non-inferiority test, kept despite its cost in power.
3. Mean words, E4 at most 1.25 x V0 (r1's budget).
4. Judge completeness: no flagged figure left unlabelled in V0 or E4, and no missing grade.

The dropped-fact rate, per-reader differences and the regex invented rate are reported, not gating. Kill criterion: any of 1 to 4 failing is REVERT; there is no re-run on the same scenarios and no second tuning pass.


## Procedure
1. Freeze this file, the copied harness and prompts, and gen.py (SHA256-frozen.txt and the ledger `preregistered` line). 2. `python3 gen.py` writes the scenarios; hash them into SHA256-frozen.txt with a `freeze_add` ledger event. 3. `run_held.py V0 E4 RIVAL` (cached, never overwritten; re-running only fills records lost to transport errors, before the first report). 4. `report.py held V0 E4 RIVAL`; the last line is the verdict. 5. Descriptive extras after the verdict inputs are fixed, which gate nothing: E4 minus RIVAL accuracy and real-fab rate with paired CIs (vs_rival.py).

## After the verdict
- KEEP: the exact two E4 bullets (the lines E4.txt adds to V0.txt) are inserted into `.claude/skills/communication-structure/SKILL.md` at the same place, the skill's evals are touched, and `docs/perun-vs-rivals.md` records the measured result. It may call E4 an outcome win over the humanizer only if the E4 minus RIVAL accuracy CI lower bound is above 0; otherwise it states the measured difference.
- REVERT: no skill edit; the result is reported as measured. There is no re-run on these scenarios and no second tuning pass.

## Known limits
As r2: one generator, two reader families, model-written scenarios, one judge model validated on 91 tokens labelled by one model rater (8 fabricated test cases), a skill written for Claude run on another model, a guard that sees only numbers and weekdays. Added here: scenarios repeat (kind, domain) pairs of r1 and r2 with new content; the 500-scenario bootstrap treats scenarios as independent although several share a pair. A result is evidence for this reader, judge and scenario set, not a general claim.
