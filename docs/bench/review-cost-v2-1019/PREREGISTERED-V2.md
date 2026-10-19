# Pre-registration: review-cost V2 held-out confirmation on Claude (frozen before any paid call)

Goal: a measured review win against the rival TK (pr-review-toolkit code-reviewer system prompt): F1 not worse than TK at no more tokens than TK, or F1 clearly better than TK at no more than twice TK's tokens. This follows the V1 revert (../review-cost-parity-1017/DEVIATIONS.md item 9: stub plus references plus 5.6 tool turns cost 4.2x TK).

## Variants tried (maximum 3, tune split only, free PCSS Qwen3.5-397B-A17B host, free PCSS judges, no paid call)
V2 = one inlined compact method used as the whole review prompt: no routed reference for a small DIFF, one read of the patch, answer on the next turn (2 turns). Non-DIFF scopes still route to `references/full-map.md` (the unedited skill body).
Tune results vs TK on the 21 tune cases (pairs where both arms completed; cases that errored twice are dropped per arm, so n differs by variant):
- V2a: n=19, F1 0.578 vs 0.537, difference +0.040 (95% CI -0.042 to 0.127), tokens 5211 vs 5257.
- V2b: n=18, F1 0.661 vs 0.538, difference +0.124 (CI -0.016 to 0.309), tokens 5058 vs 4808.
- V2c: n=18, F1 0.783 vs 0.563, difference +0.220 (CI 0.053 to 0.392), tokens 5127 vs 4869.
Selection rule (stated before looking at V2c): highest tune F1 difference. V2c is selected. Tune numbers are for tuning only and are not evidence for the keep rule.

## Frozen artifact
Frozen file hashes are in SHA256-frozen.txt (paths from the repo root); the ledger's first line carries the hash of that list. V2 = `variants/V2c.md` (body) built into a skill copy by `mk_v2.py V2c <dir>`; `variants/V2c.built-SKILL.md` is the built SKILL.md. The V2 arm passes the body (everything after the frontmatter) as `--system-prompt`, the same harness as TK; `system_for` in driver.py does the stripping.

## Held-out run (once, no re-run, no re-tuning)
- Cases: the 22 held-out ids in split.json; n = cases where V2 and TK both completed and were judged (a case that errors twice is dropped from the V2-vs-TK read and reported).
- Host: `claude -p`, model claude-sonnet-5-5 for every arm, read-only tools Read/Grep/Glob, `--setting-sources project,local --strict-mcp-config`, same PRODUCER request text for V2 and TK; BASE and V2s get the PERUN request with the unedited skill (BASE) or the V2 skill copy (V2s) in the workspace. V2s is descriptive only and does not enter the keep rule.
- Judging: free PCSS judges exactly as in driver.py (DeepSeek-V4-Flash, GLM-5.2 tie-break), per-finding classification, pooled precision/recall/F1.
- Tokens per review = input + cache-creation + cache-read + output tokens of the `claude -p` result usage (the same accounting for all arms).
- Spend: hard cap $25 total by ledger (`ledger.jsonl`), per-call reserve $0.30 checked before each call, `--max-budget-usd 0.30` per call, abort at plan utilization >= 0.8 or if the reading is missing. Pre-estimate from the earlier real-skill bench ledger: TK $0.013, skill-in-workspace $0.041 per review; 22 cases x 4 arms is about $3, about $6 with retries.
- Statistics: paired case-level bootstrap, 10000 resamples, seed 1, 95% percentile CI, on F1 of V2 minus TK.

## Keep rule (decided by `confirm.py verdict`, `decide()`)
Keep if A or B holds, else REVERT:
- A: F1(V2) - F1(TK) >= 0 (point), its CI lower bound >= -0.05, and mean tokens V2 <= mean tokens TK.
- B: the CI lower bound of F1(V2) - F1(TK) is > 0 and mean tokens V2 <= 2 x mean tokens TK.
The V2 vs BASE F1 difference is reported but does not decide.

## Stated in advance
- Tune tokens were 1.05x TK on the PCSS host, so A may fail on tokens; B then needs the CI lower bound above 0.
- n=22 gives a wide CI; a real gain can fail by noise. A failed read is reported as REVERT, not rerun.
- If the rule says keep, the skill edit (SKILL.md body replaced by V2c, size/mustload budgets, routing, eval) is a separate change: this branch edits no SKILL.md and ships the evidence only.
