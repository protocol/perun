# Held-out 19 (authored 2026-10-25, blind; not scored)

Nineteenth held-out destructive-command-guard corpus. Authored blind: no guard source, test, scorer, or earlier corpus rows were read (only the file layout of held-out 18). Not scored; no results claimed.

Files: `destructive-dangerous.txt` (60 rows) and `destructive-benign.txt` (60 rows), one single-line shell command per line. Rows are never executed. Hosts and names are fictional (example.com, acme).

Dangerous rows: data loss, system damage, credential wipe, force history rewrite, remote infra deletion, disk wipes, with evasion via variables, subshells, base64/eval, aliases, interpreters, xargs/find, rsync --delete, mv of system dirs, wrappers, and cloud, k8s, terraform, docker and database CLIs. Benign rows: look-alikes that are safe (in-tree build cleanup, mktemp cleanup, topic-branch push, named test containers, dry-runs, echo/comments, read-only queries).

Integrity: `SHA256-frozen.txt` holds the corpus hashes; `ledger.jsonl` records the preregistration with the sha256 of `SHA256-frozen.txt`.
