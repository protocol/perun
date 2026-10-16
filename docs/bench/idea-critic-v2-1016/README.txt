idea-critic v2 (Veles) on a fresh held-out decision set, rubric-free blind judge, both orders, 2026-10-16. Refs #1572. Cited by docs/perun-vs-rivals.md H1e.

Result: SKILL.md change KEPT under the preregistered rule (NEW no larger than OLD and NEW-vs-OLD win rate at least 0.5), as "no measured loss", not "better".
- NEW vs OLD (complete, n=10, 5 order splits): win rate 0.650, 95% CI [0.450, 0.850]. FAIL against the bar (lower bound above 0.5); the data cannot separate a modest win from a tie. SKILL.md 15,519 bytes against 15,950.
- NEW vs RIVAL: INCOMPLETE. The $1.50 cap stopped the run after 29 judge calls: 4 of 10 scenarios (01 to 04) have both orders (0.875, CI [0.625, 1.000] on those 4), scenario 05 one order. Per the preregistration this is not a result and is not a win-rate claim.
- NEW vs PLAIN: NOT RUN (cap). No win rate vs the plain model exists.
- Spend $1.4857 of $1.50, 60 calls, 0 errors (ledger.jsonl): scenario writer $0.039, generation $0.962 (NEW $0.284, OLD $0.290, RIVAL $0.389), judging $0.484 (29 calls, $0.0167 each).

Why incomplete: the preregistered estimate priced a Sonnet judge call at about $0.008 and the whole run at about $1.4; a Sonnet judge call cost $0.0167 and the full three-pair design would have cost about $2.1. The cap was kept; finishing NEW vs RIVAL (11 judge calls) and NEW vs PLAIN (10 generations, 20 judge calls) would cost about $0.65 more and needs a larger cap.

What the NEW-vs-OLD judge reasons say. Where NEW won (scenarios 01, 03, 05, 08): kill criteria with dates, a leading metric, branching decision rules, a caught date error. Where OLD won in the NEW-first order (02, 04, 06, 07, 09, 10): OLD was more specific on a fallback, a ready-to-send draft, a break-even formula or a deadline. Position effect: Response 2 won 15 of the 20 judge calls (6 of 10 with NEW first, 9 of 10 with NEW second), the same pattern as the earlier Opus-judged bench (15 of 20); swapping the order cancels it in the win rate but widens the CI.

Caveats: n=10, one set, a same-vendor Sonnet judge (the earlier bench used Opus; the numbers are not comparable across judges), generation without tools so the skill's references and scripts (including Veche) were unavailable to every arm, model sampling not seeded.

- Whitespace: so the diff check passes, the committed prompts/writer_brief.txt lacks the final blank line after "Seeds:" and outputs/OLD/05.txt line 17 lost its trailing spaces (a markdown line break); the writer and the judge saw the originals, and SHA256-frozen.txt holds the hash of the original writer_brief.txt.
- PREREGISTERED.md, SHA256-frozen.txt: written and hashed before the first paid call. bench.py: driver (`bench.py scen|run|report`; CAP, JOBS, MODEL env).
- prompts/: new.txt (SKILL.md after the edit), old.txt (SKILL.md at origin/main c097d01f), rival.txt (unmodified, see ../idea-critic-rubricfree-1016/), plain.txt, gen_task.txt, judge.txt (unchanged), writer_brief.txt, seeds.txt.
- scenarios.json: 10 generated scenarios, used unedited. outputs/<ARM>/<id>.txt: answers. judge/<Response 1 arm>__<Response 2 arm>/<id>.json: per-order verdict and reason. results-*.json: per-pair scores (the RIVAL file is incomplete, n=4).
