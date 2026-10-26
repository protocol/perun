# Held-out 24 (authored 2026-10-26, blind; not scored)

Twenty-fourth held-out destructive-command-guard corpus. Authored blind, without reading the destructive guard: no guard source, test, scorer output, rival port, score file or other corpus was read; only the held-out-23 README, ledger and layout (first rows of each file) were consulted. Not scored; no results claimed.

Files: `destructive-dangerous.txt` (60 rows) and `destructive-benign.txt` (60 rows), one single-line shell command per line after a leading `#` header line. Rows are never executed. Hosts and names are fictional (example.com, acme). Benign row N is the near-miss twin of dangerous row N.

Dangerous rows: package-manager removal of system packages (apt, dnf, yum, brew, rpm, pip), database CLIs beyond psql/mysql (cqlsh, influx, clickhouse, sqlcmd, cockroach, Elasticsearch REST, cypher-shell), k8s and cloud CLIs (kubectl, oc, eksctl, gcloud GKE, doctl, flyctl, heroku, vercel), disk and partition tools (parted, sgdisk, wipefs, mkfs, cryptsetup, blkdiscard, diskutil, lvremove), git remote and history ops, container and registry deletes (docker, skopeo, crane, gh), IaC (pulumi, cdk), backup deletion (restic, borg, velero, tmutil), permission and account wipes (setfacl, chmod, passwd, chown), and obfuscated forms (base64 eval, variable-held command, split quoting, command substitution, ssh-wrapped dd, python rmtree). Benign rows: list, describe, dry-run, test, print, no-act, inspect or preview twins.

Integrity: `SHA256-frozen.txt` holds the corpus hashes; `ledger.jsonl` records the preregistration with the sha256 of `SHA256-frozen.txt`.
