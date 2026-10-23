# Energy & carbon efficiency (domain E)

Read this when the target runs on a battery or radio (mobile, embedded, wearable, laptop client, browser tab), runs at fleet scale or always-on (pollers, daemons, scheduled jobs, streaming, ML inference), or the ask is carbon, energy or sustainability. Wasted work is already an E finding (`performance-db-cost.md`); this file adds what that one does not: the measurement frame, the battery and idle-power cases, and carbon-aware placement.

## The measurement frame: a number or `UNMEASURED`

The Green Software Foundation's Software Carbon Intensity (SCI) specification (version 1.1, October 2024; its standards page cites ISO/IEC 21031:2024) scores software as a rate: **SCI = ((E × I) + M) per R**.

| Term | Meaning (SCI) | What code review can move |
|---|---|---|
| E | energy consumed by the software system (kWh) | do less work; stop idle work; cheaper algorithms and payloads |
| I | region-specific carbon intensity of that energy (gCO2eq/kWh) | where, and on which grid, the work runs |
| M | embodied emissions of the hardware needed (gCO2eq) | fewer or smaller instances; longer hardware life |
| R | the functional unit (per user, per API call) | the denominator: pick one that matches the product |

A review does not compute an SCI without measurements. With no energy or carbon data in the repo or its telemetry, report `UNMEASURED`, never a made-up kWh or gCO2eq (the same rule as DORA in `release-engineering.md`). AWS's Well-Architected Framework lists Sustainability as one of its six pillars, so a review that claims Well-Architected coverage walks it or says it did not (standards are not claimed unless walked, `SKILL.md`).

## Probes (each is a lead, to be measured before it is a number)

- **Polling and timers.** `setInterval`, `while True: sleep(small)`, busy waits, and short polling where push exists (`performance-db-cost.md`, "Events over polling", for the server side); a timer with no backoff or no cancel on teardown keeps waking the CPU after the view is gone.
- **Wake locks and background work (mobile, embedded).** Android's documentation says holding a wake lock "can have a dramatic impact on the device's battery life", to avoid one when a suitable alternative exists, and to hold it as briefly as possible. 🚩 a wake lock acquired with no matching release on every exit path, a foreground service or continuous high-accuracy location or sensor stream with no stop condition, background work with no constraints.
- **Browser tabs.** MDN states that most browsers pause `requestAnimationFrame` callbacks in background tabs and hidden iframes to save performance and battery. A render loop that does not use `requestAnimationFrame` (a `setInterval` redraw, a socket-driven update) is not covered by that pause: check what it does in a hidden tab and gate it on the Page Visibility API. 🚩 animation or polling that continues in a hidden tab, autoplaying video, unoptimised media, uncompressed responses, no HTTP caching (`web-fetch.md`, `web-render.md`).
- **Idle and always-on capacity.** Non-production environments that never scale down, minimum instance counts above need, over-provisioned limits (rightsizing is in `performance-db-cost.md`, FinOps), cron more frequent than the data changes (`ci_cost_lint.py` checks CI schedules; apply the same question to production schedules).
- **Work multiplied by failure.** Retry storms and unbounded retries (`reliability-error-handling.md`), chatty telemetry and log volume (`observability.md`, cardinality), reprocessing unchanged inputs.
- **Data footprint.** Cold data kept on a hot tier, duplicate copies, retention with no end date (retention is also a privacy finding: `privacy-compliance.md`).
- **Model use.** Over-sized model or no cache for repeated prompts (`model-tiering.md`); cost and energy usually move together, so the cost finding is the energy finding.

## Carbon-aware placement (an option for the owner, not a patch)

I is region-specific in the SCI. Deferrable batch work that could run in a lower-carbon region is worth naming as an option. Check data residency, latency and cost first (`privacy-compliance.md`); moving work or data across regions is a design decision, not a review fix (principle 5 in `full-map-principles.md`).

## Limits on this lens

- An energy claim needs a measurement. A finding with no measurement is a hypothesis, labelled as one (principle 3).
- Never trade correctness, security or accessibility for energy (principle 4).
- Severity: Low or Medium by default. High only for waste on a hot path at scale, or background drain on a user's device (a user-visible harm). Never a Blocker.
