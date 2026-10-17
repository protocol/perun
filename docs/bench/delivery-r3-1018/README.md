# Delivery-plan bench, round 3, 2026-10-18

Question: can a small, root-caused edit to `agentic-delivery/SKILL.md` beat the unedited skill, and either beat Superpowers, on fresh tickets? Preregistered in `PREREGISTERED.md` (hashes in `SHA256-frozen.txt` and `SHA256-tickets.txt`, timestamped `preregistered`, `tickets_frozen` and `selected` lines in `ledger.jsonl` before the corresponding generation). PCSS models only, 0 paid calls, judge prompt v2 from `scripts/rival_eval.py`, three judges, both orders, strict agreement, then majority.

Result (held-out, n=60 tickets `h3-11`..`h3-70`, win rate against Superpowers, 95% bootstrap CI):

| Arm | Win rate [95% CI] | W / L / mixed | DeepSeek-V4-Flash | GLM-5.2 | gpt-oss_120b | Slot-1 rate (ds, glm, j3) |
|---|---|---|---|---|---|---|
| v0 (unedited, origin/main) | 0.517 [0.450, 0.583] | 10 / 8 / 42 | 0.625 | 0.525 | 0.525 | 0.63, 0.84, 0.82 |
| c1 (finalist) | 0.517 [0.458, 0.575] | 8 / 6 / 46 | 0.554 | 0.483 | 0.500 | 0.73, 0.87, 0.87 |

Paired c1 minus v0: +0.000 [-0.075, +0.075] (11 tickets up, 11 down).

Tune (n=10, selection only, `soft` = mean of all judge picks versus Superpowers): v0 0.567, c1 0.633, c2 0.600, c3 0.533; c1 was the finalist.

Decision: rule 1 needs the paired lower bound above 0; it is -0.075, so the edit is not shown to help and does not ship (`SKILL.md` unchanged, bench only). Rule 2: the unedited skill's lower bound is 0.450 and c1's is 0.458, so no superiority claim over Superpowers is made, and across rounds 2 and 3 the unedited skill sits at 0.52 to 0.56, which is a tie within noise. All three judges are position-biased (slot-1 rates 0.63 to 0.87), so 42 to 46 of 60 tickets are 0.5 under strict agreement.

Diagnostic worth keeping: the candidate paragraph did not change the behavior it targeted. Gate numbers (G1, G4, ...) appear in 59 of 60 `v0` held-out plans and 60 of 60 `c1` plans, against 0 of 60 Superpowers plans, even though c1 says "never hat names or G-numbers". A one-paragraph instruction at the top of a 24 KB system prompt does not override the gate table that follows it, so a prose edit cannot close this gap; a change would have to restructure what the plan arm is given (for example a plan-answer view of the skill without the gate table), which is a larger design decision than this round's scope. The judges did not penalize the jargon either: the paired difference is zero.

Files: `bench.py`, `run.sh`, `prompts/` (seeds, v0, c1..c3), `prior/` (the 120 earlier tickets and 96 earlier archetypes used for the disjointness check), `tickets_tune.json`, `tickets_held.json`, `<split>/outputs/<arm>/<ticket>.txt`, `<split>/judge/<judge>/<arm>__sp/<order>/<ticket>.json` (verdict plus the judge's raw analysis), `ledger.jsonl`. Score with `python3 -I bench.py score held v0 sp` (and `c1`), then `paired held v0 c1`; this writes `<split>/results/`. Re-running needs `PCSS_KEY` in the environment.
