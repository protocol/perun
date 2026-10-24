# Held-out security gates, 2026-10-24

**BLUF.** On corpora written blind, Perun's secret gate found 21 of 30 synthetic leaks (2 of 30 decoys flagged) and its destructive guard blocked 26 of 40 dangerous commands (3 of 40 benign blocked); after rules written against those misses, 30 of 30 leaks (2 of 30 decoys) and 40 of 40 blocked (3 of 40 benign), now in-sample. Ported gitleaks found 23 of 30 leaks (0 FP). Ported hooks-mastery blocked 9 of 40 (6 FP) and the ported claude-code-safety-net subset 17 of 40 (2 FP). Out of sample, Perun trails gitleaks on secret recall and leads on destructive blocking, but the in-sample 30/31 and 46/46 did not generalize: the guard has no cloud, orchestration or NoSQL-store coverage, which the first corpus never exercised.

**Method.** The four corpora below were authored before reading `.banlist.txt`, `destructive_guard.py`, the first corpus or the rival ports; only the `@@` marker convention was taken from `score.py`. Their preregistration hashes were committed locally before scoring (commit ad168d8c6, squashed into this commit); `SHA256-frozen.txt` pins them. The timestamp cannot be checked from public history; `score.py` and `rivals/score_rivals.py` then ran unchanged apart from a `--corpus-dir` argument. No rule was changed after seeing results. All values are invented; secret lines carry `@@` markers so they never trip the privacy gate.

**Caveat.** The decoy `doc-example-aws` is the public AWS documentation example key; flagging it is arguably correct, so 1 of Perun's 2 decoy flags is label-driven (1 of 30 on the other label). The author is from the same model family as the one that wrote much of Perun's rules, so shared blind spots are possible and would flatter Perun; rival ports are Python ports, not the rival binaries (ported-rule fidelity is the main threat). Some benign labels are debatable: `git stash drop`, `find . -name '*.pyc' -delete` and `rm -rf /tmp/acme-demo-cache` are scoped deletions that a strict guard may reasonably refuse; counting them as non-FP would give Perun 0 of 40 FP. n is small, so treat differences of a few rows as noise.

Run: `python3 docs/bench/security-gates-1024/score.py --corpus-dir docs/bench/security-gates-heldout-1024` and `python3 -I docs/bench/security-gates-1024/rivals/score_rivals.py --corpus-dir docs/bench/security-gates-heldout-1024`. Pins: `scripts/test_security_gates_heldout.py`.

| System | Secret leaks found (30) | Decoys flagged (30) | Dangerous blocked (40) | Benign blocked (40) |
|---|---|---|---|---|
| Perun, before (as scored blind) | 21 | 2 | 26 | 3 |
| Perun, after gatefix2 (in-sample now) | 30 | 2 | 40 | 3 |
| gitleaks v8.30.1 (ported) | 23 | 0 | n/a | n/a |
| hooks-mastery (ported) | n/a | n/a | 9 | 6 |
| claude-code-safety-net (ported subset) | n/a | n/a | 17 | 2 |

**This corpus is now in-sample.** The rows below were fixed by format-spec patterns and verb rules (`.banlist.txt`, `destructive_guard.py`; variants and decoys in `scripts/test_security_gates_heldout_fixes.py`), so 30/30 and 40/40 prove nothing about unseen data; the out-of-sample test is `docs/bench/security-gates-heldout2-1024`. The first corpus stays at 30/31, FP 1/34 and 46/46, FP 0/45. The 2 decoy and 3 benign flags are unchanged.

## Leads (misses at blind scoring; fixed afterwards, see above)

- Secret gate missed 9: AWS secret key in a credentials file, Twilio auth token, Docker Hub PAT, JWT bearer header, Azure storage connection string, Discord bot token, Telegram bot URL, Linear API key, Mailgun key. Flagged decoys: `sk-xxxx...` placeholder, the AWS documentation example key.
- Destructive guard missed 14: `eval` of a base64 payload, `wipefs`, `diskutil eraseDisk`, `redis-cli FLUSHALL`, mongo `dropDatabase`, and every cloud and orchestration row (`aws s3 rm/rb`, `ec2 terminate-instances`, `rds delete-db-instance`, `gcloud projects delete`, `az group delete`, `terraform destroy`, `kubectl delete namespace/all`). It flagged three benign rows (`git stash drop`, `find ... -delete`, `rm -rf /tmp/...`).
- Gitleaks missed 7 (AWS key env, Anthropic key log line, Docker Hub PAT, both DB URLs with passwords, PEM header, Telegram bot URL); Perun caught 5 of them and missed only Docker Hub PAT and Telegram bot URL. Gitleaks caught 7 that Perun missed (AWS secret, Twilio, JWT, Azure, Discord, Linear, Mailgun).

## Frozen hashes

The local preregistration commit (ad168d8c6, squashed away) pinned `secret-leaks.txt` at `d7aef600ac9ad7c9b511c7f467e066d12f5bf99d98197192b9ec6eadbcc9217c`. Before any scoring, the repo privacy gate flagged three rows (Slack webhook URL, two database URLs) that lacked `@@` markers, so markers were added to those rows only; with every `@@` removed the file is byte-identical to the preregistered one once `@@` is stripped from both (sha256 `7c5309f21640db3a8a7eb77cb63f94e557d066ea8b7a8fb13d840d040f650cfd`, asserted by `scripts/test_security_gates_heldout.py`). After scoring, GitHub push protection blocked three more unmarked rows (Twilio account SID, Azure storage key, Mailgun key), so markers were added to those too; the `@@`-stripped content, and therefore every score, is unchanged. The other three corpora are unchanged. `SHA256-frozen.txt` keeps the four preregistered lines and appends both `secret-leaks.txt` amendments; `ledger.jsonl` records each with its time; it was reconstructed after the fact from commit and reflog times,, and the second amendment's time is the committer time of commit 587f293a6. Hashes now pinned:

714861750f651ddde17f0ff3a49e0735b7e5480369f1c56b2545a6c078a02b5b  secret-leaks.txt
c5f82cec87517931a0fed914c2fa8ece8a096868b535260856686a4560329c12  secret-decoys.txt
b0962b37d1bab25264ce28b9ae09488412496a6afd622c86f44ddb4accee3a4f  destructive-dangerous.txt
257f644fa288203f17f29545c5b30c8261b527f0a19ebed5201654280b4b3f32  destructive-benign.txt
