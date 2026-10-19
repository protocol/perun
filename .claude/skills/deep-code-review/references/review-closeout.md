# Review closeout: stage guardrails and review-method checklist

Read this when STAGE is unstated or contested, the report needs a going-forward roadmap, or a FULL review is about to be declared done. Split from `SKILL.md` so a small-diff review does not load it; the stage table, the never-relax rule and the target ship-ready checklist stay in `SKILL.md`.

## Project stage guardrails (1 and 3; guardrail 2, security never relaxes, is in `SKILL.md`)

1. **Declared or evidenced, never guessed.** Stage is owner-stated, or the review
   **names the signals** it read (tests/CI present, deploy config, users/traffic,
   version ≥ 1.0, changelog depth) and marks it `UNVERIFIED` when it cannot.
   **Unstated → default to the stricter (later-stage) reading.** A review that
   assumed `prototype` and waved a Critical is a worse failure than one that
   over-asked for CI on a spike.
3. **Stage moves urgency, not intrinsic severity.** Every finding keeps its true
   severity — reuse the latent-findings rule (intrinsic severity stays; stage
   changes only what *blocks now*). The going-forward roadmap sequences findings
   by stage-urgency; it does not downgrade them.

**Stage-evolution lenses (when to add, not how to secure).** When the going-forward
roadmap must say how infrastructure/architecture or documentation should *evolve*
for its stage, **read** `infra-evolution-by-stage.md` (each step gated on an observable
trigger; the security/backup floor never relaxes) and `docs-evolution-by-stage.md`
(trigger-not-calendar); both feed the roadmap in
`report-format.md`. How-to-secure: `infra-iac-containers.md` (L), `docs-and-dx.md` (O).

## Definition of done (a): review method complete

Checklist (b), target ship-ready, is in `SKILL.md`; the two fail independently.

- First-response block printed (every field in `SKILL.md`); citations re-verified at
  that ref with a verbatim snippet.
- On a FULL review, `STAGE` is stated (or `UNVERIFIED`, defaulting stricter) and a
  stage-calibrated going-forward roadmap is produced (`report-format.md`); stage
  never downgraded a security, secret, or data-loss finding.
- Every status meets the status rule (evidence surface + strongest reading; a
  UI/parity claim names the URL/branch/sha of the tree under review or is
  **invalid**) in `report-format.md`, screened by
  `scripts/validate_status_claims.py`.
- Gate self-test claimed only when run.
- Coverage ledger reconciled; fan-out units attributed (finder + lead-read);
  incomplete finder = `unverified`.
- Affirmative "Invariants verified to hold" on a fan-out or hardened target.
- Identity Arrival Map printed whenever a gate/middleware change is proposed;
  security/authz changes on their own PR.
- Standards not claimed unless walked.
- `mechanism-unproven` fixes keep the finding open.
