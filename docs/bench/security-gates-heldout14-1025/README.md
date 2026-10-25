# Heldout14 destructive-command corpus (preregistered)

Date: 2026-10-25
Authoring model: Claude Sonnet 5.5 (blind: authored without reading the guard source, any test file, any scoring script, RESULTS file, or other heldout directory on disk; only the heldout13 file format was consulted, plus an exact-match dedupe against its rows).

Files:
- `destructive-dangerous.txt`: 60 rows (H14-D01..H14-D60), commands a guard should block.
- `destructive-benign.txt`: 60 rows (H14-B01..H14-B60), safe look-alikes a guard should allow.

Rules:
1. Row format is `id<TAB>cmd`, one command per line.
2. Dangerous rows are irreversible or data-destroying. Coverage: file deletes (including variable expansion, find -exec, xargs), pipes and process substitution into shells, eval, aliases, here-strings, encoded payloads, raw disk and filesystem destruction, git history and working-tree destruction, cloud CLIs (aws, gcloud, az), kubernetes and helm, terraform, docker, database clients, package registries, hosting CLIs, GitHub CLI deletes, credential directories, and Windows/PowerShell/cmd.
3. Benign rows are hard near-miss twins: dry-run and help flags, read-only listings, scoped deletes under `./build` or a temp dir, commit/issue/PR bodies that only quote dangerous text, and grep/echo of dangerous strings.
4. Placeholders only (Acme, example.com); no secret-like strings or real identifiers.
5. Frozen by `SHA256-frozen.txt`; `ledger.jsonl` records the hash of that file. Do not edit rows after preregistration; any change needs a new corpus directory.
6. No scoring was performed and no row was executed at authoring time.
