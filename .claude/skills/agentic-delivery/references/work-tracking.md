# Keeping a work tracker current

Read this when: a repo uses a work tracker (Linear first-class; GitHub Issues or Jira the same shape), you open or
merge a PR that closes tracked work, you set up `install.sh --tracker-project`, or you draft a weekly project update.
Core rules are tracker-agnostic; the Linear section holds only product-specific gotchas.

## Object mapping

| Concept | Tracker object | Rule |
|---|---|---|
| Product or workstream | Project | One project per product or workstream, not per sprint. |
| Deliverable | Issue | An outcome someone can verify. A chore ("bump deps", "rerun CI") is a checklist line in the PR, not an issue. |
| Slice of a deliverable | Sub-issue | Use when one PR cannot finish the parent. |
| Dependency | blocks / blocked-by relation | Never prose in a description; a relation is queryable, prose is not. |
| Urgency | Priority | Set on every issue; "No priority" is a finding. |
| Objective (OKR) | Initiative linked to the project | The project reports up to it; do not duplicate the objective text per issue. |
| Accountable person | Project lead (DRI) | One name. Working-group members are project members. |

## Status moves (three, no more)

1. **Start**: assignee set and status In Progress when work begins.
2. **PR open**: status In Review; the PR links the issue.
3. **Merge confirmed**: Done only after the merge is confirmed on the default branch, not at PR open or review approval.

Anything else is noise. An issue In Progress with no update for 14 days is stale: move it, split it, or close it.

## Weekly project update

Post one update per project per milestone, not on a schedule, in the structure from `communication-structure`
(`references/leadership-status-update.md`; no PR numbers, no promises). `scripts/tracker_weekly_update.py` drafts raw
material from the last 7 days of merged and open PRs and never posts; rewrite it into that structure before a human or
agent posts it through the tracker UI or MCP. Health is a suggestion: the DRI decides, and only a person calls Off track.

## Hygiene check

`scripts/tracker_check.py` reads open and recently merged PRs through `gh` and flags: PRs with no tracker ID, and
revert or partial PRs whose title carries an ID (auto-close hazard below). With `LINEAR_API_KEY` (read-only, never
logged) and a project ID it also lists open issues missing assignee, priority or status, and stale In Progress issues.
A missing `gh` or key prints a `NOT CHECKED` line and exits 0: absence of a check is not a pass. Text by default,
`--json` for loops. Run both scripts from the coordinator loop (`templates/loops/coordinator.md`).

## Linear gotchas (verified in the field, 2026-10-07)

- **The GitHub integration auto-closes an issue when a PR whose title carries its ID merges.** Put the ID in the
  title of only the PR that completes the issue. Slices, reverts, partial work and every member of a merge train
  carry `Refs ACME-123` in the body instead; the title stays ID-free.
- **`#NNN` in Linear text autolinks to a guessed repository.** Write `repo PR 456`, never `#456`, in issue
  descriptions, comments and project updates.
- **Priority may be owned by a portfolio owner.** Set the issue's priority; leave the project's priority alone unless
  you are that owner.

## Install

`./install.sh --tracker-project ACME-PROJECT [--tracker linear|github|jira]` writes a marker-delimited "Work
tracking" block (at most 12 lines) into the target `AGENTS.md`, idempotently, and records the flag so
`scripts/update-installed.sh` replays it. The install is owner-run, so the instruction-file change goes through the
owner; an agent never edits `AGENTS.md` to add tracking on its own.

- **A pipeline, CI, train or hook fix, or one merged behind a default-off flag, closes only on production evidence.** Label the issue `verify:prod`, write `Refs #N` (never `Fixes #N`), add an enforce-flip checklist for a flagged fix (shadow line seen in 2 runs, or a replay against past logs showing the decisions it would have made; flip PR), and close after 2 production runs, each linked as a `production run: <log url>` line; `lane_guard.py shadow-fix --base <ref> --body-file <f>` refuses the closer otherwise.
