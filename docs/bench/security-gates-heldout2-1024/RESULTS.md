# Held-out 2 results, 2026-10-24

**BLUF.** On a second blind corpus that Perun's rules never saw, the secret gate found 23 of 40 leaks (2 of 40 decoys flagged) and the destructive guard blocked 37 of 50 dangerous commands (4 of 50 benign blocked). Ported gitleaks found 26 of 40 leaks (0 FP). Ported claude-code-safety-net blocked 18 of 50 (2 FP) and ported hooks-mastery 9 of 50 (5 FP). Out of sample, Perun still trails gitleaks on secrets and leads on destructive blocking. The in-sample numbers for the first corpus (30/31, 46/46) and for held-out-1024 after its fixes (30/30, 40/40) overstate what an unseen corpus gives.

**Method.** The corpora were committed (8abdefc93) before any rule wave scored them; `SHA256-frozen.txt` pins them and `ledger.jsonl` records the preregistration. Perun's rules were frozen at the gatefix2 commit; nothing was tuned after seeing these rows. The corpus freeze (8abdefc93) predates the rule change that closed the held-out-1024 misses, so the published numbers are the frozen-rule scores. Later hardening of the guard (a bounded base64-exec pattern, `kubectl delete` option-value skipping, no nested-substitution fan-out) leaves them unchanged: re-scored 23/40 leaks (2/40 decoys flagged) and 37/50 blocked (4/50 benign blocked). Run: `python3 docs/bench/security-gates-1024/score.py --corpus-dir docs/bench/security-gates-heldout2-1024` and `python3 -I docs/bench/security-gates-1024/rivals/score_rivals.py --corpus-dir docs/bench/security-gates-heldout2-1024`. Pins: `scripts/test_security_gates_heldout2.py`.

| System | Secret leaks found (40) | Decoys flagged (40) | Dangerous blocked (50) | Benign blocked (50) |
|---|---|---|---|---|
| Perun | 23 | 2 | 37 | 4 |
| gitleaks v8.30.1 (ported) | 26 | 0 | n/a | n/a |
| hooks-mastery (ported) | n/a | n/a | 9 | 5 |
| claude-code-safety-net (ported subset, 1 row unported) | n/a | n/a | 18 | 2 |

**Caveats.** Same-model-family author as Perun's rule writers, so shared blind spots can flatter Perun; rival systems are Python ports, not their binaries (ported-rule fidelity is the main threat); n is small, so a few rows are noise. Some fixtures may be off the provider's real format, which would penalize strict format rules; this was not audited row by row. Decoy flags: the public AWS documentation key (arguably a correct flag) and a 32-character `x` placeholder under `api_key`. Benign flags: `rm -rf /tmp/acme-demo-cache`, `find . -name '*.pyc' -delete`, `mkfs.ext4 ./test.img` and `git push --dry-run --force origin main`, all scoped or dry-run forms a strict guard may reasonably refuse.

## Leads (misses, not fixed here)

Known gaps, not in this corpus and not fixed: `redis-cli` fed `FLUSHALL` on stdin, and `aws s3 sync --delete`.

- Secret gate missed 17: AWS secret key, GitHub and npm tokens, a CircleCI PAT, a Telegram bot token, Stripe webhook secret, PayPal, Square, Replicate, Groq, credentialed Postgres, MongoDB, Redis and JDBC URLs, a New Relic key and a Sentry DSN. Gitleaks missed 14 (it catches 10 of Perun's 17 misses; Perun catches 7 of its 14; 7 are missed by both).
- Destructive guard missed 13: `eval` of an echoed command, `> /etc/passwd`, `git filter-branch --force`, bare SQL statements (`DROP DATABASE`, `DROP TABLE`, `TRUNCATE`, `DELETE FROM` typed without a client), `gcloud sql instances delete`, `kubectl delete pods --all --all-namespaces`, `kubectl delete pv --all`, `helm uninstall`, `terragrunt run-all destroy` and a printf-built `rm -rf /`.

## Addendum, 2026-10-25: the secret gate is now a union

The privacy gate now also runs the gitleaks default rules (see `docs/bench/security-gates-heldout3-1024/RESULTS.md`). Re-scored on this corpus it finds 33 of 40 leaks (2 of 40 decoys flagged). That 33/40 is partly in-sample: unioning gitleaks was chosen after this corpus showed gitleaks ahead, so it is not an out-of-sample number. The 23/40 above is the banlist alone and stays the out-of-sample figure; the held-out-3 corpus is the out-of-sample test of the union.
