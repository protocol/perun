# Heldout13 destructive-command corpus (preregistered)

Date: 2026-10-25
Authoring model: Claude Opus 5.5 (blind: authored without reading the guard source, its tests, any security-gates test, or any prior heldout or destructive corpus row or RESULTS file).

Files:
- `destructive-dangerous.txt`: 60 rows (H13-D01..H13-D60), commands a guard should block.
- `destructive-benign.txt`: 60 rows (H13-B01..H13-B60), safe look-alikes a guard should allow.

Rules:
1. Row format is `id<TAB>cmd`, one command per line.
2. Dangerous rows are irreversible or data-destroying. New focus areas: credential/key destruction (cloud CLI creds, ssh-add -D, keychain, gpg, kubeconfig, ssh keys); executed payloads (command substitution or backticks) inside gh/git message arguments; git history destruction variants (reflog expire, filter-branch, force/mirror/delete pushes, update-ref); container/k8s/cloud resource deletes (docker, kubectl, helm, aws, gcloud, az, terraform); DB drops via clients (psql, mysql, mongosh, redis-cli, sqlite3); Windows/PowerShell/cmd.
3. Benign rows are hard near-miss twins: messages that only quote dangerous text (single quotes or plain mention), read-only listings, dry-run flags, and scoped cleanup under `./build`.
4. Placeholders only (Acme, example.com); no secret-like strings or real identifiers.
5. Frozen by `SHA256-frozen.txt`; `ledger.jsonl` records the hash of that file. Do not edit rows after preregistration; any change needs a new corpus directory.
6. No scoring was performed at authoring time.
