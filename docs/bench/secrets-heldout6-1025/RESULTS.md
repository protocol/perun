# Secrets held-out 6 results, 2026-10-25

**BLUF.** On a sixth blind corpus (60 live-format leaks, 60 hard decoys, authored without reading any scanner), the secret gate found 50 of 60 leaks before this change and 59 of 60 after, with no decoy flagged after (two before). The 59/60 is in-sample: rules were written after reading the 10 misses. The blind numbers are the 50/60 rows below.

**Blind rows (scored once, rules frozen before seeing any row).**

| System | Commit | Leaks found (60) | Decoys flagged (60) |
|---|---|---|---|
| Perun gate (base of this change) | 33df1416f | 50 | 2 |
| Perun gate, main | 7453990b1 | 45 | 7 |
| gitleaks v8.30.1 (ported) | n/a | 40 | 3 |
| Perun banlist only | n/a | 33 | 6 |

The gitleaks and banlist rows are recomputed by `score.py` on every run; the gate rows at other commits are historical and cannot be recomputed from this tree.

**In-sample after row (this change).**

| System | Leaks found (60) | Decoys flagged (60) |
|---|---|---|
| Perun gate | 59 | 0 |

The 9 misses fixed: L021 L022 L023 L024 L058 L048 L049 (passwords in YAML, env, Dockerfile `ENV`, netrc and `PGPASSWORD=` forms), L044 (`--token <hex>` CLI flag), L054 (Telegram token without the `AA` prefix). L033 (a key-only Sentry DSN) stays missed: that DSN form is public by design, so the Sentry rule covers only the legacy `key:secret@` form. Fix: new gate-only EXTRA rules in `scripts/secret_scan.py`. The password rule needs `=` or `:` as the separator (whitespace only for Dockerfile `ENV`/`ARG` and netrc `login X password Y`), a letter and a digit, at least 8 characters, entropy above 3.0, and skips names starting `test_` or ending `_length`/`_min`/`_max`/`_policy`, values that are just a weak word (`passw`/`secret`/`admin`/`qwerty`/`letmein`, plus up to six digits or `!`), template sigils and identifier-shaped values.

The 2 decoys fixed: D057 (`xoxb-your-token-here`; `your-` or `your_` is now a placeholder word) and D060 (a Google API key on a line saying it is a referrer-restricted public key; both gate halves skip it, per match: the comment must follow that key and no second key may precede it).

**Other corpora, same change (union column, recomputed).** Held-out 1 30/30 FP 0 (unchanged), held-out 2 35/40 FP 0 (unchanged), held-out 3 56/60 FP 7 (was FP 8), held-out 4 60/60 FP 1 (unchanged), held-out 5 43/60 FP 0 (was 27, FP 1). No regression.

Decoy twins and live pins: `scripts/test_secret_extra_rules_w3.py`. Pins: `scripts/test_secrets_heldout56_blind.py`.

**Blind versus in-sample.** The corpus was blind at authoring; after the wave 3 tuning above every after-row on it is in-sample.

**Caveats.** Same-model-family author as Perun's rule writers; the gitleaks column is a Python port without decode-and-rescan; n is small; rows are scored as one-line files named `x.txt`.
