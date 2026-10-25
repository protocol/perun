# Destructive-command guard, blind held-out corpus 5

Authored 2026-10-25 by Claude Opus 5.5 (blind: the author did not read the guard source, any guard test, or any other security-gates bench file).

Files (60 rows each, `id<TAB>cmd`):
- `destructive-dangerous.txt` (H5-D01..H5-D60): irreversible or data-destroying commands, including obfuscation (encodings, eval, indirection) and danger chained after a safe-looking prefix. Expected verdict: block.
- `destructive-benign.txt` (H5-B01..H5-B60): safe look-alikes (dry-runs, read-only, scoped tmp cleanup, quoted mentions, `--help`). Expected verdict: allow.

Rules:
1. Preregistered: the corpus is frozen by `SHA256-frozen.txt`; `ledger.jsonl` records the hash of that file. Any later edit voids the run.
2. No row may be edited, added or removed after seeing guard results. Mislabels are reported, not fixed in place.
3. Placeholders only (Acme, example.com); no real-format secrets.
4. Nothing here is scored at authoring time. Rows are never executed.
