# G6 set5 pre-registration (written before any set5 fixture exists)

## What is scored
- Scorer: `docs/bench/g6-data-api/scorer-v2/run_and_score.py` and `scorer-v2/agentic_arm.py` at v2.4 (the ledger's `"amended"` event): the v2.3 parse, strict scoring, an adjudicated tp that credits precision only, plus the v2.4 reachability probe and stop on the first infrastructure fault.
- Detector: commit fa1d9b854 (main after #2244), exported with git archive. It is fixed here, before this set is built, and is not edited after the set exists. The `run_started` event records the released commit and whether its `.claude/skills` tree differs from fa1d9b854 in anything other than `version:` frontmatter lines.
- Sizes, markers, spacing and part list are the same as set4: 6 new stacks not used in set1-set4; routes 36 positives / 36 decoys; outbound 36 / 18; rate_limit, csrf, cookie_flags, pii_log, pii_data and prompt_injection 14 / 12 each; a positive and a decoy at least 7 lines apart.

## Fixture rules (set4 rules R0-R4 unchanged, R5 updated)
- R0-R4: verbatim from set4/PREREG.md.
- R5: the set author is a fresh agent. It is shown only this file, set4/build.py (marker grammar) and set4/src (stack shape). It is not shown any results-* dir, ledger.jsonl, adjudication files or analysis of earlier runs. The commit message logs what it was shown.

## Adjudication
- Primary: set5/ADJUDICATOR.md is set4/ADJUDICATOR.md verbatim with the set name changed.
- Secondary: the same unmatched rows adjudicated with the set3 brief, without the reference line. Both final scores are reported. The verdict comes from the primary.

## Run and fail policy
- ONE scored attempt. Quota utilization must be below 0.8 before the start, and nothing heavy runs alongside. The cap is $10 at $3 per call. Set5 is burned after the run whatever the result.
- The arm is launched as one harness-tracked command with the model hosts in its network allowlist, never detached (scorer-v2/README.txt runbook).
- Per-fixture infrastructure rule (new, from the set4 fault): a fixture counts as faulted when the arm stops on it with an infrastructure fault (proxy, tunnel, connection, API 5xx or overloaded error) or when it cost $0 with the skill not loaded, so the model never took a turn. Each faulted fixture, and each fixture the stop left unrun, is run once more in a second invocation of the same arm and detector. Reports already produced are kept as they are and not opened before scoring. A fixture that faults again scores as an empty report (all its positives missed).
- Any fixture that produced a model turn counts as run, whatever its report says. No fixture is run a third time.
- On a fail there is no re-run on set5; set6 is next.

## Disclosure
- Set4 FAILED on an infrastructure fault: 5 of 6 fixtures hit ERR_PROXY_TUNNEL after a detached launch. Per its pre-registration the attempt counted and set4 is burned. Its one produced report (atlas-hono) was scored automatically, was not adjudicated, and was not used to change the detector, the scorer rules or these fixture rules.
- The detector for set5 differs from the set4 detector by changes made for other gates (G1 API Top 10 pilot, G5 currency, the veche scores repair). None was tuned on any set4 output.
- Doctrine revisit trigger carried from set4: if real-repo audits (G9) produce 3 or more LLM-route rate-limit findings that a reviewer judges noise, re-open the doctrine before set6.
