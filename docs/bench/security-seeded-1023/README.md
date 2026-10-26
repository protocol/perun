# Seeded security bench: Perun vs the claude-code-security-review prompt

## Blind held-out result (2026-10-26, `runs/heldout2/`)

Result: on 10 blind held-out diffs (8 seeded, 2 decoys) Perun and the rival tie: both find 8/8 (recall 1.00, Wilson 95% interval
0.68 to 1.00, n=8), both have precision 0.80 (10 findings, 8 true), both flag 0/2 decoys. Perun costs 1.39x the rival ($0.343 vs $0.247).
One call per diff per arm, so this is a point result, not a significance claim.

Both held-out sets are RETIRED: each was used once, so neither may back a future claim; the next claim needs a new blind set.
Only heldout2 is independent evidence for the skill change: the section 0 rule to cite the line a fix would change came from the
tuned misses 05 and 06, so the tuned set measures the fix it shaped.

- Set: `scripts/eval-fixtures/security-seeded-heldout2`, written by a separate lane that had not seen the skill change, and read by this
  lane only after the skill edits were final. The rival keyword table in `run.py`
  gained `timing` (CWE-208) before scoring, so its strict score is not hurt by a missing map entry.
- Both arms' two extra findings sit on the same unseeded lines (a session issue next to the redirect in h2-06, an authentication issue
  next to the timing compare in h2-07). They may be real but are not keyed, so both count as false positives for both arms.
- Spend: $0.590 for 20 calls, no errors; plan quota peaked at 0.57 (stop at 0.8). Ledger total $1.93 in `ledger-1026.jsonl`.

| Set | Arm | Recall (Wilson 95%) | Precision | Decoy FP | Spend |
|---|---|---|---|---|---|
| heldout2 (blind, 10) | PERUN | 8/8 (0.68 to 1.00) | 0.80 | 0/2 | $0.343 |
| heldout2 (blind, 10) | RIVAL | 8/8 (0.68 to 1.00) | 0.80 strict, 0.89 location-only | 0/2 | $0.247 |

The gain over the first run below comes from the harness fixes and the skill change together; this bench cannot separate the two,
because both changed between the runs.

### Earlier rerun on tuned and burned sets (`runs/tuned/`, `runs/heldout/`)

The 8-diff set in `scripts/eval-fixtures/security-seeded-heldout` is BURNED and RETIRED: the same author wrote it and the skill change, and a later
review found the skill text named two of its classes. Treat it as regression data, not as a held-out measure.

| Set | Arm | Recall (Wilson 95%) | Precision | Decoy FP | Spend |
|---|---|---|---|---|---|
| tuned (16, seen while fixing) | PERUN | 12/12 (0.76 to 1.00) | 1.00 | 0/4 | $0.524 |
| tuned | RIVAL | 11/12 (0.65 to 0.99) | 0.92 | 0/4 | $0.358 |
| heldout, BURNED (8) | PERUN | 6/6 (0.61 to 1.00) | 1.00 | 0/2 | $0.272 |
| heldout, BURNED | RIVAL, location only | 6/6 (0.61 to 1.00) | 1.00 | 0/2 | $0.187 |
| heldout, BURNED | RIVAL, strict CWE | 5/6 (0.44 to 0.97) | 0.83 | 0/2 | (same calls) |

- Cost on these two sets: Perun 1.46x the rival ($0.796 vs $0.545); it was about 4x in the first run.
- The rival's strict miss on the burned set is a scoring artifact: its category text mapped through the keyword table to CWE-862 for a
  signature-verification finding at the right line. The rival's tuned miss is 05-authz-bypass, cited at line 6 instead of line 9.
- Cost (`usage-1026.jsonl`, means over 24 calls per arm): PERUN 4 turns, 6,772 cache-write and 16,017 cache-read tokens, 445 output;
  RIVAL 1 turn, 4,506 cache-write, 3,223 cache-read, 435 output. Perun's premium is reading `SKILL.md` and `appsec-verify.md`.
- Fixture 06 on main carries a shorter placeholder key than the first run used (privacy gate); the key line is unchanged.
- Spend for the 48 calls: $1.34, no errors; plan quota peaked at 0.37.

### What the first run got wrong, and the fixes

All four Perun misses in the first run were location errors, and each also counted as a false positive (8/12 recall, precision 0.67):

