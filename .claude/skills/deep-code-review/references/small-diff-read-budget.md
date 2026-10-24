Read this when reviewing a small DIFF (the fast path in SKILL.md), before the first read or command.
Read/output budget for the fast path; it never skips a security check in SKILL.md.

- `git diff --stat -p` is the one patch read; do not re-run it per file.
- For each changed symbol, grep its callers and callees and Read those ranges, plus the context around each hunk, with offset/limit.
- Read a whole file only if it is under ~200 lines.
- Pipe test and CI output through `tail -n 40`.
- No narration between tool calls.
