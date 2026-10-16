# Leadership status update

Read this when you write any status update a non-technical leader will read: a tracker project update, an issue
status comment, or an owner hand-off. It is the default structure for those.

## Structure (in this order)

1. **Bottom line.** Timestamp with time zone (any day/month form plus HH:MM plus a zone abbreviation), the outcome, and one number: `12 Oct, 14:30 PT: 20 of 21 requests fixed (was 12, +8).`
2. **What moved.** Only metrics the reader cares about, each as `before → after`; a delta is welcome, not required.
3. **What users can now do.** Only what was verified live in production, in plain value terms, or `Nothing new is live yet.` ("Teams" may replace "users" in the label.)
4. **Health.** One line: On track, At risk or Off track, plus when the next milestone completes.
5. **Slipped.** What slipped and the plain cause, or `none`.
6. **Decision needed.** One A/B line, recommendation first: `Recommended: A (ship now) over B (wait for the redesign). Dana to reply A or B by Tue 2026-10-20.` Write `none` when no decision is needed.
7. **Detail.** One link or file path, last.

Label each section on its own line (`What moved:` and so on) so the linter can find it.

## Rules

- Lines 1-6 carry no PR numbers, branch names or pipeline jargon (CI, pipeline, commits, SHAs).
- No effort counts (PRs, lines, commits, tasks) and no "coming next week" promises; the next milestone is a date in Health.
- Never write "live" or "done" for anything not verified live; use the status vocabulary in `SKILL.md`.
- Post per milestone, not on a schedule. No milestone moved, no post.
- Everything technical goes behind the Detail link.

## Check

`python3 .claude/skills/communication-structure/scripts/comms_lint.py --kind status --file <update.md>` runs the
structure above (`status_update_lint.py`) plus owner, date and budget checks; exit 1 prints each fix. It proves
the shape, not that a number is true: verify each figure against its source before you post.
