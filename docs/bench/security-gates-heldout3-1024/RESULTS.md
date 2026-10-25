# Held-out 3 results, 2026-10-25

**BLUF.** On a third blind corpus (60 live-format leaks, 60 hard decoys) the secret gate as shipped, the banlist unioned with the gitleaks default rules, found 54 of 60 leaks and flagged 16 of 60 decoys. The banlist alone found 41 of 60 (12 of 60 decoys flagged); ported gitleaks alone found 47 of 60 (8 of 60 flagged). The union beats both parts on recall by 7 to 13 leaks, and pays for it with the union of their false positives (16 flagged against 12 and 8). Out of sample, the gate no longer trails gitleaks on recall, at the cost stated above: twice gitleaks' false positives.

**Method.** Corpora were committed as 8068504a6 (prereg/heldout3) before any scoring; `SHA256-frozen.txt` pins them. The rules (the banlist at the base commit and the vendored gitleaks v8.30.1 config) were frozen before scoring and nothing changed after seeing a row; this was scored once. Before scoring two rows gained an `@@` marker (L053, D037), disclosed as ledger amendments; stripped content and scores are unaffected. Run: `python3 -I docs/bench/security-gates-heldout3-1024/score.py`, which drives the real `ci-gates.sh privacy` for the union and asserts union equals banlist OR gitleaks on every row. Pins: `scripts/test_security_gates_heldout3.py`.

| System | Leaks found (60) | Decoys flagged (60) |
|---|---|---|
| Perun union (banlist + gitleaks rules, the shipped gate) | 54 | 16 |
| Perun banlist only | 41 | 12 |
| gitleaks v8.30.1 (ported) | 47 | 8 |

**Caveats.** The decision to union gitleaks into the gate was made after seeing held-out-2, where the same union finds 33/40 (up from 23/40 for the banlist alone); that 33/40 is partly in-sample and is not evidence. Held-out-3 is the out-of-sample test of the union, because the union and every rule were frozen before it was scored. Same-model-family author as Perun's rule writers; gitleaks is a Python port without decode-and-rescan, not the binary; n is small. The gitleaks half scores each row as a one-line file named `x.txt`, with no path context. Push-protection was not queryable offline, so the `@@` amendments used raw-text hits of the gitleaks rules as the criterion.

## Leads (misses and false positives, not fixed here)

- Missed by the union: L004, L006, L021, L045, L056, L057 (also missed by both parts).
- Flagged decoys: 16 of 60 (D004, D006, D007, D008, D009, D020, D021, D025, D029, D030, D032, D033, D037, D038, D040, D050). Placeholder-looking `generic-api-key` hits dominate the gitleaks side; the banlist side flags 12 of them already.

## Precision pass (in-sample, after seeing this corpus)

The blind rows above stay the out-of-sample result. After they were scored, the gate gained a placeholder pass (`PLACEHOLDER` in `scripts/secret_scan.py`): a hit is dropped when the matched text itself (never the rest of its line) carries a documentation word (example, dummy, fake, placeholder, redacted, revoked, replace-me, changeme), a filler run (8+ `x`, 10+ `0`), a Stripe test-mode or publishable key prefix, a `NEXT_PUBLIC_` variable name, a Mapbox public token or a CSRF key name. The gitleaks half applies it to every match; the banlist half applies it only to patterns under its secret headers (names and PII are never relaxed) and fails closed when it cannot verify a file. `example.com` host names do not count as the word. An earlier draft judged the whole line and let a real token through when a placeholder word sat elsewhere on it; that was a bug and is fixed, with regression tests.

| System (in-sample, re-scored on this corpus) | Leaks found (60) | Decoys flagged (60) |
|---|---|---|
| Perun union with placeholder pass (the shipped gate) | 54 | 8 |

Recall is unchanged (same six misses); decoys flagged fell from 16 to 8 (D007, D021, D025, D032, D037, D038, D040, D050: the placeholder cue sits in a trailing comment or a key name outside the match, which the gate deliberately ignores). This is tuned on the rows it is scored on, so treat 8/60 as an upper bound on the gain until a fresh corpus confirms it. Pins: `scripts/test_security_gates_heldout3.py`, `scripts/test_secret_precision.py`.
