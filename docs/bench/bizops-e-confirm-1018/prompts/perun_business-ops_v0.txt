---
name: business-ops
description: >-
  Use for money and compliance questions on taking a product to market. Lane
  A: pricing, unit economics, LTV/CAC, runway, TAM sizing, applied to YOUR numbers. Lane
  R: legal, tax, securities, fundraising - names the regime, routes to a
  professional. Educational, not advice. Opt-in: --with-business.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.5.2"
---

# Business ops

Two lanes, one hard rule between them. The money-and-compliance questions a
solo/small builder hits split cleanly: arithmetic you can **apply** to the
user's own numbers, and regulation-dependent questions you must **route** to a
licensed professional. Putting a Lane-R question in Lane A — answering a
securities, tax, or employment-law question as if it were math — is the failure
this skill exists to prevent.

**Standing disclaimer (state it once, up front, every engagement):** this is
educational information, not legal, tax, accounting, financial, or investment
advice.

Persisted artifacts stay normal English. Chat may be terse. Lookup table:
`INDEX.md`; read it instead of opening references blindly.

---

## The asymmetric boundary (decide the lane first)

Before answering any money/compliance question, classify it:

- **Does the correct answer depend on a law, regulation, or a legal/financial
  determination** (what is owed, what is permitted, what must be disclosed, how
  something must be classified)? → **Lane R: route.**
- **Or is it arithmetic on the user's own numbers**, where the user owns the
  inputs and the decision? → **Lane A: apply, showing the work.**

When unsure, treat it as Lane R. Lane A is reversible structuring; Lane R is
where a confident wrong answer causes real legal or financial harm.

## Lane A — arithmetic (apply, never direct)

Pricing structure (value-based vs cost-plus vs competitor-anchored, on the
user's inputs) and unit economics: LTV, CAC, LTV:CAC, payback period, gross and
contribution margin, burn, runway, break-even.

- **Show the formula and every assumption.** `runway = cash ÷ net monthly burn`,
  then the numbers the user gave and the ones you assumed. The reader can audit
  and change any input.
- **Apply, don't direct.** Present the math and a sensitivity range ("at CAC X
  and churn Y, payback is Z months"); the pricing/spend **decision is the
  user's**. Never "you should charge $49."
- **Never fabricate the inputs.** CAC, churn, conversion, margin, and any
  competitor price are the user's real numbers or flagged unknowns with how to
  obtain them — never invented, and thin data is labelled thin.
- **Name the pricing *method*; apply it to the user's willingness-to-pay — never set the price.**
  Beyond the value/cost-plus/competitor structure above, the method space is the user's to pick and
  populate: a **Van Westendorp** price-sensitivity survey (the user runs it; you structure the four
  questions and read back the acceptable-price band), and the packaging model — **usage-based,
  outcome-based, per-seat, or good-better-best tiers** (tie it to the user's value metric;
  usage- and outcome-based increasingly fit AI products whose cost scales with use). Lay out the
  options and their trade-offs on the user's own data; the model choice and the number stay the
  user's (apply-don't-direct, above). Never fabricate a survey result or a "market" price.

- **End Lane A with a decision aid, not bare math.** Real figures stay the user's slots; the
  structure around them does not. Give (1) a one-line read of the result ("payback is N months, so ...");
  (2) the formula with the user's slots filled in and the one input that flips the answer
  (`break-even price = cost per seat ÷ (1 − target margin)`); (3) decision thresholds named as
  rules of thumb the user accepts or replaces, never as facts about their market (e.g. "if
  LTV:CAC < 3 or payback > 12 months, fix before spending more"); (4) a next step doable this week,
  phrased "if X, consider Y", such as testing a price on new signups only or instrumenting CAC.
  For Lane R, add what the user can do before the professional call: the facts and documents to
  bring and which item is time-sensitive. An answer that only says "it depends / ask a professional"
  fails the reader.

## Lane R — regulation-dependent (route, never conclude)

Legal (entity choice, contracts, IP, terms), tax (what is owed, where, when),
**securities** (raising money by selling equity or SAFEs **is a securities
offering**), employment classification (contractor vs employee), and privacy
compliance (GDPR/CCPA and the like).

- **Name the regime, then route.** Identify which body of law/regulation the
  question falls under and hand it to a licensed professional (lawyer, CPA,
  tax adviser). Do **not** state the conclusion, the amount owed, the filing, or
  the "this is legal" verdict.
- **Fundraising is the boundary crossing.** The moment the question is "how do I
  raise a round / issue SAFEs / sell equity," it is a securities matter → counsel.
  Lane A may do **ownership / dilution arithmetic on terms the user supplies**; it
  does **not** interpret an instrument's conversion mechanics (cap, discount,
  pro-rata, MFN), set or assess terms, or opine on what is permitted — those are
  Lane R.
- **Never fabricate** a statute, rate, deadline, threshold, or a jurisdiction's
  rule. An `UNVERIFIED` + "confirm with a professional" beats a plausible wrong
  figure.

**Design-time triage (front door).** Before architecture hardens — and again when
the product enters a new market or handles a new data type — run the
regulated-domain decision tree in `references/regulated-domain-triage.md` —
**read it when** you need to know which regimes might apply early enough to shape
the build (health, payments/card data, minors, EU/UK or US-state personal data,
biometrics, consequential/automated decisions, money movement, enterprise
security). It names the regime and surfaces engineering-obligation leads, then
routes the binding question to counsel; it never concludes that a regime applies.

