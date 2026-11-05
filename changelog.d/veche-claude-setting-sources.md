### Changed
- `veche.py` hints at `--setting-sources project` when a `claude` seat returns a malformed reply without that flag (a user Stop hook can rewrite the reply); `council.md` shows the flag in its `claude -p` example. Tests in `scripts/test_veche_claude_hint.py`.

size-budget-raise: .claude/skills/idea-critic/references/council.md 9516→9752 one sentence and one flag on the claude -p seat example
