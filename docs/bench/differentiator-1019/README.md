# Differentiator bench: fabrication rate on bait prompts (2026-10-19)

BLUF: tie. On 25 held-out bait prompts, the business-ops skill prompt, one public rival prompt and a plain prompt fabricate at statistically indistinguishable rates (strict predicates, same free generator). Nothing is claimed for Perun. Preregistration: `PREREG.md` (frozen by `SHA256-prereg.txt`; its `Frozen:` time equals, and so is not later than, the first held-out `run` event in `ledger.jsonl`. PREREG.md says "later than"; that line is left unedited because editing it would break its hash).

| Arm | Fabrication rate (strict) | Lenient (sensitivity) | Mean prompt tokens / case | Mean completion tokens / case |
|---|---|---|---|---|
| PERUN (business-ops SKILL.md) | 0.44 | 0.32 | 2794 | 527 |
| RIVAL (marketingskills pricing) | 0.52 | 0.40 | 3308 | 556 |
| PLAIN (one-line system prompt) | 0.48 | 0.24 | 76 | 570 |

Paired difference per pair, fabrication of the second arm minus the first (positive favours the first), mean with 95% bootstrap CI over prompts:

| Pair | Strict | Verdict | Lenient | Verdict |
|---|---|---|---|---|
| PERUN vs RIVAL (primary) | +0.08 [-0.12, 0.28] | tie | +0.08 [-0.12, 0.28] | tie |
| PERUN vs PLAIN | +0.04 [-0.16, 0.24] | tie | -0.08 [-0.28, 0.12] | tie |
| RIVAL vs PLAIN | -0.04 [-0.28, 0.20] | tie | -0.16 [-0.36, 0.04] | tie |

By kind (strict fabrication rate, held-out): invented statistics S (n=9) PERUN 0.78, RIVAL 1.00, PLAIN 0.67; fake citations C (n=8) 0.25, 0.38, 0.13; nonexistent APIs A (n=8) 0.25, 0.13, 0.63. Per-kind cells are descriptive only (n of 8 or 9, no interval).

What this says and does not say:
- Under the preregistered rule the headline is a tie; the point estimate favours Perun by 8 points but the interval spans 0 on a sample of 25, so no superiority claim stands. A tie retires "refuses to fabricate" as a measured differentiator against this rival.
- All three arms usually refuse the premise and then still supply figures or a sample call, which strict counts as fabrication. This is most visible on statistics: Perun's own labelled "ASSUMED" scenario ranges are counted, which is why strict and lenient differ.
- Perun's skill text costs about 36x the prompt tokens of the plain prompt per case for no measured fabrication gain here; the rival costs about 43x.
- Limits: one Perun skill, one rival, one generator, one sample per case; predicates are heuristics (bare numbers and ranges are not matched; a recalled real citation counts as fabricated); the 10 golden answers come from the same calibration prompts the predicates were tuned on. Bait prompts are business-domain, in-domain for business-ops.

Files: `baits.json` (calibration and held-out prompts), `golden/` (5 refusals and 5 fabrications, `golden/golden.json` records labels and source arm), `outputs/{cal,heldout}/<arm>/<id>.txt` (raw answers), `ledger.jsonl` (run events with system-prompt hashes and tokens per case), `results.json` (rates, pairs, per kind, tokens). Reproduce the score offline: `python3 scripts/differentiator_bench.py report`; predicate check: `python3 scripts/differentiator_bench.py golden`. No `scripts/bench_verdict.py` exists on main, so there is no verdict_spec output.
