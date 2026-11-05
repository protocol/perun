### Added
- `report_contract_lint.py` rules `missing-route-inventory` (no `## Route inventory` section) and `inventory-no-cite` (an inventory list line without exactly one repo-relative `path:line` that resolves under `--root`). `whole-project-report.md` template gains the section: one line per route, never grouped. An empty inventory fails unless it holds `- none`; a non-list inventory line fails `inventory-not-list`; only a token with a file extension counts as a cite (`host:8080` does not); the rate-limit anchor is reviewer guidance, not a lint rule.
- G6 data/API bench blind set3 record (final FAIL 4/8, burned) and scorer amendments v2.2 (attack/chain subsections are not claims, as in the report lint) and v2.3 (fenced code skipped; only a `Findings` or `Findings (...)` heading opens the section), both logged in the bench ledger before set4. The v2.3 scorer and its tests live in `docs/bench/g6-data-api/scorer-v2/` (the set1-frozen top-level scorers stay at their landed bytes); a `relocated` ledger event records the move, offline set2/set3 parity and recovered scorer snapshots.

### Fixed
- `bad-citation` now also checks unquoted bare `basename.ext:line` cites in prose, which previously passed unchecked when the file lives in a subdirectory.

size-budget-raise: .claude/skills/deep-code-review/references/whole-project-report.md 5593→6651 route inventory template section, its lint rules and reviewer-guidance wording
