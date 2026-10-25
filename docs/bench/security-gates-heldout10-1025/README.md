# Heldout10 destructive-command corpus (preregistered)

Date: 2026-10-25
Authoring model: Claude Opus 5.5 (blind: authored without reading the guard source, its tests, any security-gates test, or any prior heldout or destructive corpus row or RESULTS file).

Files:
- `destructive-dangerous.txt`: 60 rows (H10-D01..H10-D60), commands a guard should block.
- `destructive-benign.txt`: 60 rows (H10-B01..H10-B60), safe look-alikes a guard should allow.

Rules:
1. Row format is `id<TAB>cmd`, one command per line.
2. Dangerous rows are irreversible or data-destroying and biased toward evasion: variable indirection, inline aliases and functions, subshells, here-strings, quoting tricks, env/sudo/nice/timeout/stdbuf wrappers, find/xargs chains, PowerShell aliases, Windows cmd, and less common tools (rclone, restic, zfs, lvm, wipefs, shred, firebase, supabase, vercel, netlify, pulumi, docker prune, gcloud).
3. Benign rows are near-miss twins: dry-run flags, `--help`, quoted mentions, read-only listings, scoped cleanup under `./build` or `/tmp`.
4. Placeholders only (Acme, example.com); no secret-like strings or real identifiers.
5. Frozen by `SHA256-frozen.txt`; `ledger.jsonl` records the hash of that file. Do not edit rows after preregistration; any change needs a new corpus directory.
6. No scoring was performed at authoring time.
