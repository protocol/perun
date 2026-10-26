# Held-out 25 (authored 2026-10-26, blind; not scored)

Twenty-fifth held-out destructive-command-guard corpus. Authored blind: no guard source, test, scorer output, or earlier corpus rows were read; only the file layout, README, ledger and hash-file format of held-out 21 (held-out 22 was not present on origin/main). Not scored; no results claimed.

Files: `destructive-dangerous.txt` (60 rows) and `destructive-benign.txt` (60 rows), one single-line shell command per line after a leading `#` header line. Rows are never executed. Hosts and names are fictional (example.com, acme).

Dangerous rows: home and system wipes, env-prefix/sudo/subshell/command-substitution forms, find -delete and -exec shred, disk, LVM, ZFS, RAID and LUKS destruction, permission and ownership blasts, credential deletion, root lockout (passwd -l, sshd and firewall lockouts), forced power-off and sysrq, crontab wipe, force pushes, ref deletes and history rewrites, npm unpublish, gh deletions, docker, k8s, terraform, pulumi, restic, aws, gcloud, az and database drops or flushes. Benign rows: look-alikes such as in-tree cleanup, scoped temp paths, dry runs, read-only inspection, topic-branch pushes, dumps, and echo of a dangerous string.

Integrity: `SHA256-frozen.txt` holds the row-file hashes; `ledger.jsonl` records one preregistration event with the sha256 of each row file and of `SHA256-frozen.txt`.
