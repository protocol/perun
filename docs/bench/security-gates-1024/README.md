# Security gates corpus, 2026-10-24

Frozen synthetic corpora for the H5 (secret gate) and H8 (destructive-command guard) rows of docs/perun-vs-rivals.md. Drafted on 2026-10-24 before any Perun check was run on them; the before-fix scores come from that draft. The hashes below were pinned after the fixes, and every number is in-sample. All values are invented; secret lines carry `@@` markers (deleted by the scorer) so they never trip the repo privacy gate.

| File | Contents |
|---|---|
| secret-leaks.txt | 31 fake leaks in common provider formats, no PII |
| secret-decoys.txt | 34 look-alikes that must not be flagged (includes the public AWS documentation example key) |
| destructive-dangerous.txt | 46 dangerous command strings, including interpreter, IFS, brace, quote-split and wrapper tricks |
| destructive-benign.txt | 45 benign command strings |

Run: `python3 docs/bench/security-gates-1024/score.py` (offline, deterministic, nothing executed). It fails on hash drift against the SHA256 lines below. Rival tools (gitleaks and others) were not run: not installed, owner gate.

Caveat: Perun fixes in the same change post-date this corpus, so the after-numbers are in-sample. The guard is a best-effort string check, not a security boundary.

## SHA256
```
d718d24caf1112adcfccc4bce1ea94a5170bbe2b0512d3f42919bbb060382d16 destructive-benign.txt
70e849016b643b7c61c01175655ca2f647980d99ac3779a6744a692ccee2595d destructive-dangerous.txt
270469ea29a1c53599d5cfc3ff99bdf7612a4cb45572e28160bd3bf22d505b0d secret-decoys.txt
2a88a92b3e6867f1a33d4e36f5ade61189bc1ba899ae826e48d855c76937689d secret-leaks.txt
```

## Results (2026-10-24, `score.py`)

| Check | Before fixes | After fixes |
|---|---|---|
| Secret gate recall | 20/31 | 30/31 |
| Secret gate false positives | 1/34 (AWS documentation example key) | 1/34 (same) |
| Destructive guard blocked | 29/46 | 46/46 |
| Destructive guard false positives | 0/45 | 0/45 |

Remaining secret miss: `gh_ghs` is a 35-character `ghs_` fixture (the real format is 36), kept frozen and counted as a miss. The AWS documentation key stays a false positive because an ERE cannot exclude the `EXAMPLE` suffix. Held-out variants and decoys for each fix are in `scripts/test_security_gates_corpus.py`. The older 32-string guard corpus in `scripts/test-destructive-guard.sh` went from 30/32 to 31/32 (a secret piped to `curl -d @-` is still allowed).

Freeze note: the before-fix scores were taken on the first draft. Afterward two secret lines (`aws_secret`, `generic_json`) gained `@@` markers so the files pass the repo privacy gate; the scorer strips markers, so the scored text is unchanged. `SHA256-frozen.txt` and `ledger.jsonl` were written after the fixes (see the ledger note); they pin the corpora from here on.
