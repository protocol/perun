Business-ops candidate e, confirmatory test, 2026-10-18. Preregistration: PREREGISTERED.md (+ PREREGISTERED-ADDENDUM-1.md); hashes in SHA256-frozen.txt, SHA256-amend.txt, SHA256-scenarios.txt; append-only ledger.jsonl. All calls on the PCSS endpoint, $0. Rival text is MIT, notice in LICENSE.rival.txt.

Question: e ("lead with the call", frozen text from ../bizops-call-1017) scored paired e - v0 +0.083 [-0.025, 0.183] at n=60, underpowered. This is one confirmatory test of the same e text. Disclosure: a second test after a near-miss, so the false-positive risk is higher than a first test.

Held-out, n=150 fresh scenarios (ids c150-001..c150-150, `bench.py check` clean against 286 earlier business-ops prompts by id, exact text and 6-word shingles), generator Qwen3.5-397B-A17B, judge v2 of scripts/rival_eval.py (GLM-5.1 slot-1 rate 0.511 so it scored both arms), both orders, strict agreement else 0.5, rival generated once and shared, bootstrap 10,000 resamples seed 1:
  v0                   0.473 [0.397, 0.547]   62 wins / 18 ties / 70 losses
  e                    0.563 [0.490, 0.633]   71 / 27 / 52
  paired (e - v0)      +0.090 [0.037, 0.143]
Ship rule (paired CI lower bound above 0): passed (0.037), so e is applied to .claude/skills/business-ops/SKILL.md. Superiority rule (e win-rate lower bound above 0.5): failed (0.490); no claim of beating the rival.

Reproduce: python3 -I bench.py unpack (outputs.jsonl and judge.jsonl hold the per-scenario files; see PREREGISTERED-ADDENDUM-2.md), then python3 -I bench.py run v0 e (cached outputs and judge records are reused), then bench.py paired. Existing records are never overwritten.
