# G6 set4 pre-registration (written before any set4 fixture exists)

## What is scored
- Scorer: `docs/bench/g6-data-api/scorer-v2/run_and_score.py` and `scorer-v2/agentic_arm.py` with the rules in the ledger's `set4+` events: the v2.3 parse, strict scoring, and an adjudicated tp that credits precision only.
- Detector: one product commit recorded in the `run_started` event. It is frozen before this set is built and is not edited after the set exists.
- Sizes, markers, spacing and part list are the same as set3: 6 new stacks not used in set1-set3; routes 36 positives / 36 decoys; outbound 36 / 18; rate_limit, csrf, cookie_flags, pii_log, pii_data and prompt_injection 14 / 12 each; a positive and a decoy at least 7 lines apart.

## Fixture rules (set1-set3 rules plus R1-R5)
- R0 (from set2): a decoy is clean in every respect and sits in its own file region. It carries no issue of any class.
- R1: every route that is not a rate_limit positive has a limiter applied or does no brute-forceable or costly work. Brute-forceable or costly work means a credential, PIN or OTP compare, an SMS or email send, a model/LLM or paid API call, or a bulk export.
- R2, what "limiter applied" means: a route-level limiter, a router or group middleware, or a global limiter registered in app setup that covers the route, all visible in the fixture repo. Any key (per IP, per user, per token) and any window counts.
- R3: at least 4 rate_limit positives are LLM or model-call routes with no limiter. At least 4 rate_limit decoys are LLM routes with a limiter, and at least 2 of those get their limiter from group or global middleware, not a route-level call.
- R4: a positive carries only its own class. Its route has no issue of another class unless that issue is a separate truth row at least 7 lines away.
- R5: the set author is a fresh agent. It is shown only this file, set3/build.py (marker grammar) and set3/src (stack shape). It is not shown any results-* dir, ledger.jsonl, adjudication files or analysis of earlier runs. The commit message logs what it was shown.

## Adjudication
- Primary: set4/ADJUDICATOR.md is the set3 brief verbatim with the set name changed, plus one reference line under criterion 3:
  `Reference for rate_limit (OWASP LLM10:2025 Unbounded Consumption, prevention): "Apply rate limiting and user quotas to restrict the number of requests a single source entity can make in a given time period."`
- Secondary: the same unmatched rows adjudicated with the set3 brief, without the reference line. Both final scores are reported. The verdict comes from the primary.

## Run and fail policy
- ONE scored attempt. Quota utilization must be below 0.8 before the start, and nothing heavy runs alongside. The cap is $10 at $3 per call. Set4 is burned after the run whatever the result.
- On a fail there is no re-run on set4; set5 is next.
- An infrastructure fault voids the attempt, and it may be re-run once from scratch, only if no fixture report was produced or read. Infrastructure faults are a harness crash, an API or proxy error, or skill-not-loaded. Once any report exists, the attempt counts.

## Disclosure
- R1-R3 and the adjudicator reference line were derived from the set3 failure: all 8 set3 rate_limit false positives under the v2.3 offline re-parse were LLM routes without a limiter that sat on prompt_injection decoys or positives. That breaks R0.
- The set3 record stays as scored: FAIL 4/8, with rate_limit precision 15/32 under v2.1.
- Two set3 results are diagnostics, not claims: the v2.3 offline re-score (7/8 parts; rate_limit 14/22) and a dry run of the primary brief on those 8 burned rows (6 tp, 2 fp).
- Doctrine revisit trigger: if real-repo audits (G9) produce 3 or more LLM-route rate-limit findings that a reviewer judges noise, re-open the doctrine before set5.
