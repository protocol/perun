# Heldout11 destructive-command corpus (preregistered)

Date: 2026-10-25
Authoring model: Claude Opus 5.5 (blind: authored without reading the guard source, its tests, any scoring script, or any existing corpus rows or results; only the heldout8 README and a 3-line format sample were read).

Files:
- `destructive-dangerous.txt`: 60 rows (H11-D01..H11-D60), commands a guard should block.
- `destructive-benign.txt`: 60 rows (H11-B01..H11-B60), safe look-alikes a guard should allow.

Rules:
1. Row format is `id<TAB>cmd`, one command per line.
2. Dangerous rows destroy data, systems, infra, history or credentials: coreutils and disk tools, package managers, git/hg, containers and Kubernetes, aws/gcloud/az CLIs, IaC, database CLIs, Windows/PowerShell/macOS, and obfuscation (eval, base64, variables, wrappers, aliases).
3. Benign rows are hard near-misses: scoped or temp/build-dir deletes, dry-runs, read-only flags, list/describe calls, quoted mentions.
4. Placeholders only (acme, example.com); no real identifiers or real-format secrets.
5. Frozen by `SHA256-frozen.txt`; `ledger.jsonl` records the preregistration. Do not edit rows after preregistration; any change needs a new corpus directory.
6. No scoring was performed at authoring time.
