# Judge slot-1 skew calibration, 2026-10-18

BLUF: The skew is not a general position bias of the judges. On identical pairs GLM-5.1, GLM-5.2 and gpt-oss_120b say "tie" (359 of 360 verdicts across the three judges), and on pairs with a real gap they pick the better answer with slot-1 rates of 0.45 to 0.52 (correct picks 0.97 to 1.00). The 0.62 to 0.67 seen in growth round 5 comes from close contests: in the spent round-5 verdicts 41 to 42 percent of pairs are decided by slot alone (both orders pick the same slot), and in those pairs the judge picks slot 1 in 80, 88 and 93 percent of cases. So the judges are healthy discriminators that break a close call toward the first answer and almost never say "tie" on real round-5 pairs (0 to 1 of 300 verdicts per judge). This is a property of the judge on close pairs, not of the judge on clear pairs, so swapping among these three judges will not fix the gate. Because both orders are always scored and a split is 0.5, the skew shrinks scores toward 0.5 (less power) but is not shown to push them in one direction. No skill, rival row or past verdict is changed. Cost: $0 (PCSS only, 1080 judge calls). Proposed protocol fix: see "Proposal" (not applied).

## What was run

- Judge: the frozen judge of `docs/bench/growth-r5-1018` unchanged, imported from `scripts/rival_eval.py` (sha256 in `SHA256-frozen.txt` equals the `scripts/rival_eval.py` line of `docs/bench/growth-r5-1018/SHA256-frozen.txt`): `JUDGE_SYSTEM`, neutral three-letter labels, reason first, `max_tokens` 3000, temperature 0, GLM-5.1, GLM-5.2, gpt-oss_120b, both orders.
- Items: 60 spent held-out outputs, calibration only, never a decision. 30 drawn (seed 1018) from the round-4 held-out set and 30 from round 5, with the arm (v0, v1, rival) rotating by item. `calib.py items()` is the exact list.
- Controls (per judge, per item, both orders, so 120 verdicts per cell):
  - a: the answer against an identical copy. Any decisive verdict is pure position.
  - b: the answer against a copy cut to its first 30 percent of characters (cut fraction 0.299 to 0.300). The full answer is the correct pick.
  - c: the answer against itself with its last section dropped (last markdown heading if it starts in the back half, else the last blank-line block). Mean fraction kept 0.851, range 0.589 to 0.953. The full answer is the correct pick.
- One change from the frozen call: the label seed is salted with the control and the order. Without it the two orders of an identical pair are the same prompt and the control would be one call counted twice.

## Results

Slot-1 = share of decisive (non-tie) verdicts that picked slot 1; 0.5 is no position effect. Correct pick = share of decisive verdicts that picked the full answer. Last column: share picking slot 1 when the full answer was in slot 1 / in slot 2 (a judge with no position effect shows 1.0 / 0.0 on a clear gap). Raw table: `raw/report.md`; every verdict: `raw/verdicts.jsonl`.

| Judge | Control | Slot-1 [95% Wilson CI] | Ties of 120 | Correct pick | Slot 1 when full is in slot 1 / slot 2 |
|---|---|---|---|---|---|
| GLM-5.1 | a identical | no decisive verdict | 120 | n/a | n/a |
| GLM-5.1 | b first 30% | 60/120 = 0.500 [0.412, 0.588] | 0 | 120/120 = 1.000 | 60/60 / 0/60 |
| GLM-5.1 | c last section dropped | 40/89 = 0.449 [0.350, 0.553] | 31 | 86/89 = 0.966 | 38/39 / 2/50 |
| GLM-5.2 | a identical | 1/1 (one decisive verdict) | 119 | n/a | n/a |
| GLM-5.2 | b first 30% | 60/120 = 0.500 [0.412, 0.588] | 0 | 120/120 = 1.000 | 60/60 / 0/60 |
| GLM-5.2 | c last section dropped | 42/92 = 0.457 [0.359, 0.558] | 28 | 92/92 = 1.000 | 42/42 / 0/50 |
| gpt-oss_120b | a identical | no decisive verdict | 120 | n/a | n/a |
| gpt-oss_120b | b first 30% | 60/120 = 0.500 [0.412, 0.588] | 0 | 120/120 = 1.000 | 60/60 / 0/60 |
| gpt-oss_120b | c last section dropped | 60/116 = 0.517 [0.427, 0.606] | 4 | 116/116 = 1.000 | 60/60 / 0/56 |

Control c slot-1 is 0.45 to 0.52, inside the 0.4 to 0.6 gate. The b and c slot-1 rates are balanced by construction (the full answer is in slot 1 in exactly half the orders), so a rate near 0.5 means any position pull is smaller than the content signal; for b and c this is "the gap beats the bias", not "there is no bias". Control a is the pure-position test: it shows none, because the judges decline to choose.

Re-reading the spent round-5 verdicts (`raw/real-r5.md`, from `docs/bench/growth-r5-1018/results/judge-verdicts.json`; 300 skill-versus-rival pairs per judge, each with both orders). Content-consistent = the two orders picked the same answer; both slot 1 / both slot 2 = the two orders picked the same slot, so slot decided it.

