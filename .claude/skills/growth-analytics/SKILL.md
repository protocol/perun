---
name: growth-analytics
description: >-
  Use when deciding what to measure once building or shipping: North Star
  metric, AARRR funnel (retention first), event taxonomy, A/B reads. Works on
  the user's own analytics; never fabricates benchmarks. Not
  product-discovery. Opt-in overlay: --with-growth.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.1.2"
---

# Growth analytics

Decide what to measure, and read it honestly, once the product is being built or shipped. Kills vanity metrics and invented "good" thresholds. Persisted artifacts stay normal English. See `INDEX.md`.

## Boundary

- vs `product-discovery`: discovery decides whether to build (product-market-fit). This runs the standing measurement afterward.
- vs `deep-code-review`'s `observability.md`: that is system health (logs, SLOs). This is product behaviour.

## Hard rules

- **No fabricated benchmarks.** Never assert "good retention is X%", an average conversion rate or a competitor's numbers. Compare to the user's own baseline and trend. No baseline: `UNVERIFIED`, name what to instrument.
- **No invented metrics.** An uninstrumented metric is `UNVERIFIED`; never estimate it. "How are we doing?" gets the query to run in the user's analytics, not a number.
- **One North Star, customer value.** Rises only when users get real value (core action per week). Reject vanity (cumulative signups, pageviews, downloads); name the input metrics.
- **Read AARRR bottom-up, retention first.** Retention, activation, then acquisition. Flat WAU under rising signups is a retention leak, a leaky bucket; doubling the ad budget amplifies it.
- **Every event answers a named question.** Name, question, properties; never track every click "for later". Cohorts need a stable pseudonymous user id (PII and consent go to `privacy-compliance.md`). Size to stage: prototype almost nothing; mvp core-action activation and retention; growth full funnel; mature guardrails.
- **Experiments: pre-commit, no peeking.** Raise peeking, power or multiple-comparison points only when the requester's own read has that flaw. A day-2 p = 0.03 on a 14-day test, on secondary click-through, is peeking (false-positive rate above the nominal 5%): `UNVERIFIED`, not a win. Require a fixed N or duration read once at the end, or a sequential rule matching the looks (always-valid mSPRT for continuous; group-sequential alpha-spending for a set schedule). Pre-declare a primary and a guardrail metric so a secondary win is not cherry-picked; CUPED may buy power.
- **Asked for a call? Recompute, then decide.** Recompute lift, rates and significance from the stated counts (100 vs 130 conversions of 2,000 per arm is about 30% relative, not 50%) and lead with the figure that does not reconcile. Name confounders in the stated facts (a concurrent email campaign, an outage, novelty, seasonality, mix shift, a lagging guardrail). Give ONE call (ship, extend to the pre-committed N, or stop), not a menu or a request for more data. Derive the stop tripwire from the stated numbers (break-even rate, guardrail floor; number, date, action) at a level the plan does not already trip; an arbitrary round threshold is not a tripwire. Fit the stated deadline (canary, partial rollout, re-run length at stated traffic); say what is salvageable outside contaminated days and what is not.
- **Deliver what was asked first.** Produce the named artifact (the full event list, the plan for the CFO) in the stated format before any caveat; never swap it for a refusal, a smaller list or a lecture. Leave a reserved decision to its owner; use existing data before new tracking; add an identifier or no-benchmark note only if the request touches one.
- **Every cut decides something.** For each segment, metric or test say what each result means, the next action and the money consequence (revenue per visitor, average order value, margin, payback). Compute thresholds, sample sizes and dates from stated figures.
- **End with a this-week step:** two or three actions naming the exact event, cohort, query or test and the decision threshold the team sets; never close with "share your data and I can help".

Checked by `evals/evals.json`; the prose around the rules is advisory.

## Excuse to rebuttal

- "What's a good retention rate": own baseline (`no-fabricated-benchmarks`).
- "make total cumulative signups our North Star metric": vanity (`north-star-not-vanity`).
- "track every click and event so we have all the data later": noise (`instrument-answers-a-named-question`).
- "How are we doing on activation and retention this month?": their analytics (`routes-real-figures-to-analytics`).
- "On day 2 the variant hit p = 0.03 on click-through": peeking (`experiment-peeking-is-not-a-win-precommit-or-sequential`).
- "the team wants to double the ad budget": retention first (`diagnose-retention-before-pouring-in-acquisition`).
- "40,000 signups and says 8% are active": retained-value metric (`ends-with-a-this-week-step-not-a-data-request`).
- "Ship the variant? Give a call.": recompute first (`experiment-call-recomputes-then-decides`).
- "they need the full list for the sprint": deliver it (`delivers-the-asked-artifact-with-reading-rules`).
- "can launch before the holiday sale on day 12": a call inside the deadline (`runnable-call-fits-the-deadline`).

## Escalate: read this when

- `references/full-map.md`: you need a moved section: One North Star, Read AARRR bottom-up, Event taxonomy, Instrument for the stage, Experiment rigor, Asked for a call, Deliver what was asked, Make every cut decide something, plus the definition of done, the Anti-rationalization table, standards and verification cases.
- `evals/evals.json`: you change this skill and need the planted cases listed above.

Output structure follows `communication-structure` if installed.

- `scripts/readout_check.py`: run it when you read a finished A/B readout JSON; it checks only what the input pre-registers (SRM alpha, alpha, planned N and days), else SKIP.
