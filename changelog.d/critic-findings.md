### Added
- `idea-critic` verdicts take optional `findings: [{text, class, quote}]` (class: real, misread, accepted-cost, noise; quote at least 12 characters). An independent REVISE or HOLD that carries `findings` must include a `real` one. `validate_verdict.py --artifact FILE` also requires each quote to occur in the artifact (NFC, whitespace runs collapsed) and makes findings mandatory for that REVISE or HOLD. Old verdicts without `findings` validate unchanged. Tests: `scripts/test_critic_findings.py` (registered in `scripts/ci-tests.d/critic-findings.sh`), plus a fabricated-quote fixture in the idea-critic `evals.json`.

size-budget-raise: .claude/skills/idea-critic/SKILL.md 15575→15943 documents the optional findings schema and the --artifact validate usage
