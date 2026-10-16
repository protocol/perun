# Preregistration: communication-structure after the comms-quality fix, 3 arms, rubric-free blind judge (2026-10-16)

Written and hashed (SHA256-frozen.txt) before the first call.

## Why

The previous rubric-free run (docs/bench/comms-rubricfree-1016) tied humanizer: 0.500 [0.250, 0.800]. Its judge reasons named the same failures again and again: an invented recommendation or rationale, invented dates and figures, "Reply A or B" inside a PR body, placeholder signatures, and answers longer than the facts needed. The fix under test: per-artifact templates with word and line budgets (`references/artifact-templates.md`), a faithfulness rule (add nothing the source lacks), `scripts/comms_lint.py`, and the pre-send hook `agentic-delivery/scripts/comms_guard.py`.

## Arms (system prompt only, no tools, same model, same task wrapper)

- PERUN: `prompts/perun.txt` = `SKILL.md` plus `references/artifact-templates.md` at this commit (what an agent loads when it follows the skill's routing). Draft, then `comms_lint.py --kind <kind>` on the finished text with no source (what the hook sees); if below the bar, one rewrite call that receives the FAIL lines. The final text is the arm's answer. The first drafts are kept as PERUNDRAFT.
- RIVAL: humanizer v3.1.0, the unmodified file from `../comms-rubricfree-1016/prompts/rival.txt` (MIT, license stored there).
- PLAIN: the system prompt "You are a helpful assistant." (`prompts/plain.txt`).
- Generation: claude-sonnet-5-5, `--tools ""`, wrapper `prompts/gen_task.txt` and judge `prompts/judge.txt`, both byte-identical to comms-rubricfree-1016 (checked by `bench.py verify`).

## Scenarios

10 fresh scenarios written by claude-opus-5-5 from `prompts/writer_brief.txt` and `prompts/seeds.txt`; the writer never sees the skill. Used unedited, none dropped: 4 status updates from raw notes, 3 PR bodies from a diff summary, 3 executive summaries from a long pasted report. Fictional names only. The kind passed to the linter is fixed by seed: 01-04 `status`, 05-07 `pr`, 08-10 `decision`.

## Judge

claude-opus-5-5, blind Response 1 / Response 2, no criteria ("which would you rather receive"), verdict only, both orders per scenario; a scenario score is the mean of 1 (PERUN preferred), 0.5 (tie), 0 per order.

## Bar

Two primary comparisons, each reported on its own: PERUN over RIVAL and PERUN over PLAIN. Win rate with a bootstrap CI over scenarios (10,000 resamples, seed 1, percentile). A comparison PASSES only if its 95% CI lower bound is above 0.5; otherwise FAIL ("not shown superior"), and a tie or loss is reported plainly. No multiple-comparison correction. Secondary and descriptive only, not part of the bar: PERUNDRAFT over PLAIN (the lint loop's contribution), run only if cumulative spend is at most $2.00 after the primary comparisons; and judge-free numbers per arm (share of outputs that clear `comms_lint.py`, median words), which favour PERUN by construction because the linter was written for it.

## Budget

Hard cap $3 over everything in `ledger.jsonl`, plus `--max-budget-usd` on every call and an in-flight reserve; the driver stops at the cap and the report covers only scenarios with both orders judged. One set, no skill edits after the freeze, no re-runs after seeing results. Caveats on any outcome: n=10, a same-vendor judge, model sampling not seeded, and PERUN's loop uses the linter without a source (the hook's view), so the `--source` check is not exercised here.