| Fixture | Class | Reported vs key | Root cause | Label |
|---|---|---|---|---|
| 02-xss | reflected XSS | line 10 vs 5 | cited the line number inside the patch text (the patch has 5 header lines), not the new-file line | output format (skill gap) |
| 03-ssrf | SSRF | line 11 vs 6 | same patch-line offset | output format (skill gap) |
| 06-hardcoded-secret | hardcoded credential | line 8 vs 3 | same patch-line offset | output format (skill gap) |
| 05-authz-bypass | missing authorization | line 6 vs 9 | anchored at the function header, not the privileged call the check should guard | skill gap (which line to cite) |
| 11-toctou (first attempt) | TOCTOU | unparsable | stalled on Write approval | harness |

Harness gaps found: the `Write(rows.json)` allow rule never matched, so 14 of 15 Perun replies say the verify script never ran (the 15th is a bare `[]`) and spent
turns retrying; the forced prompt read `security-appsec.md` (27,998 B) and `appsec-verify.md` and demanded the script, overriding the
skill's own small-diff route; Perun had to Read `change.patch` (line-numbered by the tool) while the rival got the diff inline; the rival's
PR title carried the fixture id (`change 05-authz-bypass`, `change 13-decoy-...`), leaking the class or the decoy label; and
`out/PERUN/02-xss.json` from 2026-10-23 has no ledger or raw record, so the first run's 02-xss row has no provenance.
The first run logged no token usage, so its 4x cannot be split exactly; the forced reads and the blocked-write retries are the only
per-call differences, and removing both took Perun from about $0.09 to $0.033 per call on the same model.

Fixes: `SKILL.md` asks for the new-file line (hunk `+start` plus offset) and routes a security review of a small DIFF to
`references/appsec-verify.md` section 0 only; section 0 is a one-paragraph sink sweep that cites the line a fix would change and skips the script on a
patch-only review. `run.py` now inlines the diff for both arms, gives both Read, Grep and Glob only, uses a neutral PR title, logs usage,
and scores strict and location-only.

Rerun: `python3 docs/bench/security-seeded-1023/run.py run tuned|heldout|heldout2`, then `run.py score <set>` (`runs/<set>/score.json`).

## History: first run (2026-10-23 and 2026-10-26, `out/`, `raw/`, `ledger.jsonl`)

Result: no verdict. After one paid call (PERUN on 01-sqli, $0.0822, 1 finding matching the key) the plan-quota reading was
utilization 1.00, at or above the 0.8 stop, so the run ended by contract. RIVAL arm: zero calls. Win/tie/loss: none claimed.

- Spend this run: PERUN $0.0822, RIVAL $0.00 (cap $8). `ledger.jsonl` holds it; `ledger-blocked-network.jsonl` is one
  $0 call that failed because the sandbox denied api.anthropic.com before the host was allowed.
- $190 total cap: in-repo ledgers (`docs/bench/**/ledger*.jsonl`) sum to $32.44, but earlier ledgers were lost when a scratch dir was wiped,
  so that is a floor, not the true spend. Remaining headroom is not provable from the repo; this run's $0.08 is negligible either way.
- Rival prompt: `rival_prompts.py` is `claudecode/prompts.py` (trailing whitespace stripped, otherwise verbatim) from https://github.com/anthropics/claude-code-security-review
  (upstream main 0c6a49f1fa56a1d472575da86a94dbc1edb78eda, committed 2026-02-11), fetched 2026-10-23. The rival output has no CWE field, so `run.py`
  maps its `category` text to a CWE by keyword (a conservative guess; unmapped means file+line only scoring).
- Perun arm caveat: the sandbox required approval for every way of feeding `security_verify.py`, so the model fell back to a manual
  verify-or-drop; the script was not exercised. The harness allows only that one Bash command.
- Resume: `python3 docs/bench/security-seeded-1023/run.py` when utilization is below 0.8 (reuses finished `out/` files), then
  `python3 scripts/security_bench_score.py PERUN=docs/bench/security-seeded-1023/out/PERUN RIVAL=docs/bench/security-seeded-1023/out/RIVAL`.

## Result (2026-10-26, completed run, supersedes the quota-stop note above)

16 diffs (12 seeded, 4 decoys), both arms, same model. Spend PERUN $1.42, RIVAL $0.35 (ledger total $1.78, cap $8); plan quota 0.34 at the end.
PERUN recall 0.67 (8/12, Wilson 95% 0.39-0.86), precision 0.67, decoy FP 0/4. RIVAL recall 0.83 (10/12, Wilson 95% 0.55-0.95), precision 0.91, decoy FP 0/4.
Verdict: Perun does not beat the rival on this bench; CIs overlap (n=12), at about 4x the cost. Scores in `score.txt`.
Caveats: PERUN/11-toctou first attempt asked for Write approval and was unparsable (harness permission gap); it was rerun once (extra paid call, both attempts in the ledger), the second parse is scored. RIVAL CWE comes from a keyword map of its category text.
