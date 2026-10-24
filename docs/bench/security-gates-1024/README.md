# Security gates corpus, 2026-10-24

Frozen synthetic corpora for the H5 (secret gate) and H8 (destructive-command guard) rows of docs/perun-vs-rivals.md. Drafted on 2026-10-24 before any Perun check was run on them; the before-fix scores come from that draft. The hashes below were pinned after the fixes, and every number is in-sample. All values are invented; secret lines carry `@@` markers (deleted by the scorer) so they never trip the repo privacy gate.

| File | Contents |
|---|---|
| secret-leaks.txt | 31 fake leaks in common provider formats, no PII |
| secret-decoys.txt | 34 look-alikes that must not be flagged (includes the public AWS documentation example key) |
| destructive-dangerous.txt | 46 dangerous command strings, including interpreter, IFS, brace, quote-split and wrapper tricks |
| destructive-benign.txt | 45 benign command strings |

Run: `python3 docs/bench/security-gates-1024/score.py` (offline, deterministic, nothing executed). It fails on hash drift against the SHA256 lines below. Rival rules are scored by `python3 -I docs/bench/security-gates-1024/rivals/score_rivals.py` (pins and gaps in `rivals/SOURCES.md`).

Caveat for the rival rows: rules ported to Python, not the rival binary; ported-rule fidelity is the main threat. Nothing downloaded was executed (data only). The safety-net port is a subset scored three-state (block, allow, unported); its number is a ported-subset result, not the tool's score. Unported rule families: heredocs, PowerShell and cmd, awk, parallel, policy files, strict and paranoid modes, worktree and temp-root relaxations, shell variable assignment tracking, filesystem-dependent path resolution, the raw-text fallback, the interpreter exec-sink check, `git rm`, `git rebase --abort`, `git reflog delete`, disk-erase tools and nested `$(...)` analysis. hooks-mastery targets only `rm -rf` and `.env` by design, so 13/46 is not a general quality comparison. `go2py` keeps Python's Unicode `\d`, `\w`, `\s` and `\b` where Go RE2 uses ASCII, which slightly favours gitleaks.

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

Rival rows (ported rules, same corpus, `rivals/score_rivals.py`):

| Tool (pinned) | Secret recall | Secret FP | Destructive blocked | Destructive FP |
|---|---|---|---|---|
| Perun | 30/31 | 1/34 | 46/46 | 0/45 |
| gitleaks v8.30.1 default config | 22/31 | 0/34 | n/a | n/a |
| claude-code-safety-net (subset port) | n/a | n/a | 27/46 ported-subset result (4 rows unported) | 0/45 |
| hooks-mastery (exact port) | n/a | n/a | 13/46 | 5/45 |

gitleaks misses 9: 5 fixtures are off the provider's real format (AWS keys with non-base32 digits, 35-character `ghs_`, short fine-grained PAT, short Anthropic key), 3 are header-only PEM lines, 1 is a connection URL. Decode-and-rescan and path rules are not ported.

Remaining secret miss: `gh_ghs` is a 35-character `ghs_` fixture (the real format is 36), kept frozen and counted as a miss. The AWS documentation key stays a false positive because an ERE cannot exclude the `EXAMPLE` suffix. Held-out variants and decoys for each fix are in `scripts/test_security_gates_corpus.py`. The older 32-string guard corpus in `scripts/test-destructive-guard.sh` went from 30/32 to 31/32 (a secret piped to `curl -d @-` is still allowed).

Freeze note: the before-fix scores were taken on the first draft. Afterward two secret lines (`aws_secret`, `generic_json`) gained `@@` markers so the files pass the repo privacy gate; the scorer strips markers, so the scored text is unchanged. `SHA256-frozen.txt` and `ledger.jsonl` were written after the fixes (see the ledger note); they pin the corpora from here on.
