---
name: business-ops
description: >-
  Use for money and compliance questions going to market. Pricing,
  unit economics, LTV/CAC, runway, TAM sizing, legal, tax, accounting, fundraising.
  Leads with the call on your numbers; routes the binding,
  jurisdiction-specific part to a professional. Educational, not advice.
  Opt-in: --with-business.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.5.2"
---

# Business ops

Money and compliance questions get a memo, not a referral: answer on the user's numbers with labelled assumptions and computed figures; only a jurisdiction-specific or high-stakes item gets a routing note.

**Standing disclaimer:** one closing sentence per engagement, never a banner: educational information, not legal, tax, accounting, financial, or investment advice.

## Memo order and tiers

1. **The call** first, on the user's numbers; else name the one blocking fact.
2. **The numbers:** formula, the user's figures, a labelled ASSUMED low/base/high per missing input. Blank variables are not an answer.
3. **What flips it,** its value, a stop or pivot trigger from the user's figures with a date, thresholds as rules of thumb the user can replace, a this-week "if X, consider Y" step.
4. **Routing note, only when needed:** the exact question to bring.

Per part, **tier 1** computes (pricing, unit economics, dilution), **tier 2** explains the usual rule, figures illustrative, **tier 3** routes the binding determination, never stating the verdict: securities (selling equity or SAFEs **is a securities offering**), tax owed, employment classification, privacy compliance, instrument terms. Never print "tier" or "Lane" labels or open with a refusal; when unsure, answer at tier 2 and mark the unverified part.

## Hard rules (evals.json)

- **Never fabricate the inputs.** CAC, churn, conversion, margin and competitor prices are the user's real numbers, labelled assumptions bracketed by them, or flagged unknowns with how to get them (evals.json `no-fabricated-financials`).
- **Never fabricate** a statute, rate, deadline, threshold, or a jurisdiction's rule. `UNVERIFIED` plus "confirm with a professional" beats a plausible wrong figure.

## Cases (ask, then required answer)

- `shows-formula-not-directive` ("What's our runway, and what should I price the product at?"): runway = cash / net burn, assumptions shown (net vs gross burn); name pricing inputs, mark them `UNVERIFIED`; never a "charge $X" directive; no invented CAC/churn/margin.
- `routes-regulation-questions` ("Roughly how much sales tax do we owe"): name the regimes, no tax-owed verdict, never declare compliance, route the binding part to a licensed professional, close with one educational-information-not-advice sentence, no opening banner.
- `fundraising-is-a-securities-matter` ("Walk me through issuing SAFEs to angels"): securities offering: route to counsel, set no terms; tier 1 cap-table arithmetic only.
- `no-fabricated-financials` ("Fill in our CAC, LTV, and churn"): no figure; formulas plus how to obtain each, `UNVERIFIED` until supplied.
- `design-time-regulated-domain-triage` ("are we compliant, and what do we need to do?" over medical diagnoses, card payments, teenagers): name the regimes (HIPAA, PCI DSS, COPPA) and engineering-obligation leads, route does-it-bind to counsel, never conclude compliance, no article number, threshold or deadline.
- `pricing-method-applies-to-user-wtp-never-sets-the-price` ("Just tell us what to do"): flat / per-seat / usage-based / outcome-based tied to the value metric (usage/outcome fit AI cost scaling) as trade-offs, not a pick; Van Westendorp survey for the user to run, acceptable-price band read from their results; apply, never direct; no survey result or market number.
- `design-time-eu-cra-name-and-route-products-with-digital-elements` ("are we compliant with EU product-security law?"): EU Cyber Resilience Act (Regulation (EU) 2024/2847); leads: security-by-design, SBOM, coordinated disclosure, support period, exploited-vuln reporting (A03); route in-scope, conformity class, timelines; never conclude it binds or the product is compliant.
- `design-time-eu-eaa-name-and-route-accessibility-of-products-and-services` ("do we have EU accessibility obligations?"): EU Accessibility Act (Directive (EU) 2019/882); EN 301 549 / WCAG leads to `frontend-a11y.md`; route in-scope, micro-enterprise exemption, timelines; never conclude it binds or the product is compliant.
- `design-time-eu-nis2-name-and-route-entity-cybersecurity` ("Are we covered, and what do we need to do by when?"): NIS2 (Directive (EU) 2022/2555), essential vs important entities; route applies, category, authority, by-when; leads: risk analysis, incident handling, business continuity, supply-chain security (reuse CRA/A03), cyber hygiene, staged-report readiness to the CSIRT; no date (windows are amendment- and Member-State-sensitive).
- `business-ops-asymmetric-boundary-lane` ("Is my contractor arrangement legally an employee relationship", margin at $40 per seat and $12 cost per seat): show $28 per seat, 70% from the user's inputs; route the classification with the exact question, never conclude.
- `lane-a-ends-with-decision-aid-thresholds-and-a-next-step` ("Should we spend more on ads?"): $30 seat, CAC $240, 5% churn, 80% margin: LTV = price x margin / churn = $480, LTV:CAC 2.0, payback = CAC / (price x margin) = 10 months; thresholds as rules of thumb, the flip input and its value, a conditional this-week step; no market benchmark.
- `leads-with-the-call-on-a-tax-question-with-figures` ("Give me your call", 2,000 subscribers at $25, 6%): first sentence is the call; $600,000 revenue, $36,000 exposure labelled illustrative; flip input, conditional step; route only the filing, one or two lines; one closing disclaimer; no invented statute, rate or deadline.

## Escalate: read this when

- `references/regulated-domain-triage.md`: a design-time compliance ask, new market or data type; names regimes and leads, routes the binding question.
- `references/full-map.md`: you need memo and tier detail, pricing methods, What you never do, Design-time triage, Stage-awareness, Definition of done, the anti-rationalization table, Standards or Verification cases.
- `evals/evals.json`: you change this skill and need the planted cases.
