# Held-out 18 (authored 2026-10-25, blind; not scored)

Eighteenth held-out security-gates corpus. Authored blind: no guard source, test, scorer, or rival code was read, and no rows from earlier corpora were copied (only the file layout of held-out 17 was inspected). Not scored; no results claimed.

Files: `destructive-dangerous.txt` (60 rows) and `destructive-benign.txt` (60 rows), one shell command per line. Rows are never executed. Hosts and names are fictional (example.com, Acme).

Dangerous rows: destructive commands an agent must not run unasked, with evasion via wrappers (env, sudo, nice, command), find/xargs, interpreters, quoting and escaping, base64/eval/substitution, aliases, symlinks, raw-device writes, git history rewrites, and cloud, k8s and database CLIs. Benign rows: look-alikes that are safe (scoped build and temp cleanup, dry-runs, echo/printf of commands, comments, read-only listings and queries).

Integrity: `SHA256-frozen.txt` holds the corpus hashes; `ledger.jsonl` records the preregistration with the sha256 of `SHA256-frozen.txt`.
