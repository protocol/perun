### Added
- `install.sh --apply-operating-layer` now sets `autoCompactWindow: 200000` in `.claude/settings.local.json`, but only when no user, project or local settings file already sets it; policy `auto_compact: off` (`--policy auto_compact=off`) opts out, and uninstall removes only the value install added.
- New SessionStart hook `handoff_inject.py` (matchers `compact|startup|clear`) re-injects the newest `.claude/handoff*.md` after a compaction, at most 2KB, nothing when absent. Stdlib only, fails open. Tests: `scripts/test-auto-context-reset.sh`. Measured: 2048 bytes injected at most and about 32 ms per run (python3 start-up included); no token saving was measured, so none is claimed.

### Changed
- `context_nudge.py` no longer suggests the owner start a fresh session: it tells the agent to write `.claude/handoff.md` and not to ask for a restart. `references/operating-discipline.md` documents that auto-compact plus re-inject replaces "restart the session" (a session cannot `/clear` itself).
