### Changed
- `scripts/bench_check.py` also accepts the ledger event name `prereg_frozen` and the hash key `sha` for the preregistration line. Two benches recorded before the gate existed used those names. Their hashes match `SHA256-frozen.txt` exactly, so the ledgers are truthful and stay unedited. The hash must still prefix-match the frozen list and precede the first generation event.
