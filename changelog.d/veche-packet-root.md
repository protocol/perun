### Fixed
- `veche.py --packet` resolves a relative path from the current directory first, then under `--root`, so a packet kept under `--root` runs from any directory with its citations verified. A packet found in neither place now fails before any seat is called, and the error names both paths tried (it was `internal error: FileNotFoundError`). New test: `scripts/test-veche-packet-root.sh`.
