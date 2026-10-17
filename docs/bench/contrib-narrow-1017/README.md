# Narrowed contribution skill against its rival, fresh held-out n = 60, 2026-10-17

BLUF: narrowing the contribution skill to the privacy-safe upstream-PR flow lifts its win rate against github-contributor from 0.250 to 0.550 (paired difference +0.300, 95% CI [0.183, 0.417], n = 60, judge GLM-5.1, slot-1 rate 0.444). The preregistered keep rule is met, so the edit ships. It does not yet beat the rival: win-rate CI [0.458, 0.642], lower bound not above 0.5. Spend $0.00 (PCSS only).

- Rule, arms and seeds: `PREREGISTERED.md` (hashes in `SHA256-frozen.txt`), `PREREGISTERED-ADDENDUM-1.md` (driver fix before any draw), `-2.md` (tune, edit frozen), `-3.md` (results); later hashes in `SHA256-amend.txt`.
- Scenarios: `scripts/eval-fixtures/rival/contribution/tune10.json` and `heldout60.json`, from `prompts/seeds.txt` by the blind writer.
- Raw outputs and judge verdicts: `results/`. Reproduce: `python3 docs/bench/contrib-narrow-1017/bench.py run heldout docs/bench/contrib-narrow-1017/frozen/contribution.v1.md <out>` (PCSS key from `.env`; the rival text is fetched from its public URL).
- Tune (n = 10, never a verdict) is noisy: v0 scored 0.40 and 0.25 across two regenerations of the same text.
- The shipped `SKILL.md` differs from the tested text in its description, the Verification list and two clauses (gate and eval requirements): `shipped-vs-tested.patch`, explained in `PREREGISTERED-ADDENDUM-3.md`.
