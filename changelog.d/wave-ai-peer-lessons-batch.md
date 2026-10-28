### Added
- agentic-delivery: `fitness_tick.py` runs each fix's executable fitness check every operating-loop tick (one-line `ALARM`), and `closable NAME` passes only after 2 consecutive passing ticks and a caller. `flake_holder.py` (pre-push, warn-only) names the open PR that already changes a flaky-test fix's test file. `finding_guard.py` (operating-layer PreToolUse hook) runs the `file_finding.py` dedupe search on every `gh issue create --title` and denies a match (`# finding-force: <reason>` overrides; a failed search fails open).
- agentic-delivery: `wired_check.py` now reports a new script that appears only on an orphan/unused allowlist as `merged-not-wired`.
- agentic-delivery: `baseline_guard.py` stores a test baseline only after solo re-runs, with the host load recorded, and refuses a run far above the normal failure count. `freeze_gate.py` (pre-push) enforces a freeze file: only pure deletions and `Red-Trunk-Fix:` commits pass. `flow_alarm.py` is one symptom alarm (ready work but nothing merged in 2h, or trunk red over 1h), a stop-starting PreToolUse hook that denies `gh pr create` while 5 or more PRs are ready-but-unmerged, and a value-stream split (`split`). `prevention_lint.py` fails a postmortem action item that lacks an owner, tracking id or verifiable end state.

### Changed
- agentic-delivery: `reply_cap.py` skips when a user-level Stop hook already runs a different reply-cap script, so an over-cap reply gets one rewrite demand, not two.
- agentic-delivery: `flake_ledger.py quarantine` takes `--ticket`, flags ticketless entries in `report`, and on a full list (`--max`, default 10) exits 1 and can file a P0 issue (`--file-issue`).
size-budget-raise: .claude/skills/agentic-delivery/references/unattended-operating-mode.md 26739→27923 fitness-check close rule, finding_guard hook, symptom alarm, stop-starting, value-stream split
size-budget-raise: .claude/skills/agentic-delivery/references/red-gate-triage.md 27186→28248 flaky-fix holder rule, baseline guard, quarantine ticket, freeze file
size-budget-raise: .claude/skills/agentic-delivery/references/full-map.md 24381→24488 merged-not-wired allowlist note
size-budget-raise: .claude/skills/agentic-delivery/references/template-postmortem.md 3387→3519 done-when column and prevention lint

size-budget-raise: .claude/skills/agentic-delivery/references/red-gate-triage.md 27616→28678 peer-lessons rows (freeze gate, flow alarm, fitness tick) routed from triage
