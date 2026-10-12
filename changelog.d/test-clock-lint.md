### Added
- agentic-delivery: `clock_lint.py [--base REF] [FILES]` flags tests that read the real clock (`Date.now()`, `datetime.now()`, `time.time()`, `time.Now()`, shell `date`) in files with no fake-clock marker, as `file:line: real clock in test; pin a fake clock or inject now`; exit 1 on findings, 2 and `COULD_NOT_CHECK` on an unreadable file, `clock-lint: allow` as the per-line escape. Doctrine: the future-clock run in `verification-handback.md` **Done means verified**; review lens in `testing-situational.md`.

size-budget-raise: .claude/skills/agentic-delivery/references/verification-handback.md 58477→59102 future-clock run bullet
size-budget-raise: .claude/skills/deep-code-review/references/testing-situational.md 40032→40355 real-clock review lens sentence
