# G6 set6 pre-registration (written before any set6 fixture exists)

## What is scored
- Scorer: `docs/bench/g6-data-api/scorer-v2/run_and_score.py` and `scorer-v2/agentic_arm.py` at v2.4, unchanged since set5.
- Detector: commit 5c2ebf4947c612d2a6c6b7ca8db8aa4bba73c10f (main at release 1.652.0, #2259; tree 177c693269f92185df16f214bc0b416cb738bd28, .claude/skills tree 91557d1b3911b770d31c31ce3a78714378dcd7be, hooks/hooks.json blob 184e6e646cd61d0afe8d5af961739d78ce7dd78b), exported with git archive. It is fixed here, before this set is built, and is not edited after the set exists. The `run_started` event records:
  - the released commit;
  - whether its `.claude/skills` tree differs from 5c2ebf4947c612d2a6c6b7ca8db8aa4bba73c10f in anything other than `version:` frontmatter lines;
  - whether its `hooks/hooks.json` blob differs from 184e6e646cd61d0afe8d5af961739d78ce7dd78b. Any difference stops the run.
- Sizes, markers, spacing and part list are the same as set5:
  - 6 new stacks, none used in set1-set5. Used so far: Go net/http, Express, Next.js, Flask, Spring, Django, ASP.NET, Rails, FastAPI, Laravel, Fastify, gin, Hono, axum, Phoenix, Ktor, echo, Sinatra, actix-web, Symfony, Koa, NestJS, chi, Quarkus.
  - Routes 36 positives / 36 decoys; outbound 36 / 18.
  - rate_limit, csrf, cookie_flags, pii_log, pii_data and prompt_injection 14 / 12 each.
  - A positive and a decoy at least 7 lines apart.

## Fixture rules (set4 rules R0-R4 unchanged, R5 updated)
- R0-R4: verbatim from set4/PREREG.md.
- R5: the set author is a fresh agent. It is shown only this file, the "## Fixture rules" section of set4/PREREG.md, set4/build.py (marker grammar), set4/src (stack shape) and its brief's generic fixture-craft rules (no detector or run information).
  - No set5 file is shown, because the detector changes below were developed against set5.
  - It is not shown any results-* dir, ledger.jsonl, adjudication files, analysis of earlier runs, or the detector's changelog for #2251, #2252, #2256 or #2258.
  - The commit message logs what it was shown.

## Adjudication
- Primary: set6/ADJUDICATOR.md is set4/ADJUDICATOR.md verbatim with the set name changed.
- Secondary: the same unmatched rows adjudicated with the set3 brief, without the reference line. Both final scores are reported. The verdict comes from the primary.

## Run and fail policy
- Unchanged from set5/PREREG.md: ONE scored attempt, with quota utilization below 0.8 before the start.
  - Cost: $10 cap at $3 per call. Launched as one harness-tracked command, never detached.
  - Faults: the same per-fixture infrastructure rule and the same run_started stop rules. No fixture runs a third time.
- Set6 is burned after the run whatever the result. On a fail there is no re-run on set6; set7 is next.

## Disclosure
- Set5 FAILED on recall:
  - Strict recall: routes 30/36, outbound 29/36, rate_limit 9/14, csrf 10/14, cookie_flags 12/14, pii_log 12/14, pii_data 11/14, prompt_injection 10/14.
  - Set5 is burned and was then used as development data.
- The detector for set6 differs from the set5 detector (fa1d9b854) by changes developed against set5 output. Set6 measures whether they generalize to stacks the detector has not seen:
  - #2251: raw-http route inventory, a failing-lint stop sign, and cost-limit recall (PHP Symfony/Laravel handlers, a `send` cost kind, a one-hop LLM-helper rule, `->chat(` receivers).
  - #2252: cost-limit evidence binds to the route the limiter covers (imports and DI declarations are not evidence; group and `.With` scoped limiters cover only their routes).
  - #2256: a plugin Stop hook (`hooks/hooks.json` -> `scripts/audit_report_gate.py`) lints the final whole-app report with `report_contract_lint.py` and blocks delivery once when it fails. It was built after a dev run of e075b0534 on set5: 3 of 6 audits skipped the report template and hand-wrote tables (their reports fail the lint with 20, 64 and 72 violations), and two of them held 52 of the 54 misses. In the dev run of 7ab8f800bbfdb8ca8594fcf73526e7eb347380d9 on set5 the gate never fired: all 6 final reports passed the lint without it.
  - #2258: whole-app report inventory rows gain `csrf=<none|token|origin|samesite|n/a>`. The lint fails a cookie or session POST/PUT/PATCH/DELETE row without it (`inventory-no-csrf`) and a `csrf=none` row with no matching `[csrf]` finding (`csrf-unfiled`). It was built after the 7ab8f800b dev run missed set5 csrf recall by one hit (11/14): the three missed routes were all listed in the reports' inventories but never filed. A replay that edited the six dev reports flagged exactly those three rows and no row that already had a finding. It was not re-run live on set5.
- No other `.claude/skills` or `hooks/` change lies between fa1d9b854 and 5c2ebf4947c612d2a6c6b7ca8db8aa4bba73c10f except the lockstep `version` stamps of releases 1.649.0 (#2248), 1.650.0 (#2255), 1.651.0 (#2257) and 1.652.0 (#2259). Checked with `git log fa1d9b854..5c2ebf4947c612d2a6c6b7ca8db8aa4bba73c10f -- .claude/skills hooks`.
- Development checks on the burned set5, run before this file was committed (results in the commit that adds this file): e075b0534 once, 7ab8f800bbfdb8ca8594fcf73526e7eb347380d9 once, and the #2258 replay on the 7ab8f800b reports. Set5 was already burned, so none of these measures anything about set6.
- Doctrine revisit trigger carried from set4: if real-repo audits (G9) produce 3 or more LLM-route rate-limit findings that a reviewer judges noise, re-open the doctrine before set7.
