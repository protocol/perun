### Added
- deep-code-review FULL audits: whole-repo lenses (plus writer/reader data shape, identity match, mutation reachability, gate review, metric labels, fix-class re-verify and findings ledger) in `references/full-audit.md` (guard added later, access matrix with secondary read surfaces, external retry/replay, fail-closed switches and readiness) and per-path timeout sums in the entry-point table; `references/nextjs-app-router.md` gains per-page server-action serialization and non-void action returns. Default single-pass review text unchanged.
- agentic-delivery: QA on a fresh database per branch (`verification-handback.md`).

size-budget-raise: .claude/skills/deep-code-review/references/full-audit.md 2290→4172 FULL-audit lenses
size-budget-raise: .claude/skills/deep-code-review/references/nextjs-app-router.md 1391→2111 server-action footguns
size-budget-raise: .claude/skills/agentic-delivery/references/verification-handback.md 58477→58759 fresh DB QA rule
size-budget-raise: .claude/skills/deep-code-review/references/full-audit.md 4172→    6000 data-shape, identity, mutation, gate, ledger lenses
size-budget-raise: .claude/skills/deep-code-review/references/full-audit.md 4172→6000 data-shape, identity, mutation, gate, ledger lenses

- deep-code-review: gate-tooling and hook checks in `references/release-engineering.md` (new section: config-env scrub, could-not-check on infra failure or empty evidence, shared cache acceptance rule, import-graph test selection, seeded safety nets, argv over `bash -c`, machine-wide pid-reclaim lock, hooks verify receipts); tightened `merge-operations.md` (could-not-check is neither PASS nor FAIL; carry gated SHA to land) and `testing-ui.md` (name-based locators). Default review text unchanged.

size-budget-raise: .claude/skills/deep-code-review/references/release-engineering.md 27810→30031 gate-tooling and hook checks
size-budget-raise: .claude/skills/deep-code-review/references/merge-operations.md 79273→79433 gated SHA to land, could-not-check wording
size-budget-raise: .claude/skills/deep-code-review/references/testing-ui.md 18016→18054 name-based locator wording
