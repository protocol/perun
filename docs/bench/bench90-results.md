# Benchmark results: held-out cases, clean re-run (2026-10-09)

This page replaces the earlier 30-case numbers and the 64-case interim numbers. It is a clean re-run of 89 cases with isolated run directories (harness branch `fix/bench-run-isolation`).

## Bottom line

- **Reviewing with repo access is the big win.** Run as an agent in a checkout at the pre-fix commit with Read, Grep and Glob, a review reached recall 0.644 and precision 0.820. A prompt-only review (diff only) reached recall 0.367 and precision 0.611. The difference is +0.278 recall (interval +0.189 to +0.378) and about +0.2 precision. Perun makes repo access the default.
- Adding the full deep-code-review skill text on top of agent access gave no further gain (-0.044 recall, interval -0.122 to +0.033) at 1.5 times the cost. A compact prompt asking the agent to trace callers on top of repo access lowered precision by 0.137 (interval -0.203 to -0.071) with recall not significantly different. The default is therefore repo access with a minimal prompt.

- On this prompt-only benchmark, Perun's review is not measurably better than a plain "review this" prompt, and it costs about 2 times as much per review.
- No difference clears zero: every paired 95% interval below includes 0.
- One Perun pass found slightly fewer bugs than plain (0.326 against 0.360); two independent passes plus union found slightly more (0.393). Neither gap is distinguishable from noise.
- Verified precision (share of flagged issues judged real) was 0.653 for Perun against 0.618 for plain, also not distinguishable.

## Results (89 cases, Sonnet, one replicate)

| Setup | Recall (adjudicated) | Recall vs plain [95% CI] | Verified precision | Precision vs plain [95% CI] | Findings | Cost per review (review only) |
|---|---|---|---|---|---|---|
| Plain prompt | 0.360 | - | 0.618 | - | 220 | $0.043 |
| Perun, single pass | 0.326 | -0.034 [-0.101, +0.034] | 0.653 | +0.035 [-0.038, +0.105] | 196 | $0.080 |
| Perun, two independent passes plus union | 0.393 | +0.034 [-0.022, +0.090] | 0.653 | +0.035 [-0.036, +0.100] | 291 | $0.163 |

Cost including the verifier pass: plain $0.082, single $0.119, two-pass $0.240. Single-pass review cost is about 1.9 times plain; two-pass about 3.8 times.

## Agentic run (90 held-out cases, Sonnet, one replicate)

| Setup | Recall | Precision | Cost per review (basis not recorded) |
|---|---|---|---|
| Prompt only (diff only) | 0.367 | 0.611 | $0.082 |
| Agent with repo access (Read, Grep, Glob) | 0.644 | 0.820 | $0.073 |

Cost basis: this table was first labelled "including verifier", while the high-stakes table below shows the same $0.073 as a bare "cost per review". The raw per-call costs are not committed, so the basis of $0.073 cannot be confirmed; the $0.082 matches the verifier-inclusive plain figure of the 89-case table above, which is a different run. Do not compare the two rows' costs or use them as cost per review.

Agent minus prompt-only: +0.278 recall [+0.189, +0.378], about +0.2 precision. Agent plus the full skill minus agent alone: -0.044 recall [-0.122, +0.033], at 1.5 times the cost. Agent plus compact caller-tracing prompt minus agent alone: precision -0.137 [-0.203, -0.071], recall not significant. This is a separate run from the prompt-only table above.

## Method

- Corpus: 90 held-out real bug fixes from open-source projects; 89 used. One case was excluded because the second Perun pass returned no JSON array. The reviewing model sees only the code change, not the fix. Case answers are read only by the test runner and are not published.
- Model: Sonnet, one replicate (one run per case and setup), test split. Three setups ran concurrently, one case at a time each, each model call under a 900 second alarm.
- Recall: share of known bugs a review named, as judged by an independent verifier model (adjudicated).
- Verified precision: (findings judged real or matching a known bug) divided by findings.
- Two-pass setup: a single pass plus one fresh independent pass, merged; a second-pass finding in the same file within 3 lines of a first-pass finding is dropped as a duplicate.
- Intervals: paired bootstrap over cases, 10,000 resamples, seed 1.
- Runner: [`scripts/bench_corpus.py`](../../scripts/bench_corpus.py).

## Caveats

- One replicate, one model family, one corpus; all intervals include zero. Results are directional.
- Verification is done by a model, not a human.
- The main table measures prompt-only review of a diff; the agentic run measures repo access with one agent and one skill setup, not Perun's multi-step workflows.
- Per-language breakdowns are not reported.

## High-stakes review: one Opus pass (2026-10-09)

A second benchmark used agentic review (a checkout plus Read, Grep and Glob tools, minimal prompt) on 90 held-out bugs, one replicate. It led Perun to replace "two independent passes plus union" with one Opus pass for explicitly high-stakes changes; the normal default stays one Sonnet pass.

| Setup | Recall | Recall vs Sonnet single [95% CI] | Precision | Cost per review (basis not recorded, see above) |
|---|---|---|---|---|
| Sonnet, one pass | 0.644 | - | 0.828 | $0.073 |
| Sonnet, two passes, union | 0.667 | +0.022 [0.000, +0.056] | 0.808 | $0.144 |
| Opus, one pass | 0.744 | +0.100 [+0.022, +0.189] | 0.867 (+0.039 [-0.032, +0.113]) | $0.131 |

Opus costs less than the two-pass union and is the only setup whose recall interval clears zero. Its precision gain does not clear zero. Same caveats as above: one replicate, one corpus, model-judged.

## Optional: repeatability

For N replicate runs of one case, `score_review.py --repeat RUN1.json RUN2.json ...` prints, per finding (same file, lines within 3), the share of runs that report it and the severity agreement with direction (up/down/both/none). Not part of the headline numbers.
