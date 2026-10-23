# Product impact — does the change move the outcome it claims, and can anyone tell? (domain M)

Read this when a change claims a user or business outcome (faster, easier, more conversions, fewer support tickets), adds or edits analytics or telemetry events, ships behind an experiment or flag, or changes a user-visible flow whose failure is measured in lost users. Where the rest lives, not restated here: problem to acceptance, smallest slice, non-goals and "a success metric must trace to an emitter" are in `role-coverage.md` (section "Product & requirements — lightweight product planning"); experiment assignment, exposure and sample-ratio checks and the flag lifecycle are in `release-engineering.md`; metric design (north star, funnel, event taxonomy) is the `growth-analytics` overlay when installed; personal data in events is `privacy-compliance.md`. This file reviews the **instrumentation code and the guardrails** that none of those carry.

## Claim, emitter, guardrail, decision

For each outcome the change claims, find four things. A missing one is `unverified` (say which); it becomes a defect only when the claim is in the PR text or release notes.

1. **The metric**, named, with a baseline. A target with no baseline is `unverified`; never invent a baseline or a target.
2. **The emitter**: the `file:line` that produces the event, in the diff or already in the tree.
3. **A guardrail metric that must not regress** (latency, error rate, support contacts, unsubscribes or churn, accessibility). The outcome metric alone can rise while the product gets worse.
4. **The decision rule and its owner**: which reading means keep, which means roll back, and by when.

Qodo's code review names "requirement gaps" (catching a pull request that misses its linked spec) as a finding category. The same check applies here: does the diff do what the linked issue or PR text says it does, and is anything it promises missing?

## Is the event right? (read the emitting code)

- **Exactly once per action.** Not in a render body or an effect whose dependencies re-run, not once per retry, not both optimistic and confirmed. React's Strict Mode runs one extra setup-and-cleanup cycle for every effect in development, so an unguarded event in an effect doubles in development data and still re-fires in production whenever its dependencies change (React documentation). 🚩 `track()` in a component body or an unguarded `useEffect`.
- **At the right moment.** After the server confirms, not at the click. A failure is its own event, and an error path never emits the success event.
- **Survives leaving the page.** MDN calls `unload` and `beforeunload` unreliable (in many situations, especially on mobile, the browser does not fire them) and recommends sending analytics with `navigator.sendBeacon` from a `visibilitychange` to hidden; queued beacon data is limited to 64 KiB. 🚩 analytics sent from `unload` with `fetch` or `XMLHttpRequest`.
- **Server-side for what must be right.** Billing, security and conversion events computed only on the client can be blocked, spoofed or lost; emit them from the server, where the outcome is known.
- **One definition per fact.** The same fact counted by two emitters (client and server, or two components) double counts, and a metric defined in two places drifts (`domain-h.md`, lockstep surfaces).
- **Stable names, typed properties.** A renamed event breaks the series with no error; a property that is sometimes a string and sometimes a number breaks aggregation. Version the schema and test the payload shape at the emitting call site (`testing-and-evals.md`).
- **Identity and consent.** One person across anonymous and signed-in states stitches on a stable id. Events fire only after consent where the regime requires it and carry no personal data they do not need (`privacy-compliance.md`).
- **Time.** Which clock stamps the event: client clocks skew, and occurrence time differs from receive time (`time-date-correctness.md`).
- **Silent loss is observable.** A dropped event increments a counter somewhere, and "no data" is not read as zero (`data-freshness.md`).

## Rollout and reversibility

A change that claims an outcome ships so that it can be measured and undone: behind a flag or to a cohort first, with a kill switch and a halt condition tied to a guardrail (`release-engineering.md`: canary claims, rollback). A behaviour change shipped with no way to read its effect is flying blind; one shipped to everyone with no way back turns every wrong guess into an incident.

## The negative product impact a code read can see

- Steps, fields, modals or clicks added to a critical path (signup, checkout, a primary action).
- A performance regression on that path. web.dev's Core Web Vitals "good" thresholds are LCP within 2.5 seconds, INP of 200 milliseconds or less and CLS of 0.1 or less, at the 75th percentile of real page loads; a lab run is not field data (`frontend-a11y.md`).
- Accessibility regressions that exclude users (WCAG 2.2 AA, `domain-p.md`), and removed information or copy that users relied on (`ux-writes.md`).

Report the mechanism and the path it sits on, never an invented conversion loss.

## Limits

Product ideas and priorities are owner decisions (`role-coverage.md`, principle 5 in `full-map-principles.md`). This lens verifies that the claim, the measurement and the way back exist; it does not rank features or predict outcomes. Severity: a missing emitter or guardrail on a claimed outcome is Medium. High only when the change touches money, safety or an irreversible user-facing action and has no kill switch.
