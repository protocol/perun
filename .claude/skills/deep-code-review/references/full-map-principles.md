Read this when a finding turns on principle 4-6, 10 or 11 (1-3 and 7-9 stay in `full-map.md`), or when setting or reading `STAGE`. Principles 4-6, 10 and 11 and the Project stage model, moved verbatim from `full-map.md`.

# Full map: principles and project stage

## Operating principles 4-6, 10 and 11


4. **Do no harm — net-positive on every axis.** Never fix one axis by
   silently degrading another. Unavoidable trade-off = owner decision.
5. **Respect the existing design.** Defects vs redesigns. Intentional public
   posture needs a **named stating artifact**; drift from it is the finding. A
   choice the owner already made **deliberately and explicitly** (not a default,
   not an oversight) is treated the same as a stated style guide: propose
   against it openly if it's worth challenging, never silently revert it as if
   it were an accident.
6. **Rank ruthlessly.** Severity rubric in `full-map.md`. Never bury a Critical under Nits.
10. **Improve the outcome, not just the code.** For data/ML, judge what the
    code *produces*.
11. **Confidentiality by default — first vs third party.** Fail closed on
    secrets and on **third-party** identifiers. A project's **own
    intended-public identity is not a leak**. Protect everyone else.

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
1. **Declared or evidenced, never guessed.** Owner-stated, or the review
   **names the signals** it read (tests/CI, deploy config, users/traffic,
   version ≥ 1.0, changelog depth) and marks it `UNVERIFIED` when it cannot.
   **Unstated → the stricter (later-stage) reading**: assuming `prototype` and
   waving a Critical is worse than over-asking for CI on a spike.
3. **Stage moves urgency, not intrinsic severity** (the latent-findings rule:
   stage changes only what *blocks now*). The roadmap sequences findings by
   stage-urgency; it never downgrades them.

**Stage-evolution lenses (when to add, not how to secure).** Roadmap "how should
this evolve for its stage": **read** `infra-evolution-by-stage.md` and
`docs-evolution-by-stage.md` (feed `report-format.md`); the security/backup floor never relaxes.
