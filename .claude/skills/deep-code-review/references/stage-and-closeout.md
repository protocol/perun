# Project stage, review closeout and optional overlays

Read this when you set `STAGE` on a FULL review, write the going-forward roadmap, close a review against its definition of done (a), or recommend or install an overlay. A small DIFF on the quick path does not need it; `SKILL.md` keeps the one stage rule that never relaxes and the ship-ready checklist (b).

## Project stage (calibrates urgency, not severity)

Context still counts: a two-day **prototype** and a production system do not
warrant the same *demands*. Stage calibrates **what blocks now vs. what is
tracked for the next stage** — it never rewrites what a defect is. Set it in the
first-response block; it shapes the going-forward roadmap (`report-format.md`).

| Stage | What it is | Relax the *demand* on (urgency, not severity) |
|---|---|---|
| `prototype` | Throwaway spike / experiment; learning over durability | CI depth, full coverage, perf tuning, docs, tech-debt paydown |
| `mvp` | First real shippable; finding product fit; keep it lean | scale/perf headroom, exhaustive tests, polish |
| `growth` | Real users, scaling up | little — this is where CI, tests, observability, perf get hardened |
| `mature` | Stable / maintenance | net-new scope; focus shifts to stability, tech-debt, supply chain |

**Guardrails — a stage is a lens, never an excuse:**
1. **Declared or evidenced, never guessed.** Stage is owner-stated, or the review
   **names the signals** it read (tests/CI present, deploy config, users/traffic,
   version ≥ 1.0, changelog depth) and marks it `UNVERIFIED` when it cannot.
   **Unstated → default to the stricter (later-stage) reading.** A review that
   assumed `prototype` and waved a Critical is a worse failure than one that
   over-asked for CI on a spike.
2. **Security, secret-exposure, and data-loss/integrity findings never relax**
   (the rule itself stays in `SKILL.md`, always loaded). They have no "relax"
   entry at any stage; that is why the third column above omits them on purpose.
3. **Stage moves urgency, not intrinsic severity.** Every finding keeps its true
   severity — reuse the latent-findings rule (intrinsic severity stays; stage
   changes only what *blocks now*). The going-forward roadmap sequences findings
   by stage-urgency; it does not downgrade them.

**Stage-evolution lenses (when to add, not how to secure).** When the going-forward
roadmap must say how a project's infrastructure/architecture or documentation should
*evolve* for its stage — **read** `infra-evolution-by-stage.md` (infra,
deploy, and architecture earned per stage, each step gated on an observable trigger;
the security/backup floor never relaxes) and `docs-evolution-by-stage.md`
(which documents acquire normative force at which stage; trigger-not-calendar). Both
feed the going-forward roadmap in `report-format.md`. The *how-to-secure* depth for
infra/docs already in place stays in `infra-iac-containers.md` (L) and
`docs-and-dx.md` (O) — do not duplicate it here.

## Definition of done (a): review method complete

Checklist (b), target ship-ready, stays in `SKILL.md`. The two fail independently.

- First-response block printed (`SCOPE`, `START_SHA`, `TREE_STATE`,
  `VERIFY_SURFACE` on a web / port / restyle / parity task, `HISTORY_DEPTH`,
  `REVERTS_CHECKED`, `BANNED_REMEDIES`, `ARCHETYPE`, `STAGE`,
  `COVERAGE_LEDGER`); citations re-verified at that ref with a verbatim
  snippet.
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

## Optional overlays (same repository, not default)

This skill is the bar. Sibling skills, installed only on an explicit flag or
an owner yes after a recommendation:

| Skill | Install | Does |
|---|---|---|
| `agentic-delivery` | `--with-delivery` or `--full` | Gated G0–G10 delivery; independent QA/security; one writer per worktree; names this review skill at G1/G6/G7 |
| `idea-critic` | `--with-critic` or `--full` | Pre-owner attack on plans and "we should" (3 hats; HOLD / REVISE / PASS_TO_USER) |

Recommend, don't dump: `./install.sh --recommend <project>` inspects the
target and prints a pack. Default `./install.sh <project>` stays review-only.

`--with-gates` is a **mechanism, not a skill**: it wires this skill's own
gate scripts (`fix_class_gate.py`, `binaries_gate.py`) into the target's own
CI via `scripts/dcr-gates.sh` — **read `docs-and-dx.md`'s
Standards-imprint section when pairing a Phase 6 standard with a mechanized
gate**, not just a doc.

Terse chat voice is **not** vendored here. If a project wants compressed
assistant prose, add [JuliusBrussee/caveman](https://github.com/JuliusBrussee/caveman)
separately. Persisted artifacts (code, PR bodies, docs) stay normal English
either way.

Compose with other packs; do not also run a second delivery OS on the same
repo. This review skill always composes.
