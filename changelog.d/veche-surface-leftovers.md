### Added
- `veche.py`: a decided record carries `kill_criteria_by_lens` (`{lens: text}`), each seat's own kill criterion as worded before near-duplicates collapse, so a reader can see which seat asked for which tripwire. It is additive: `kill_criteria` and `validate_verdict.py` are unchanged, a seat that gave none is left out of the map, and the evil twin's criterion stays in `minority_report.twin` (#2140).

### Changed
- `veche.py --help`: `--option` states the exact name rule (the `TOKEN` pattern, which the refusal for a bad name now quotes too), `--stakes` and `--reversibility` state the real gate (the council is skipped only when stakes are low or medium and reversibility is easy, and either flag alone convenes), and `--json-out` says how the file is written (#2136, #2139).
- `council.md` states the reply contract a custom `--cmd` must meet, as the parser really accepts it: a JSON object with a `verdict` and string-only `claims` items, prose and stray braces around it skipped, the first object with a valid `verdict` wins, and the `scores` map may sit in the verdict object or in any other object (#2137). It also lists `kill_criteria_by_lens` in the output row.

### Fixed
- `veche.py --json-out` writes through a temp file in the same directory and `os.replace`, at the early write and at the final one and on every outcome, so a reader or a crash never sees half a record. A symlinked path keeps pointing at its target, an existing file keeps its mode, a device or FIFO target is written in place, and an unwritable path still exits 2 with the `--json-out: cannot write` message (#2139).
