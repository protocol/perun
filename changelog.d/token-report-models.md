### Added
- `token_report.py` shows each lane's model (majority plus counts) and `meta.json` effort when recorded, totals by model for main and subagents, a main context-per-turn line (average, first-third vs last-third trend, handoff flag above 400k), and a cheaper-route hint when orchestration share exceeds 20%.
- `token_report.py --rates TSV` prices main, subagents and each lane from a user-supplied rate card (no prices ship with the tool; without it cost reads `UNPRICED`); `--top N` sets how many lanes are listed (0 = all).
- Lanes still running (no handback, no `end_turn`) are marked `in-flight` and counted, so mid-session spend is not understated.

### Fixed
- `token_report.py --since`: a timestamp with fractional seconds of other than 3 or 6 digits, or a `+0000` offset, failed to parse on older Pythons and silently dropped its turn, so one window could look empty while a nearby one did not; a zone-less `--since` is now local time, two turns without timestamps no longer crash the sort, and an empty window prints the transcript's time span on stderr.
