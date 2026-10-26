### Added
- `operating_selfcheck.py` now FAILs when the memory index (`MEMORY.md`) is over 150 lines or 20KB (the harness truncates it and the lessons at the tail are lost) and WARNs when the newest owner-facing status stamp (`.perun/last-status-update`, skipped if absent) or the handoff `handoff_inject.py` re-injects is older than 24h. `handoff_inject.py` prefixes a `STALE:` line to a handoff older than 24h. `operating-discipline.md` gains short memory and handoff hygiene doctrine (delete superseded handoffs, rotate long sessions daily, put regression guards at merge or train time).

size-budget-raise: .claude/skills/agentic-delivery/references/operating-discipline.md 10585→11608 memory, handoff and status-update hygiene doctrine plus the resumed-lane tool-call cap note
