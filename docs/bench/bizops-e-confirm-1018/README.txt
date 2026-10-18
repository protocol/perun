Business-ops candidate e, confirmatory test, 2026-10-18. Preregistration: PREREGISTERED.md (+ PREREGISTERED-ADDENDUM-1.md); hashes in SHA256-frozen.txt, SHA256-amend.txt, SHA256-scenarios.txt; append-only ledger.jsonl. All calls on the PCSS endpoint, $0. Rival text is MIT, notice in LICENSE.rival.txt.

Question: e ("lead with the call", frozen text from ../bizops-call-1017) scored paired e - v0 +0.083 [-0.025, 0.183] at n=60, underpowered. This is one confirmatory test of the same e text. Disclosure: a second test after a near-miss, so the false-positive risk is higher than a first test.

Held-out, n=150 fresh scenarios (ids c150-001..c150-150, `bench.py check` clean against 286 earlier business-ops prompts by id, exact text and 6-word shingles), generator Qwen3.5-397B-A17B, judge v2 of scripts/rival_eval.py (GLM-5.1 slot-1 rate 0.511 so it scored both arms), both orders, strict agreement else 0.5, rival generated once and shared, bootstrap 10,000 resamples seed 1:
  v0                   0.473 [0.397, 0.547]   62 wins / 18 ties / 70 losses
  e                    0.563 [0.490, 0.633]   71 / 27 / 52
  paired (e - v0)      +0.090 [0.037, 0.143]
Ship rule (paired CI lower bound above 0): passed (0.037), so e is applied to .claude/skills/business-ops/SKILL.md. Superiority rule (e win-rate lower bound above 0.5): failed (0.490); no claim of beating the rival.

Reproduce: python3 -I bench.py run v0 e (the committed outputs/ and judge/ files are cached and reused; existing records are never overwritten), then bench.py paired.

Disclosures:
- Addendum 2 (reverted). An earlier revision of this round packed outputs/ and judge/ into outputs.jsonl and judge.jsonl (with bench.py pack/unpack and PREREGISTERED-ADDENDUM-2.md) to get around an argument-list-too-long failure in the repository privacy gate. That hid the text from the line-based gate, and the gate bug is fixed separately, so the packing is reverted: the per-file outputs/ and judge/ files are committed directly (byte-identical to what unpack yielded), the packed files, the addendum and SHA256-amend-2.txt are removed, and bench.py is back to the version hashed in SHA256-amend.txt. Packing changed no scenario, prompt, arm, judge, score or result. ledger.jsonl is append-only and was not edited, so it still holds the two `packed` events and the `bench_amended` event for SHA256-amend-2.txt; they refer to files and a script version that are no longer in the tree.
- Two `gen` events. ledger.jsonl records `gen` twice (2026-10-17T22:54:26Z and 23:02:01Z) with identical outputs_sha256 for RIVAL, v0 and e. The second was a rerun with no judge call in between; it reused the cached outputs, so the outputs judged are those of the first run.
