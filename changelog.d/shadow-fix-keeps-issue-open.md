### Added
- `lane_guard.py shadow-fix --base REF --body-file FILE` (agentic-delivery): refuses a `Fixes/Closes/Resolves #N` PR body when the diff adds a default-off flag or env default, or touches pipeline/CI/train/hook paths without two distinct `production run: <log url>` lines (also the pass path for a default-off flag), because a fix merged behind a shadow flag has not changed production. The reference now says to use `Refs #N` with an enforce-flip checklist (shadow line seen in 2 runs, flip PR, 2 production runs). Tested in `scripts/test_lane_guard_shadow_fix.py`.

size-budget-raise: .claude/skills/agentic-delivery/references/work-tracking.md 3687→4132 one bullet: default-off and pipeline fixes close on production evidence
