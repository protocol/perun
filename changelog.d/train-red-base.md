### Added
- `merge_train.py` verify and merge refuse a red base (`REFUSED red-base`) unless the lineup head is the `--base-fix` PR, and merge re-reads the open queue when it fires. Test: `merge_train.py --selftest`.
- `cost-quality-guardrails.md`: a new or changed admission/throughput gate ships log-only for 2 runs before enforcing.

size-budget-raise: .claude/skills/agentic-delivery/references/cost-quality-guardrails.md 15839→16119 one-rule gate-rollout line
