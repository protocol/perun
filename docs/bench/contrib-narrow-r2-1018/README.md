# Narrowed contribution skill against its rival, round 2, fresh held-out n = 60, 2026-10-18

BLUF: KEEP. The shipped narrowed text scores 0.558 [0.458, 0.658] against github-contributor, the previous text 0.242 [0.158, 0.333]; paired difference +0.317, 95% bootstrap CI [0.183, 0.450] (n = 60 of 60 scored, judge GLM-5.1, slot-1 rate 0.567, healthy). The preregistered keep rule (paired lower bound above 0) is met. Superiority over the rival is not claimed: win-rate lower bound 0.458 is not above 0.5. Spend $0.00 (PCSS only).

- Rule, arms, seeds: `PREREGISTERED.md`. Its hash list is `SHA256-frozen.txt`; `ledger.jsonl` records the preregistration hash before any generation, then the scenario-set hash (drawn before any arm output) and the results hash.
- Tested text: `frozen/contribution.v1.md`, byte-identical to the shipped `SKILL.md` (no tuning, no post-test edit). v0 is origin/main's text. The rival text is frozen in `frozen/rival.md` (sha256 prefix 98e03b82, identical to round 1's).
- Scenarios: `scenarios-heldout60.json`, ids r2h01 to r2h60, from `prompts/seeds.txt`; the maximum 6-word-shingle overlap with every earlier contribution set (including round 1's) is 0.025, ids are disjoint.
- Raw outputs and verdicts: `results/outputs`, `results/judge-verdicts.json` (the judge caches folded into one file; every verdict is kept), `results/verdict.json`. Reproduce: `python3 docs/bench/contrib-narrow-r2-1018/bench.py run <out>` then `fold <out>` (PCSS key from `.env`).

| Judge | Slot-1 | v0 | v1 | Paired diff [95% CI] |
|---|---|---|---|---|
| GLM-5.1 (used) | 0.567 | 0.242 | 0.558 | +0.317 [0.183, 0.450] |
| GLM-5.2 (sensitivity) | 0.556 | 0.308 | 0.542 | +0.233 [0.108, 0.358] |
| gpt-oss_120b (sensitivity, outside the 0.4 to 0.6 gate) | 0.636 | 0.250 | 0.592 | +0.342 [0.225, 0.458] |

Strict result for v1 under the used judge: 23 wins, 21 ties or splits, 16 losses. All three judges agree on the sign and on a lower bound above 0.

## Round 1 (exploratory, not preregistered)

Round 1 (`contrib-narrow-1017`) is not in this repository. It had no `ledger.jsonl`, so its preregistration timing cannot be checked; its shipped text differed from its tested text in the description, the Verification list and two clauses; and it dropped the issues-only opt-in exception. Treat its numbers as exploratory: on 60 held-out scenarios (GLM-5.1, slot-1 rate 0.444) the narrowed text scored 0.550 [0.458, 0.642] against 0.250 [0.158, 0.342] for the previous text, paired difference +0.300 [0.183, 0.417]. Round 1's preregistration also named its held-out ids h01 to h60 while its driver produced h11 to h70; this round's ids are r2h01 to r2h60 and match the seeds. A local absolute path that appeared in round 1's record is redacted and not carried here.

## Changes since round 1's shipped text

The "Opt-in exception: issues only" paragraph is restored. The clause telling the contributor to imprint a project-only quirk in `AGENTS.md` is removed (never benched; the reference file still carries that destination for borderline lessons). Two safety rules cut in round 1 are kept in short form: never delete an existing instrument to make room for an addition, and no unsupervised consolidation loop writing to the shared skillset.

## Caveats

Qwen3.5-397B-A17B generates every arm (not necessarily the model the skill runs on); judges are the PCSS models in `scripts/rival_eval.py`; the rival is one public skill; the narrowed skill changes scope as well as wording, so the gain is for requests about contributing to another project and is not evidence about the skillset-lesson flow it no longer describes in prose. One run per arm; the seed set and brief were written by the operator and the scenarios by one blind writer model.
