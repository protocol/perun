# Secrets held-out 5 results, 2026-10-25

**BLUF.** On a fifth blind corpus (60 live-format leaks, 60 hard decoys, authored without reading any scanner), the secret gate found 27 of 60 leaks before this change and 43 of 60 after, with no decoy flagged after. The 43/60 is in-sample: the rules were written after reading the misses. The blind numbers are the 27/60 rows below. The main cause of the loss was the placeholder word "example" hiding real-shaped values that merely contain it.

**Blind rows (scored once, rules frozen before seeing any row).**

| System | Commit | Leaks found (60) | Decoys flagged (60) |
|---|---|---|---|
| Perun gate, wave 2 (base of this change) | 7c2c9dd66 | 27 | 1 |
| Perun gate, precision review | 607661844 | 20 | 1 |
| Perun gate, main | 8eb9fc0d5 | 34 | 3 |
| gitleaks v8.30.1 (ported) | n/a | 23 | 3 |
| Perun banlist only | n/a | 19 | 1 |

The gitleaks and banlist rows are recomputed by `score.py` on every run; the gate rows at other commits are historical and cannot be recomputed from this tree.

**In-sample after row (this change).**

| System | Leaks found (60) | Decoys flagged (60) |
|---|---|---|
| Perun gate | 43 | 0 |

Fixes, all in `scripts/secret_scan.py` (gate only, never the rival bench):

- `PLACEHOLDER` no longer matches "example" embedded in a longer word or token (`AcmeExampleToken`, `ACMEEXAMPLE12`). It matches only the whole word (`example`, `Example`, `EXAMPLE`, not followed by letters or a domain suffix) or the AWS documentation suffix (`...EXAMPLE`, `...EXAMPLEKEY` at the end of the value). This recovered 13 leaks with no new decoy hit.
- New EXTRA rules: `hvs.` Vault tokens (L049), `Authorization: Basic` values (L043), `;password=` / `pwd=` in connection strings (L054), `--token`-style CLI flags (not path or file values), `password` assignments (`=` or `:` only, not `_length`/`_min`/`_max`/`_policy` names), Telegram tokens without the `AA` prefix, Sentry DSNs only in the legacy `key:secret@` form (a key-only DSN is public by design, so L016 stays a miss). A placeholder comment on a Google API key line now applies only to the key it follows.
- An unsigned JWT (empty signature) is not a credential: D024 no longer flagged.

Still missed (17): L001 L002 L003 L007 L016 L018 L021 L025 L028 L036 L039 L040 L041 L042 L044 L048 L052. Their values are not in the real vendor shape (short or wrong-length bodies, words in the key body, a low-entropy URL password), so a rule would be a guess. They stay misses.

Decoy twins and live pins: `scripts/test_secret_extra_rules_w3.py`. Pins: `scripts/test_secrets_heldout56_blind.py`.

**Other corpora, same change (union column, recomputed).** Held-out 1 30/30 FP 0 (unchanged), held-out 2 35/40 FP 0 (unchanged), held-out 3 56/60 FP 7 (was FP 8), held-out 4 60/60 FP 1 (unchanged), held-out 6 59/60 FP 0 (was 50, FP 2). No regression.

**Blind versus in-sample.** The corpus was blind at authoring; after the wave 3 tuning above every after-row on it is in-sample.

**Caveats.** Same-model-family author as Perun's rule writers; the gitleaks column is a Python port without decode-and-rescan; n is small; rows are scored as one-line files named `x.txt`.
