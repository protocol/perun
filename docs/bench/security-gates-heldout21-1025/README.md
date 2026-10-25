# Held-out 21 (authored 2026-10-25, blind; not scored)

Twenty-first held-out destructive-command-guard corpus. Authored blind: no guard source, test, or scorer output was read; only the file layout of held-out 19 and the rows of held-out 20 (to avoid duplicates). Not scored; no results claimed.

Files: `destructive-dangerous.txt` (60 rows) and `destructive-benign.txt` (59 rows), one single-line shell command per line after a leading `#` header line. Rows are never executed. Hosts and names are fictional (example.com, acme).

Dangerous rows: home and system wipes, quoting/variable/env/sudo/command/backslash obfuscation, xargs and find -exec, rsync --delete, moves of system dirs, disk, LVM, ZFS, RAID and LUKS destruction, force pushes and refspec deletes, k8s, terraform, docker, database, cloud CLI and gh deletions, forced power-off, sysrq, crontab wipe, and interpreter wrappers (python, php, bash -c). Benign rows: daily look-alikes such as in-tree cleanup, dry runs, read-only inspection, topic-branch pushes, dumps, and echo/grep of dangerous strings.

Integrity: `SHA256-frozen.txt` holds the corpus hashes; `ledger.jsonl` records the preregistration with the sha256 of `SHA256-frozen.txt`.
