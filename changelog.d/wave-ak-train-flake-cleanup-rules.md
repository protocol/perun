### Fixed
- agentic-delivery: `train_flake.sh` now removes the flake-store and flake-out temp dirs it creates (EXIT trap over only its own mktemp paths) instead of leaving them for OS cleanup. `scripts/test-train-flake-cleanup.sh` proves none remain.
### Added
- agentic-delivery: short rules in `red-gate-triage.md` (rerun failing titles solo with one worker, 2 of 2 passes is a flake, paired base run before a bisect, AIMD batch window), `retrospective.md` (one pin test per finding in every train, fingerprint duplicate check before filing) and `pipeline-optimizer.md` (each pipeline fix removes a knob or code path).
size-budget-raise: .claude/skills/agentic-delivery/references/red-gate-triage.md 27186→27616 one short rule paragraph added: solo rerun, paired base run, AIMD window
size-budget-raise: .claude/skills/agentic-delivery/references/retrospective.md 4844→5095 one short rule added: pin test per finding, fingerprint dedupe
size-budget-raise: .claude/skills/agentic-delivery/references/pipeline-optimizer.md 19352→19480 one short rule added: deletion budget
