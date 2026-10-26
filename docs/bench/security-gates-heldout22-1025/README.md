# Held-out 22 (authored 2026-10-25, blind; not scored)

Twenty-second held-out destructive-command-guard corpus. Authored blind: no guard source, test, or scorer output was read; only the file layout, README and ledger style of held-out 21 (plus its rows, to avoid duplicates). Not scored; no results claimed.

Files: `destructive-dangerous.txt` (60 rows) and `destructive-benign.txt` (60 rows), one single-line shell command per line after a leading `#` header line. Rows are never executed. Hosts and names are fictional (example.com, acme).

Dangerous rows: helm, kubectl, etcd, pulumi and ansible teardown, Azure, GCP, AWS, DigitalOcean, Heroku and Fly deletions, vault, Elasticsearch, Cassandra, SQL and Redis/Mongo data loss, destructive git history and ref operations, package-manager removals and unpublish, and base64/printf obfuscated wipes. Benign rows: near-miss twins of the same tools using read-only, scoped, dry-run or single-resource forms, and echo/decode of dangerous strings.

Integrity: `SHA256-frozen.txt` holds the corpus hashes; `ledger.jsonl` records the preregistration with the sha256 of `SHA256-frozen.txt`.