| Judge | Content-consistent | Both slot 1 | Both slot 2 | Slot-1 overall | Slot 1 among slot-decided pairs |
|---|---|---|---|---|---|
| GLM-5.1 | 178 | 98 | 24 | 0.623 | 98/122 = 0.80 |
| GLM-5.2 | 174 | 110 | 15 | 0.659 | 110/125 = 0.88 |
| gpt-oss_120b | 178 | 113 | 9 | 0.673 | 113/122 = 0.93 |

(GLM-5.2 has 299 pairs with both orders decisive, 1 with a tie.) Real-pair ties were 0, 1 and 0 of 300 pairs, against 31, 28 and 4 of 120 verdicts on control c.

## Diagnosis

1. Not a global judge bias. Control a gives no decisive verdicts to attribute to position (1 of 360), and controls b and c give 0.45 to 0.52 with correct picks of 0.97 to 1.00, including when the gap is one dropped section (about 15 percent of the text).
2. Not a case of the answers being near-identical either: round-5 pairs are different answers (skill versus rival), yet 41 to 42 percent are not separated by either order. On those, the judges take slot 1 80 to 93 percent of the time and do not say "tie" (0 to 1 of 300), while they do say "tie" on control c (23 to 26 percent for GLM, 3 percent for gpt-oss_120b).
3. So it is the interaction: a close contest plus a judge that always commits. The skew measures how many of the contests are close (a property of the arms and scenario set, here skill against a strong rival) times how reliably the judge falls back on slot 1. gpt-oss_120b falls back most (0.93) and GLM-5.1 least (0.80); that ordering matches the slot-1 ordering (0.673, 0.623).
4. Consequence for the gate: a judge that would pass it must tie or split evenly on close pairs, but all three non-tie on close pairs. A pooled slot-1 rate inside 0.4 to 0.6 is then a statement about the contest set as much as about the judge (the round-4 rate was 0.600 on the same GLM-5.1, round 5 was 0.623, rounds on idea-critic in `docs/bench/rival-eval-baseline-1017/README.md` were 0.65 to 0.75).
5. Effect on scores: `scenario_score` gives 1 or 0 only when both orders agree and 0.5 on a split, so a slot-decided pair scores 0.5 whichever way it falls. The skew therefore costs power (about 40 percent of scenarios per judge land on 0.5 by position alone, on top of true ties) and is not shown to move a win rate in one direction. That is an argument, not a measurement here; I did not simulate a judge with a position bonus.

## Proposal (not applied; for the owner to preregister)

Do not apply retroactively; no past verdict changes.

1. Replace "pooled slot-1 rate in 0.4 to 0.6" as the exclusion gate with two gates that test what matters:
   - Capability gate, run once per judge on spent outputs before any held-out seed: controls b and c of this directory (n = 60, both orders). Pass if correct pick is at least 0.90 and slot-1 is in 0.4 to 0.6 on each. All three judges pass today (this run).
   - Resolution gate on the held-out run: the share of scenarios where both orders pick the same answer (here 0.58 to 0.59) must be at least a preregistered floor (suggest 0.5; set it before the held-out seed and justify it with the spent rounds), and the unresolved share and the slot-1 rate are reported, not used to exclude.
2. Keep the current scoring (1/0 only when both orders agree, else 0.5) and the existing paired-bootstrap keep rule, but report the win rate with a stated sensitivity range: unresolved scenarios counted as 0.5 (headline), as all losses and as all wins, so the reader sees how much the skew can matter. The first judge passing the capability and resolution gates scores the skill, in the existing order.
3. Add a rival-fixture check before a skill is benched: if the resolved share on a 20-scenario tune slice is below the floor, the arms are too close for this judge to separate and the round is declared "underpowered" up front rather than "no verdict" after 150 scenarios.
4. Before adopting, preregister a small simulation or a spent-data replay (a judge with a slot-1 bonus delta applied to the round-4 and round-5 verdicts) showing the headline win rate is unbiased in expectation and only the width changes; item 5 of the diagnosis is the claim that needs it.

## Caveats

- Controls a, b and c are artificial: a gap of 70 percent of the text (b) is trivial, and a (identical) never occurs in a bench. Only c and the real-pair re-read speak to close contests, and the real-pair re-read is observational (a pair that both orders resolve by content may still contain a position pull).
- The "last section" in c is often a short note, so the gap is small and GLM sometimes ties it; correct pick is computed on decisive verdicts only.
- Items come from one writer-model family (growth-analytics, fictional scenarios); n = 60 per cell (120 verdicts); intervals are Wilson, per verdict, treating the two orders of an item as independent (they are not strictly, so the intervals are slightly narrow).
- Ledger: `scripts/bench_check.py` requires `ledger.jsonl` and `SHA256-frozen.txt`, so both were written after the judge calls and say so. This is a calibration, not a preregistered test. `calib.py` gained the `real` command and a no-decisive guard in `report` after the judge calls began; the judge-call path (`items`, `pair`, `judge`, `run`) did not change, and the hash in `SHA256-frozen.txt` is of the final file.
- Reproduce: `PCSS_ENV_FILE=<repo .env> python3 docs/bench/judge-calib-1018/calib.py run` (resumable), then `report` and `real`.
