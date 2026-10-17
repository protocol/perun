# Tune result and choice (recorded 2026-10-17, after the tune run and before any held-out generation)

Tune, n=10 (scenarios 01-10), win rate against the rival, three judges in both orders, strict agreement, majority (`results4-idea-critic-PERUN_*-tune.json`, `judge4/`):

| arm | win rate | 95% interval |
|-----|----------|--------------|
| v0 (current SKILL.md) | 0.55 | [0.35, 0.75] |
| cA (capped first tranche, in-cap tripwire) | 0.65 | [0.50, 0.80] |
| cB (figure mismatch first, arithmetic shown) | 0.50 | [0.25, 0.75] |
| cC (cA plus cB) | 0.50 | [0.25, 0.75] |

Choice by the preregistered rule (highest tune win rate): `cA`, which is also above v0. Held-out run: `cA` and `v0` on `scenarios4/idea-critic-h4.json`, keep rule unchanged (lower bound above 0.5 and at least v0).

The tune run had intermittent network errors (URLError retries, logged in `ledger.jsonl`); every one of the 40 judge records is complete (no order lost to a failed call), so no verdict was turned into a tie by an error.
