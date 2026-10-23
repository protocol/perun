# bizops-fab-1019: honest null, SKILL.md unchanged

Question: does an edit that bans unsupplied numbers and citations make the business-ops prompt fabricate less, without losing usefulness? Preregistered in `PREREG.md` (hash list `SHA256-frozen.txt`, `preregistered` event as the first line of `ledger.jsonl`, held-out run after it).

Result, 36 held-out fabrication prompts plus 8 controls, strict, same generator, one sample per case (`results.json`):

| | CURRENT | EDITED |
|---|---|---|
| fabricated, all | 0.58 | 0.47 |
| invented statistic (20) | 0.85 | 0.75 |
| fake citation (10) | 0.10 | 0.00 |
| nonexistent API (6) | 0.50 | 0.33 |
| controls computed correctly (8) | 1.00 | 1.00 |
| answers that give a call | 0.91 | 0.95 |
| mean completion tokens | 565 | 526 |

Paired difference fab(CURRENT) - fab(EDITED) = +0.11, 95% bootstrap CI [-0.03, 0.25]: a tie under the preregistered rule (needs lower bound above 0). The guardrail passed, but the edit is not kept and `.claude/skills/business-ops/SKILL.md` is unchanged. Lenient (sensitivity only) is -0.03 [-0.19, 0.14]: lenient excuses 7 of CURRENT's strict fabrications (0.58 to 0.39) but only 2 of EDITED's (0.47 to 0.42), so CURRENT's extra failures were mostly figures it had labelled as assumptions or illustrations.

Reading: the edit cut the strict rate by 11 points on this generator but the interval includes 0, so no claim. The residual S failures are rule-of-thumb thresholds and worked examples on invented figures that the memo format still invites. Next lever if pursued: restructure the memo template (not add a rule) so slots replace brackets for outside-world inputs, then rerun on a new prompt set; `edit.json` is the frozen candidate and cannot be reused as held-out evidence.

Reproduce (needs the PCSS key, no `claude -p`): `python3 scripts/bizops_fab_bench.py run heldout` then `report heldout`. The CURRENT arm reads the committed `SKILL-frozen.md` (the pre-slim `business-ops/SKILL.md`, 11301 bytes, sha256 prefix `39af659d`, the hash in `arm_sha` of `results.json`), so later edits to the live `business-ops/SKILL.md` do not change this bench and every `edit.json` anchor still occurs exactly once; the committed `outputs/` and `results.json` are the record. `outputs/cal/` holds the three calibration rounds (EDITED arm directories are suffixed with the prompt hash). Tests: `scripts/test_bizops_fab_bench.py`.
