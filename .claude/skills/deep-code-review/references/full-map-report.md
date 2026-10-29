Read this when writing the Phase 5 report or closing a review (Definition of done (a)). Findings report and the review-method checklist, moved verbatim from `full-map.md`.

# Full map: report and done (a)

## Findings report

Exact templates (machine table, plain-language report, invariants ledger):
`report-format.md` — **read when** writing Phase 5, or when an author disputes a filed finding; the
machine-readable findings file a program consumes (or a `PRIOR`
re-verification) follows `machine-report.md`. Gate and dedupe rows with `scripts/merge_findings.py`. Worked
fictional example: `references/example-review-report.md`.

Default per Phase 5: chat BLUF + full table **out-of-tree**; never paste the
machine table as the first chat bubble. In-repo `code-review/` only on
confirmation and an idle checkout; on a public remote, committed
reports are ID + severity + area only.

---
## Definition of done (a)

**(a) Review method complete**
- First-response block printed in full (`VERIFY_SURFACE` on a web / port /
  restyle / parity task); citations re-verified at that ref with a verbatim
  snippet.
- On a FULL review, `STAGE` is stated (or `UNVERIFIED`, defaulting stricter) and a
  stage-calibrated going-forward roadmap is produced (`report-format.md`); stage
  never downgraded a security, secret, or data-loss finding.
- Every status meets the status rule (evidence surface + strongest reading; a
  UI/parity claim names the URL/branch/sha of the tree under review or is
  **invalid**) in `report-format.md`, screened by
  `scripts/validate_status_claims.py`; every findings claim for a mode (security, perf, a11y, privacy, reliability, correctness, ux) has a `mode: ran (N files)` or `mode: NOT RUN (reason)` entry.
- Gate self-test claimed only when run.
- Coverage ledger reconciled; fan-out units attributed (finder + lead-read);
  incomplete finder = `unverified`.
- Affirmative "Invariants verified to hold" on a fan-out or hardened target.
- Identity Arrival Map printed whenever a gate/middleware change is proposed;
  security/authz changes on their own PR.
- Standards not claimed unless walked.
- `mechanism-unproven` fixes keep the finding open.

Strict verdict rows and the coverage-map completeness check: `scripts/finding_verdict.py`, `scripts/coverage_ledger.py` (rules in `machine-report.md`).
