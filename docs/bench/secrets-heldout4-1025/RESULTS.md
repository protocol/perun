# Secrets held-out 4 results, 2026-10-25

**BLUF.** On a fourth blind corpus (60 live-format leaks, 60 hard decoys, authored without reading any scanner), the secret gate found 47 of 60 leaks before this change and 60 of 60 after, with one decoy flagged both times (D034, a placeholder word outside the matched span). The 60/60 is in-sample: ten rules were written after reading the 13 misses, so it is not evidence of out-of-sample recall. The blind numbers are the 47/60 rows below.

**Blind rows (scored once, rules frozen before seeing any row).**

| System | Commit | Leaks found (60) | Decoys flagged (60) |
|---|---|---|---|
| Perun gate, before the precision review | f4e6b4bf3 | 47 | 0 |
| Perun gate, after the precision review (base of this change) | 607661844 | 47 | 1 |
| Perun gate, main | 8eb9fc0d5 | 47 | 4 |
| gitleaks v8.30.1 (ported) | n/a | 43 | 2 |
| Perun banlist only | n/a | 31 | 3 |

The gitleaks and banlist rows are recomputed by `score.py` on every run; the three gate rows at other commits are historical and cannot be recomputed from this tree.

**In-sample after row (this change).**

| System | Leaks found (60) | Decoys flagged (60) |
|---|---|---|
| Perun gate with the EXTRA rules | 60 | 1 (D034) |

The 13 misses fixed: L014 L024 L028 L029 L031 L038 L049 L051 L052 L054 L055 L059 L060. Fix: ten rules in `EXTRA` (`scripts/secret_scan.py`) for Discord webhooks, credentials in URLs, `SECRET_KEY` and `jwt.sign` string literals, Google client secrets (`GOCSPX-`), UUID-valued `*_key`/`*_token` assignments, `Authorization: Bearer` values, `password = "..."` literals, `-p'...'` on `mysql`/`sshpass`-style CLIs, and Telegram bot tokens. They run only in the gate (`precise=True`), never in the rival bench, so the gitleaks column is unchanged. Each needs entropy above a floor, skips the placeholder words, skips values that start with a template sigil (`$`, `{`, `<`, `%`, `*`), and skips identifier-shaped values (dotted paths, env references, snake_case or camelCase names). Decoy twins are pinned in `scripts/test_secret_extra_rules.py`.

**Other held-out corpora, same change (union column, recomputed with the unchanged corpora).**

| Corpus | Before | After |
|---|---|---|
| Held-out 1 | 30/30, FP 0/30 | 30/30, FP 0/30 |
| Held-out 2 | 33/40, FP 0/40 | 35/40, FP 0/40 |
| Held-out 3 | 54/60, FP 8/60 | 56/60, FP 8/60 |

No regression. The held-out-2 and -3 gains (L2-19, L2-29; L045, L057) come from the same rules and are in-sample for them too.

**Method and caveats.** `score.py` drives the real `ci-gates.sh privacy` for the union and asserts every union hit is a banlist hit, a gitleaks hit, or an EXTRA hit. Pins: `scripts/test_secrets_heldout4_blind.py`. Same-model-family author as Perun's rule writers; the gitleaks column is a Python port without decode-and-rescan; n is small; rows are scored as one-line files named `x.txt`. The corpus ledger and frozen list were repaired before landing (see the README); no row changed.

## Leads

- D034 (placeholder-looking word outside the matched span) is accepted: judging the span only is the rule.
- A fresh corpus is needed to measure the EXTRA rules out of sample.
