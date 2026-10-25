# Heldout9 destructive-command corpus (preregistered)

Date: 2026-10-25
Authoring model: Claude Opus 5.5 (blind: authored without reading the guard source, its tests, or any prior security-gates bench file).

Files:
- `destructive-dangerous.txt`: 60 rows (H9-D01..H9-D60), commands a guard should block.
- `destructive-benign.txt`: 60 rows (H9-B01..H9-B60), safe look-alikes a guard should allow.

Rules:
1. Row format is `id<TAB>cmd`, one command per line.
2. Dangerous rows are irreversible or data-destroying: cloud CLIs (az, gcloud, aws, terraform), Kubernetes and Helm, database clients, package managers, macOS/Windows/PowerShell, VCS, and wrapper/obfuscation forms.
3. Benign rows are near-miss twins: read-only listings, dry-run flags, `--help`, quoted mentions, scoped temp cleanup.
4. Placeholders only (Acme, example.com); no real-format secrets or real identifiers.
5. Frozen by `SHA256-frozen.txt`; `ledger.jsonl` records the hash of that file. Do not edit rows after preregistration; any change needs a new corpus directory.
6. No scoring was performed at authoring time.
