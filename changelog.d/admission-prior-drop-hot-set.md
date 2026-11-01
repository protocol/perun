### Changed
- `.claude/skills/agentic-delivery/references/red-gate-triage.md`, admission section: guidance for a gap in admission scoped to a change's own specs. A PR that a train dropped for a failing spec can return after a fix push that touches other files; the spec is no longer selected, and the PR breaks the next train on the same spec. Admission should also run, on the PR merged onto the base, every spec named in the PR's earlier drop records (so drop records must name the failing spec ids) and a capped hot set of specs that refused two or more PRs in the last seven days; a failure among them is triaged with the same solo re-runs as any train red, and a base-red one is subtracted, never charged to the PR. Not yet implemented in `train_land.sh`, which records no spec ids per drop and selects no hot set.

### Added
- Eval `admission-reruns-prior-drop-and-hot-specs` in `.claude/skills/agentic-delivery/evals/evals.json`.

size-budget-raise: .claude/skills/agentic-delivery/references/red-gate-triage.md 29039→30007 prior-drop and hot-set admission paragraph
