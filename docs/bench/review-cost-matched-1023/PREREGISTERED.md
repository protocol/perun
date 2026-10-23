# Pre-registration: review cost on a matched harness, shipped /review against the shipped toolkit agent (frozen before any paid call)

Status: built and dry-run only. No paid call has been made. Spend to date: $0.

## Why
`review-cost-v2-1019/confirm.py` ran the toolkit (TK) arm with `--system-prompt`, which replaces the whole Claude Code system prompt. The Perun arms (V2s, BASE) ran on the default harness plus a cold environment prefix. A review-cost ratio against TK therefore mixes method cost with harness cost. On the one matched pair in that bench, V2 (an inlined Perun prompt, also passed as `--system-prompt`) against TK, the mean review cost was $.01887 against $.01791, 1.05 times (means of the 22 non-error call costs per arm in `../review-cost-v2-1019/ledger.jsonl`). The earlier ratios (3.4 times in H7b, whose TK arm was also a `--system-prompt` run) are not harness-matched. This bench measures the shipped products on one harness.

## Arms (22 held-out cases of `../review-cost-v2-1019/split.json`, one run per case, one retry on error)
Both arms: default Claude Code system prompt, `--exclude-dynamic-system-prompt-sections`, no `--system-prompt`, `--setting-sources project,local --strict-mcp-config`, `claude-sonnet-5-5`, read-only tools, the same output-format paragraph (`bench_corpus.PRODUCER`), `--max-budget-usd 0.30` per call.
- PERUN: the repo's shipped `commands/review.md` as `.claude/commands/review.md` plus the skill in `.claude/skills/deep-code-review/`, prompt `/review FILE ./change.patch`. Tools Read, Grep, Glob. The command sha256 at run time is written to the ledger (`run_start`), because the file is not frozen here.
- TK: the Anthropic pr-review-toolkit plugin, fetched at run time from its public upstream (this bench does not vendor the plugin; it fetches it pinned): `https://raw.githubusercontent.com/anthropics/claude-plugins-official/ce721c1f1d5da2c281588818e072ae01a05d2e73/plugins/pr-review-toolkit/` (the latest upstream commit touching the agent as of 2026-10-23). `matched.py` downloads `.claude-plugin/plugin.json` (sha256 `7aa64c91a9316ef3641df115414c07c7caee8f48368815dc2950483598321865`) and `agents/code-reviewer.md` (sha256 `019395c3ce457460115cc703e2f4a86fed4bbe560dc58355051c4d877155d366`), refuses any mismatch, and copies them into a temp workspace loaded with `--plugin-dir`. The `code-reviewer` agent is invoked through the Agent tool as the plugin ships it, so it runs as a subagent on its own system prompt while the main session stays on the default harness. Tools Read, Grep, Glob, Agent.
Deviations from "as it ships": the agent's frontmatter `model: opus` is replaced with `model: inherit` in the temp copy so both arms use one model (the body is asserted identical to the fetched original). The fetched agent body is longer than `review-cost-v2-1019/tk_system.txt` (it gained a "When to invoke" section), so this bench measures the current shipped text, not the V2 text. Not measured: the plugin's `/pr-review-toolkit:review-pr` command (it fans out to up to six agents).

## Metrics and judging
- Quality: pooled F1 of free PCSS judges exactly as `driver.py` (DeepSeek-V4-Flash, GLM-5.2 tie-break); paired case-level bootstrap, 10000 resamples, seed 1, 95% percentile CI, F1(PERUN) minus F1(TK), cases where both arms completed and were judged.
- Cost: mean dollars per case from the ledger (`total_cost_usd` of every call for the case, retries included). Tokens are reported but do not decide: the result `usage` of a delegating session may not include the subagent's tokens.

## Keep rule (`confirm.decide`, the V2 rule with dollars in place of tokens)
- A (tie at lower cost = win): F1 difference point >= 0, CI lower bound >= -0.05, and cost ratio PERUN/TK <= 1.0.
- B (clear quality win): CI lower bound > 0 and cost ratio <= 2.0.
Keep if A or B, else REVERT. A failed read is reported, not rerun.

## Spend and stops
Hard cap $4 by ledger, per-call reserve $0.30 checked before each call, stop at plan utilization >= 0.8 or on a missing reading (fail closed), both via `confirm.call`. Estimate: 44 reviews plus one quota probe, at $.033 (V2s arm) to $.074 (BASE arm) per default-harness review in the V2 ledger, is $1.5 to $3.3; point estimate $2.4. Retries could add about 10 percent.

## Procedure
1. `python3 matched.py` (dry-run, default): builds the PERUN workspaces and asserts each arm's files; offline, so the TK check is skipped with a message unless a fetched plugin dir is given (`matched.py fetch DIR`, then `matched.py dry-run DIR`, both free). `run` fetches and hash-checks the plugin before any paid call.
2. `python3 matched.py run 1`: one-case smoke of both arms, plus the probe, about $0.15. It checks that the slash command and the plugin agent load. A harness fault (command not found, agent not invoked) is fixed and disclosed in a DEVIATIONS note, the case is re-run, and no method text changes. Smoke results are kept, not discarded.
3. `python3 matched.py run`, then `judge`, then `verdict` (writes `results.json`).

## Stated in advance
- n=22 gives a wide CI; a real gain can fail by noise.
- Different mechanisms: PERUN is one session, TK is a main session plus a subagent. That is how each ships and is the thing measured.
- The TK text is pinned to one upstream commit; if upstream moves, the pin and hashes still select the same text.
- One model, one run per case, judges are not Claude.
