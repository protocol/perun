# Held-out destructive-command corpus 4 (2026-10-25)

Blind, preregistered corpus for scoring a destructive-command guard.

- Blind authorship: written without reading the guard source, the guard tests, or any earlier security-gates bench file. Rows were not tuned to any detector.
- Date: 2026-10-25 (UTC).
- Author: model (Claude Opus 5.5 label per commit trailer), not a human.
- Labels: `destructive-dangerous.txt` rows are labelled dangerous (the guard should block or ask). `destructive-benign.txt` rows are labelled benign (the guard should allow). Format: `id<TAB>cmd`, 60 rows each, ids H4-D01.. and H4-B01...
- Placeholders only (Acme, example.com); no real-format secrets. Commands are data, never to be executed.
- Frozen: hashes in `SHA256-frozen.txt`; `ledger.jsonl` records the preregistration. Do not edit rows after freeze; scoring appends new ledger events only.
