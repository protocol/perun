# Heldout7 destructive-command corpus (preregistered)

Date: 2026-10-25
Authoring model: Claude Opus 5.5 (blind: authored without reading the guard source, its tests, or any prior security-gates bench file).

Files:
- `destructive-dangerous.txt`: 60 rows (H7-D01..H7-D60), commands a guard should block.
- `destructive-benign.txt`: 60 rows (H7-B01..H7-B60), safe look-alikes a guard should allow.

Rules:
1. Row format is `id<TAB>cmd`, one command per line.
2. Dangerous rows are irreversible or data-destroying: container and remote passthrough, system-file append/overwrite, nested substitution and decoders, git history and remote destruction, DB CLIs, registry and VCS CLIs, secret stores, Windows/PowerShell.
3. Benign rows are tricky look-alikes: read-only exec, dry-run flags, `--help` first, quoted mentions, scoped temp cleanup.
4. Placeholders only (Acme, example.com); no real-format secrets or real identifiers.
5. Frozen by `SHA256-frozen.txt`; `ledger.jsonl` records the hash of that file. Do not edit rows after preregistration; any change needs a new corpus directory.
6. No scoring was performed at authoring time.
