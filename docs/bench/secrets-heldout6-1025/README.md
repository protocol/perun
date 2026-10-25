Sixth blind held-out secrets corpus (60 live-format leaks L001-L060, 60 hard decoys D001-D060), authored 2026-10-25 without reading any scanner, gate, banlist, scorer, results file or test; only the heldout-5 files were consulted, for format. Leak values are freshly generated random strings in real vendor formats (cloud, payment, VCS, chat, DB URLs, private keys, JWTs, generic passwords and keys) across code, env, YAML, JSON, shell, CI, Docker, Kubernetes, URL and log contexts; none contains a word like example, dummy, fake, test, sample, placeholder, redacted, changeme or xxx, and none uses a real person or company name. Decoys are look-alikes that are not secrets: env references, hashes, UUIDs, public keys and certificates, test fixtures named as such, and docs prose.

Format: `id<TAB>text`; a literal backslash-n inside a row means a newline.

GitHub push protection note: rows whose token shape GitHub would match (Stripe, AWS, GitHub, Slack, Google, and other vendor-prefixed tokens, including a few decoys) carry a literal `@@` inside the token body. Scorers must treat `@@` as part of the row text. Leak values are random, so none is a valid credential.

Frozen by SHA256 (`SHA256-frozen.txt`) and preregistered in `ledger.jsonl` before any scoring; not scored at authoring time.

Blind at authoring (2026-10-25); in-sample after the wave 3 rule tuning, so any score on this corpus after that is not out-of-sample.
