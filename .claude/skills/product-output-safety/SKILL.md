---
name: product-output-safety
description: >-
  Use when designing or shipping a feature whose OWN AI outputs or automated
  decisions reach end-users and could harm them: bias, hallucination as fact,
  missing AI disclosure, unsafe high-stakes automation. MAP, MEASURE, MANAGE
  with a human gate; never certifies safe. Opt-in: --with-output-safety.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.3.3"
---

# Product output safety

Governs the harm a product's **own outputs and automated decisions** do to its users: a feature that generates, recommends, ranks, scores or acts on a user's behalf can mislead, exclude or damage them even when the code is correct and secure. Code review and `business-ops` do not cover this axis. Persisted artifacts stay normal English. Lookup table: `INDEX.md`.

## Hard rules

- **MAP first, per feature.** Before an output-facing feature ships, name its harms: bias / unfair outcomes, hallucination surfaced as fact, over-reliance, missing AI disclosure, deceptive patterns, unsafe automation of high-stakes or irreversible actions. For each, record who is affected and the worst realistic case. An empty inventory is not a pass.
- **Never certify.** Do not declare a system "safe", "unbiased", "fair" or "compliant": no test proves it. Red-team, measure, report residual risk, recommend controls; the ship decision is the owner's (`evals/evals.json`: `never-certifies-safe`).
- **Human gate is the floor.** Anything costly or hard to reverse (moving money, deleting data, sending on the user's behalf, high-stakes guidance) is gated behind human review or explicit confirmation by default; full autonomous execution of it is the failure. The floor never relaxes at any stage (`high-stakes-action-gated`).
- **Never fabricate a metric.** A bias, accuracy or hallucination rate that was not measured is `UNVERIFIED`: give the eval to run and how to read it, never an invented "0% bias" or "99.9% accurate". No invented incident rate, benchmark or regulatory threshold (`no-fabricated-harm-metric`).
- **One test row per harm.** Each row names the probe set (known-bad positive control, known-good negative control, sliced by subgroup), the metric, an owner-set pass threshold (zero tolerance only for a gated irreversible action; never invent a "typical" rate) and the stop condition that blocks launch or triggers rollback. Also sweep prompt injection, leakage of other users' data and excess agency. Never a bare "test for bias" (`one-runnable-test-row-per-harm-with-stop-condition`).
- **Legal duty routes out.** Whether an AI disclosure is legally required, whether a decision is regulated, or what a policy must say goes to counsel, and `business-ops` names the regime. Name the EU AI Act, ISO/IEC 42001 and NIST AI RMF, leading with the engineering obligations; timelines are amendment-sensitive: never assert that one binds and never encode a date or version. Recommend disclosure as a control (`routes-legal-disclosure-duty`, `names-and-routes-ai-governance-regimes-never-dates-or-a-binds-verdict`).
- **Confidence is a defined coarse tier**, each tier defined and shown as text plus a cue, never a bare "87%" from the model; offer an override. Keep source reliability and claim corroboration as separate axes (`confidence-as-defined-tier-not-model-number`).
- **Ship a model / data card** (intended use and out-of-scope uses, subgroup performance, limits and known gaps, owner and model version, data composition, provenance and consent). No card is a transparency finding; a card stating an unmeasured metric is `UNVERIFIED`, not a clearance (`ai-feature-ships-with-a-model-and-data-card-no-fabricated-clearance`).
- **Answer inside the stated constraint.** Treat deadline, budget and goal as fixed inputs: lead with a plan that meets them (fallbacks needing no retraining, staged rollout, kill switch, dated steps, an owner each) and state its cost to the goal. A bare "do not ship" never answers the ask.
- **Stage-aware, floors fixed.** Early: a per-feature inventory plus a human gate on the single riskiest action is enough; a full governance program is premature. Name an owner for each shipped output-harm and re-review when the feature, model or data changes.

## Excuse to rebuttal

- "Confirm it's unbiased so we can ship": I don't certify; here are the inventory, red-team and residual risk. The ship call is yours.
- "Just auto-send the payout / deletion": gate it by default.
- "Do we legally have to disclose it's AI?": counsel decides; I recommend it as a control.
- "Give us our hallucination rate": `UNVERIFIED`; here is the eval to run.
- "It's low-stakes, skip it": the gate and no-fabrication floors never relax.

## Escalate: read this when

- `references/full-map.md`: you are writing the harm inventory, the per-harm test plan, the model/data card, the confidence-tier rules, the stage call or the definition of done; or you need the full anti-rationalization table, the standards list (NIST AI RMF, model/data cards, Kent, Admiralty Code) or the verification cases. It holds the full text of every rule above.
- `scripts/output_safety_check.py`: run this when you have the product's output-handling facts as JSON; it checks only rules stated here and SKIPs any input you did not give.
- `evals/evals.json`: you change this skill and need the planted cases (certify ask, auto-action, legal duty, fabricated rate, missing card, regime coverage, bare confidence percentage, one test row per harm).

Output structure follows `communication-structure` if installed.
