### Added
- `review_status.py` posts a review verdict as commit status `perun/review` on the exact PR head SHA (success for 0 red, failure otherwise; `--dry-run` supported), and `land_ready.py` is a read-only sweep that prints one line per open PR: ready, or the reasons it is not (draft, conflict, behind, checks, missing or failed `perun/review` on the current head). The train can now read review verdicts without a human relay.
size-budget-raise: .claude/skills/agentic-delivery/SKILL.md 7006→7134 route the new land_ready.py and review_status.py scripts from the existing task row
