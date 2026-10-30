### Added
- `veche.py --json-out PATH` also writes the JSON record to PATH, for decided, `COULD_NOT_DECIDE` and `NOT_CONVENED` records alike. The file is opened before any seat is called, so a bad path exits 2 with a `--json-out: cannot write` message and costs nothing (#2139).

### Fixed
- `veche.py`: when the stakes gate skips the council, stderr now says so (`veche: NOT_CONVENED, no seat called (...)`) and adds `; --twin ignored` when `--twin` was given, so the skipped twin is no longer silent (#2139).
- `council.md` documents `--json-out`, `--progress-s`, the in-flight `--alarm-s`, the `--option` token rule, `verdict_basis` and the `dropped` and `cost` keys of a failure record.
- size-budget-raise: .claude/skills/idea-critic/references/council.md 8433→8934 documents the veche.py flags --json-out and --progress-s, the in-flight --alarm-s, the --option token rule, verdict_basis and the failure record's dropped and cost
