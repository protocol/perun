### Added
- deep-code-review: `scripts/finding_verdict.py` validates machine-report gap rows that carry a `verdict`: `confirmed` needs root cause, observed result, remediation, demonstrated impact and a verifier plus final re-check who are not the hunter, and is the only verdict that may carry `severity` (never above the demonstrated impact); `needs_validation` needs blockers and a validation plan; `rejected` needs a reason; unknown fields are errors. `merge_findings.py` applies it, drops failing or rejected rows (`dropped.invalid_verdict`, `dropped.rejected`, `verdict_errors`, present only when nonzero) and lists `needs_validation` rows under their own `needs_validation` key, never ranked. Rows without `verdict` are unchanged.
- deep-code-review: `scripts/coverage_ledger.py` checks the machine-report `coverage` map and fan-out `units`: every assigned domain has a row, partial or not-scanned rows say why, not-applicable rows carry probe and fact, and an incomplete run states `incomplete_reason`. This is the mechanical form of the coverage-ledger step in `method.md`.
- deep-code-review: fresh-verifier rule in `appsec-verify.md` section 1; `security_verify.py` marks a row `confirmed` only when `hunter` and `verifier` are both set and differ (else `needs_validation`).
- deep-code-review: `references/desktop-native-appsec.md` (desktop local IPC, release-binary hardening, updater trust), routed from the archetype table in `full-map.md`.
- docs: the Cloudflare `security-audit-skill` peer recorded by name in `docs/standards-index.md`.

size-budget-raise: .claude/skills/deep-code-review/references/full-map.md 18990→19074 one archetype row routing the desktop reference
size-budget-raise: .claude/skills/deep-code-review/references/full-map-report.md 2018→2171 pointer to the verdict and ledger scripts
size-budget-raise: .claude/skills/deep-code-review/references/appsec-verify.md 6783→7428 fresh-verifier step
size-budget-raise: .claude/skills/deep-code-review/references/machine-report.md 11602→13064 verdict-row and ledger-check rules