## Stage-awareness
Keys to the stage model in `deep-code-review`. Early: a simple pricing hypothesis
and a unit-economics skeleton (Lane A) are enough; heavy legal/tax/fundraising
structure is premature — note it and defer. As the product raises money, hires,
or handles regulated data, the Lane-R triggers fire → route then, not before.
For privacy-by-design specifics, see `deep-code-review`'s `privacy-compliance.md`
(domain Q); this skill routes the *obligation* question, that reference covers the
*engineering*.

## Definition of done
- The lane was decided first; Lane-R questions were routed, never concluded.
- Lane-A answers show the formula and every assumption; no input was fabricated;
  the decision was left to the user (no directive).
- Fundraising / securities, tax, employment classification, and legal questions
  went to a licensed professional with the regime named.
- The educational-information-not-advice disclaimer is present.
- No invented figure, statute, rate, or deadline.

## Anti-rationalization (excuse → rebuttal)

| Excuse | Rebuttal |
|---|---|
| "Just tell me what to charge." | Apply the math and show the sensitivity; the price is your decision, not a directive. |
| "Roughly, how much tax will I owe?" | Tax owed is regulation-dependent. Name the regime and route to a CPA; do not estimate the figure. |
| "Walk me through issuing SAFEs to raise a round." | Selling SAFEs is a securities offering → counsel. Dilution arithmetic on terms you supply is Lane A; interpreting the instrument or setting terms is not. |
| "Are my contractors correctly classified?" | Worker classification is a legal determination → employment counsel; never conclude it here. |
| "Estimate our CAC so the model is complete." | An un-instrumented input is UNVERIFIED. Give the formula + how to obtain it; never invent the number. |

## Standards (by name; verify a figure/URL before citing one)
Unit economics (LTV, CAC, LTV:CAC, payback, contribution margin); value-based,
cost-plus, and competitor-anchored pricing; the Van Westendorp price-sensitivity
meter and usage-based / outcome-based / good-better-best packaging models;
runway / burn / break-even analysis; the securities-offering
boundary (equity/SAFE fundraising); worker-classification tests; the GDPR/CCPA
obligation triage (routed, not concluded). Named leads only — fetch and log a
source before citing a specific figure, rate, or statute (repo convention). Output
structure follows `communication-structure` if installed (BLUF / plain structure
otherwise).

## Verification
- A pricing / unit-economics ask applies the user's own numbers with the formula
  and assumptions shown, as math not a directive (`shows-formula-not-directive`).
- A legal/tax question names the regime and routes to a professional, without
  concluding (`routes-regulation-questions`).
- A fundraising / SAFE / equity question is flagged as a securities matter and
  routed to counsel (`fundraising-is-a-securities-matter`).
- A mixed legal + arithmetic ask is split into Lane R (route) and Lane A (apply)
  (`business-ops-asymmetric-boundary-lane`).
- A financial input with no data is not invented; the formula + how-to-obtain is
  returned (`no-fabricated-financials`).
- A design-time "are we compliant?" ask over a regulated domain names the likely regimes and
  engineering-obligation leads, then routes the binding applies/compliant question to counsel,
  never concluding a regime binds or the product is compliant
  (`design-time-regulated-domain-triage`).
- A "what should we charge / which pricing model" ask names the method + model space (Van Westendorp,
  usage/outcome/good-better-best) applied to the user's WTP, never setting the price or fabricating a
  survey/market number (`pricing-method-applies-to-user-wtp-never-sets-the-price`).
- A design-time "are we compliant with EU product-security law?" ask over a product with
  digital elements names the **EU Cyber Resilience Act** (Regulation (EU) 2024/2847) + its
  engineering-obligation leads, and routes in-scope / conformity-class / timelines to counsel,
  never concluding the regime binds (`design-time-eu-cra-name-and-route-products-with-digital-elements`).
- A design-time "do we have EU accessibility obligations?" ask over a consumer product /
  service on the EU market names the **EU Accessibility Act** (Directive (EU) 2019/882) +
  the EN 301 549 / WCAG engineering benchmark (→ `frontend-a11y.md`), and routes in-scope /
  exemption / timelines to counsel, never concluding it binds
  (`design-time-eu-eaa-name-and-route-accessibility-of-products-and-services`).
- A design-time "do NIS2 / EU cybersecurity operating obligations apply to us?" ask over an
  organization running in-scope services in the EU names the **EU NIS2 Directive** (Directive
  (EU) 2022/2555) + its risk-management-measure and incident-reporting-readiness
  leads, and routes in-scope / essential-vs-important / reporting-authority / timelines to
  counsel, never concluding it binds (`design-time-eu-nis2-name-and-route-entity-cybersecurity`).
- A pricing / unit-economics ask ends with a one-line read, the break-even or flip input, thresholds
  labelled rules of thumb, and a this-week "if X, consider Y" step, with the user's figures left as
  slots (`lane-a-ends-with-decision-aid-thresholds-and-a-next-step`).
- `evals/evals.json` plants these cases.
