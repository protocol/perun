# Heldout12 destructive-command corpus (preregistered)

Date: 2026-10-25
Authoring model: Claude Opus 5.5 (blind: authored without reading the guard source, its tests, or any prior security-gates bench file).

Files:
- `destructive-dangerous.txt`: 60 rows (H12-D01..H12-D60), commands a guard should block.
- `destructive-benign.txt`: 60 rows (H12-B01..H12-B60), safe look-alikes a guard should allow.

Rules:
1. Row format is `id<TAB>cmd`, one command per line.
2. Dangerous rows are irreversible or data-destroying: coreutils and disk, cloud CLIs, IaC, k8s, DBs, git/hg history, package registries, credentials and keys, Windows/macOS, obfuscation (eval, base64, variables, bash -c, wrappers).
3. Benign rows are tricky look-alikes: destructive words only as data (PR comments, commit messages, echo/printf, grep patterns), reversible GitHub label/assignee removals, scoped temp deletes, dry-runs, read-only and list calls.
4. Placeholders only (Acme, example.com); no real-format secrets or real identifiers.
5. Frozen by `SHA256-frozen.txt`; `ledger.jsonl` records the hash of that file. Do not edit rows after preregistration; any change needs a new corpus directory.
6. No scoring was performed at authoring time.
