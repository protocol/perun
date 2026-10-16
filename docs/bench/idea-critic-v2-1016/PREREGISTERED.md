# Preregistration: idea-critic v2 (Veles) on a fresh held-out set (2026-10-16)

Written and hashed (SHA256-frozen.txt) before the first paid call of this run. Refs #1572.

## Why

`docs/bench/idea-critic-rubricfree-1016/` measured the current skill (OLD) against the same rival with a rubric-free blind judge: win rate 0.650, 95% CI [0.450, 0.850], n=10, not significant. Its 20 judge reasons say: where OLD won, the cited reasons are correct arithmetic and sharper insight; where the rival won or the order split, they are "more actionable" (a phased path, concrete data to gather before the meeting, named alternatives, quantified upside, sharper questions). The old skill has a verdict schema and hats but no instruction to compare against do-nothing and the strongest alternatives, to check strategic fit, to price delay, to mark claims as assumed, or to close with one decision, its tripwires and a leading metric.

## The change under test (NEW)

`.claude/skills/idea-critic/SKILL.md` gains a six-step "Decision method" (steelman then attack; do nothing plus the 2 strongest alternatives; fit with stage, vision and north star, reusing the CEO loop's context; pre-mortem, door type and cost of delay; evidence or `assumed`, recompute the requester's figures; close with ONE decision, kill criteria, leading metric, review date) and is otherwise shortened: 15,519 bytes against 15,950 for OLD. No scenario text is in the skill. The decision council (renamed Veche) is not exercised by this bench (no tools in either arm).

## Arms (system prompt only, no tools, same model, same task wrapper)

- NEW: `prompts/new.txt` = the edited SKILL.md.
- OLD: `prompts/old.txt` = SKILL.md at origin/main c097d01f (identical to `idea-critic-rubricfree-1016/prompts/perun.txt`, sha 0dcae5ff).
- RIVAL: `prompts/rival.txt`, the unmodified garrytan/gstack plan-ceo-review/SKILL.md used in the earlier bench (commit 47d639ab, MIT, `LICENSE.rival.txt`; sha 46e5912b).
- PLAIN: `prompts/plain.txt`, the one-line system prompt "You are a helpful assistant." (the plain model, no skill).
- Generation: claude-sonnet-5-5, `--tools ""`, arm file as `--system-prompt`, wrapper `prompts/gen_task.txt` (unchanged from the earlier bench).

## Scenarios

10 fresh generic decision scenarios (none reused from the earlier set or from `evals/`), written by claude-sonnet-5-5 from `prompts/writer_brief.txt` and `prompts/seeds.txt`; the writer sees no skill. Used unedited, none dropped. Fictional names only. The scenarios file does not exist until the first call of this run; I have not read any output of any arm before freezing.

## Judge

claude-sonnet-5-5, blind Response 1 / Response 2, no criteria, `prompts/judge.txt` unchanged, verdict only; both orders per scenario; a scenario score is the mean of 1 (first-named arm preferred), 0.5 (tie), 0 per order. DEVIATION from the earlier bench, declared: the judge is Sonnet, not Opus. Reason: the hard cap of $1.50 for this whole run; at the measured Opus price (about $0.035 per judge call) 60 judge calls alone cost about $2.10. Consequence: not comparable with the 0.650 figure; NEW and OLD are judged by the same judge on the same set, so the NEW-vs-OLD comparison is internally consistent. Same-vendor judge and n=10 are caveats on every outcome.

## Comparisons, in priority order

1. NEW vs OLD (decides keep or revert).
2. NEW vs RIVAL.
3. NEW vs PLAIN.

Win rate of the first-named arm, bootstrap over scenarios (10,000 resamples, seed 1, percentile). A comparison PASSES only if the 95% CI lower bound is above 0.5; otherwise it is reported as not shown superior, a tie or a loss, plainly.

## Decision rule (frozen now)

Keep the SKILL.md change only if SKILL.md(NEW) is no larger than SKILL.md(OLD) (true by construction) AND NEW vs OLD win rate is at least 0.5. If the lower CI bound is above 0.5 the report says "beats the old skill"; if only the point estimate is at least 0.5 it says "no measured loss", not "better". If the NEW vs OLD win rate is below 0.5 the SKILL.md change is reverted and the negative is recorded; the later comparisons are then not run (stop rule below). Comparisons 2 and 3 do not change the keep or revert decision; they are reported. One set, no skill edits and no re-runs after the first result is seen.

## Budget and stop rule

Hard cap $1.50 across everything in `ledger.jsonl` (the scenario writer included), checked before each call with an in-flight reserve; every call also passes `--max-budget-usd`. Expected spend about $1.4 (earlier ledger: gens $0.02 to $0.05, Opus judge $0.035). Pairs run in priority order; if the cap stops the run, the pairs not finished are reported as incomplete, not as results. A NEW-vs-OLD win rate below 0.5 stops the run after pair 1 (spend saved).
