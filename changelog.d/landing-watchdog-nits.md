### Changed
- `landing_watchdog.py`: the per-session stall-line stamp now re-shows after 15 minutes instead of an hour (a compaction that dropped the ~103-byte line recovers sooner), and a `session_id` containing NUL (a `ValueError` from `open`) no longer loses the line; it is returned like any other stamp I/O error. `agentic-ceo` SKILL.md's delivery-ref fallback now reads as `agentic-delivery`'s does: "else read its `INDEX.md` and open only matching rows".

size-budget-raise: .claude/skills/agentic-ceo/SKILL.md 15729→15742 ceo delivery-ref fallback now says "open only matching rows" as delivery does; no existing rule to extend
