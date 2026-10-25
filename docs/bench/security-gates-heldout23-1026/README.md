# Held-out 23 (authored 2026-10-25, blind; not scored)

Twenty-third held-out destructive-command-guard corpus. Authored blind: no guard source, test, scorer output or other held-out corpus rows were read; only the file layout, README and ledger style of held-out 22. Not scored; no results claimed.

Files: `destructive-dangerous.txt` (60 rows) and `destructive-benign.txt` (60 rows), one single-line shell command per line after a leading `#` header line. Rows are never executed. Hosts and names are fictional (example.com, acme).

Dangerous rows: terraform state and workspace removal, helm uninstall and forced rollback, GCP and Azure deletions, psql/mysql/mongosh/redis data loss, git filter-repo/filter-branch and reflog/mirror/clean history loss, launchctl and systemctl disable/mask, recursive chmod/chown/chattr, truncate and redirect wipes, zfs/btrfs destroy, rclone purge and delete-sync, AWS s3api/rds/dynamodb/kms/iam/ec2/cloudformation deletes, raw-device wipes, and a base64-obfuscated wipe. Benign rows: near-miss twins of the same tools using list, describe, show, dry-run, EXPLAIN, scoped WHERE, temp-path or echo/decode forms.

Integrity: `SHA256-frozen.txt` holds the corpus hashes; `ledger.jsonl` records the preregistration with the sha256 of `SHA256-frozen.txt`.
