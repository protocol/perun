# Held-out 16 (authored 2026-10-25, blind; not scored)

Sixteenth held-out security-gates corpus. Authored blind: no guard source, test, scorer, rival code, or other corpus rows were read. Not scored; no results claimed.

Files: `destructive-dangerous.txt` (60 rows) and `destructive-benign.txt` (60 rows), one shell command per line. Rows are never executed. Hosts and names are fictional (example.com, Acme).

Dangerous rows are commands an agent must not run unasked: data loss, host damage, shared-state destruction (rm/find -delete/dd/mkfs, force-push and reset/clean on shared refs, DB drops, cloud/k8s/terraform destroys, recursive chmod/chown on system paths, curl-pipe-shell variants, obfuscation via eval/base64/printf/variables/aliases/xargs, other shells and OSes). Benign rows are hard look-alikes that are safe: in-tree build dirs, dry-runs, --help, quoted mentions, scoped temp cleanups, read-only cloud/k8s/git commands.

Integrity: `SHA256-frozen.txt` holds the corpus hashes; `ledger.jsonl` records the preregistration with the sha256 of `SHA256-frozen.txt`.
