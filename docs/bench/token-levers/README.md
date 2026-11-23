# Token levers: what Perun's token report tells you, next to six peer tools

**BLUF:** on one synthetic session, `token_report.py` finds four levers and ranks three of them by estimated saving: pin the main cache to 1h (35.3% of session input-equivalent, at most), lower the lane tool-call cap (16.8%), auto-compact at 200K (6.0%); the fourth, a top-tier orchestrator, is listed unpriced. A derived variant of the same session adds two more, each firing once and staying quiet once: capping Bash output past `bashOutputMaxChars` (5.6% of input-eq) and trimming a 112 KB `CLAUDE.md` (5.2%); fixture numbers, not real-session claims. None of the six peer README pages (fetched 2026-10-20) describes an idle-cache, lane-tail or auto-compact estimate; at session level only caveman describes a ranking of where tokens go (and publishes no saving for it); `rtk discover` is the narrower case, missed savings in bash commands only. RTK and context-mode compress tool output; Perun compresses nothing, it measures whether that lever applies to a session (tool results past the Bash cap, carried in context) and points at the host setting. Peers beat Perun at per-output compression (RTK, context-mode, Headroom, caveman), at output voice (caveman, ponytail), at time-bucketed spend views (ccusage), and caveman can apply its fixes while Perun only prints them.

Fixture files and `gen.py` are frozen by `SHA256-frozen.txt` (check with `shasum -a 256 -c docs/bench/token-levers/SHA256-frozen.txt` from the repo root); `ledger.jsonl` holds the `preregistered` event the bench-integrity gate requires. There is no model call, so nothing else is preregistered.

Run it: `bash docs/bench/token-levers/run.sh` (offline, free, no model call, about a second). It exits non-zero if a lever, its order or its amount drifts. The frozen files are not edited after the freeze; the tool-result and startup variants are built from them at run time by `overlay.py` (not frozen) in a temp dir, with an empty user config and an empty project so no real `CLAUDE.md` leaks in.

## What the fixture is

`session.jsonl` plus `session/subagents/*.jsonl` are an invented Claude Code transcript: 60 main turns on `claude-opus-5-5`, four `claude-sonnet-5-5` lanes (one with 600 tool calls, three with 40), literal placeholder text, no real content. Every number comes from the arithmetic in `gen.py`, which rewrites the fixture byte for byte. Main: a 12-minute idle gap before every sixth turn, so the 5-minute cache has expired and the whole context is rewritten; context grows from 20K to 256K tokens with no compaction. Total priced at the built-in rates: $11.13 (main $9.25, lanes $1.88).

This fixture shows that the detectors fire and rank correctly. **It does not show how common these patterns are**: the idle gaps and the 600-call lane were put there. Each saving is an upper bound, not a bill: the 1h pin assumes your account gets a 1h cache and every gap under an hour would have kept it alive; the compaction figure assumes a 30K-token context after each compaction; the lane figure ignores the cost of redoing work in a narrower lane. Shares are of main plus lane input-equivalent (input + 1.25x 5m write + 2x 1h write + 0.1x cache read), 3,641,800 here. The three savings overlap, so do not add them.

## What the overlay adds

`overlay.py` copies the frozen session and injects four placeholder tool results on the main thread (only their length matters to the report; the body is the word "synthetic"), then pairs it with a generated `CLAUDE.md`. Two variants:

- `fire`: one 150,000-char Bash result, one 9,999-char Bash result (under the floor, ignored), one 20,000-char Read, one 15,000-char MCP result; a 112,000-byte `CLAUDE.md`.
- `quiet`: the same four results clipped to at or below 10,000 chars (the floor itself or less, never over it); a 2,000-byte `CLAUDE.md`.

The injected results do not change the fixture's token usage, which stays the frozen arithmetic. So the tool-result and startup figures below show that the detectors fire and stay quiet at their floors; they are not a model of what such results or such a file would cost in a real session.

## Detector output (computed by `run.sh`)

These are upper-bound estimates on synthetic data, not measured savings.

| Rank | Lever (as printed) | Estimated saving, input-eq | Share of session | Finding behind it |
|---|---|---|---|---|
| 1 | pin main cache to 1h | at most 1,284,000 | 35.3% | 85.1% of main 5m cache-write tokens follow an idle gap over 5 minutes, all under 1 hour |
| 2 | lower LANE_TOOL_CAP below 150 | at most 611,494 | 16.8% | 1 lane over the shipped 150-call cap; 55.1% of lane input-eq is spent beyond it |
| 3 | auto-compact at 200000 | at most 217,575 | 6.0% | 1 simulated compaction; main context reaches 256K with none observed |
| 4 | orchestrator tier | UNPRICED | n/a | main on a top-tier model carries 69.5% of all input-eq |

Overlay levers, same units (fixture numbers; each saving is an estimate and an upper bound, not a bill):

| Lever (as printed) | `fire` | `quiet` | Floor | Finding behind it |
|---|---|---|---|---|
| cap Bash output with bashOutputMaxChars | at most 203,000 input-eq = 5.6% (estimate), rank 4 | absent | a result counts only over 10,000 chars; the lever needs Bash past-cap carry of at least 5% of input-eq | 1 Bash result of 150,000 chars; the 140,000 chars past the cap, at 4 chars per token, resent for 58 later turns at the 0.1 cache-read weight |
| trim CLAUDE.md (estimate: 50% of its cost) | at most 190,400 input-eq = 5.2% (estimate), rank 5 | absent | needs half the file's cost to be at least 5% of input-eq (the 50% cut is an assumption) | 28,000 tokens (bytes/4) re-read by 4 lanes: 380,800 input-eq, 10.5% of the session; `quiet` has 500 tokens, 0.2% |
| startup remainder (system prompt, tools, skills, brief) | printed as 0.2% of lane startup; no lever | lever printed: 98.2% of lane startup, 33.8% of lane input-eq | lever needs over 50% of lane startup and at least 15% of lane input-eq | what is left of lane startup after the file estimate; the large file explains the startup, the small one leaves the remainder as the target |
| Large Read, large MCP result | info lines only (1 and 1) | absent | same 10,000-char floor | `bashOutputMaxChars` does not cap them; the lines point at offset/limit reads and `MAX_MCP_OUTPUT_TOKENS` |

The `fire` and `quiet` runs share the frozen lanes, so the first three levers of the first table are unchanged in both.

## Questions a user asks, by tool

A peer cell states only what that tool's public README says, fetched 2026-10-20 (URLs in [`docs/standards-index.md`](../../standards-index.md), "Token-lever peer READMEs"). "Not described" means the fetched page does not mention it, not that the tool cannot do it. Peers' own numbers use their own units (bytes, tokens, output tokens, cost) and are not comparable with input-equivalent.

| Tool | What did I spend? | What is wasted? | What should I change, ranked, with saving? |
|---|---|---|---|
| **Perun** `token_report.py` | Main vs lane input-eq, tokens, USD by model and lane (fixture: $11.13) | Idle-gap cache rewrites, lane tail beyond the cap, auto-compact counterfactual, top-tier orchestrator share, Bash output past the cap, auto-loaded instruction files, the startup remainder | Yes, "Top levers" block with saving and share (above); prints the setting to change, applies nothing |
| **caveman** | `caveman stats` token history; `/caveman-stats` for a Claude Code session | `caveman learn` "ranks where your tokens go"; a "Warm cache" feature keeps the prompt cache warm during pauses | `caveman learn implement` applies fixes one diff at a time with approval; the page says `learn` and Warm cache are "Not yet" measured, so no published saving. Published: 33.2% fewer input tokens per session (54 runs); output tokens 4,334 ("Answer concisely.") to 2,693 (`/ultracave`) on 10 questions, 6,983 with no instruction |
| **ponytail** | Band shows per-task cost, tokens, agent time, code reuse; local board over time | Not described | Not described. Published: -53% code, -26% cost, -45% tokens (39 tasks, Opus 5.5, 5 runs, self-run); the page says lower cost is "a side effect" |
| **RTK** | `rtk gain` reports command-output savings, not spend; its page says that "is not the same as cutting your bill by the same amount" | `rtk discover` "Find missed savings opportunities" (bash commands) | Not described. Published: 60-90% on common dev commands, tokens estimated as bytes/4, Bash tool calls only |
| **context-mode** | `ctx_stats` shows context savings and tokens consumed; statusline shows "$ saved this session" | Not described | Not described. Published: "315 KB becomes 5.4 KB. 98% reduction" (examples, in KB, not averages); last 15,848 characters of the page were not read |
| **Headroom** | `headroom savings` and `headroom dashboard` show tokens saved | CacheAligner flags volatile content that would bust a prefix cache | Not described. Published: 20% fewer tokens for coding agents, 60-95% for JSON; "Savings scale with how repetitive the payload is" |
| **ccusage** | Daily, weekly, monthly, session and 5-hour-block reports in USD, cache creation and read shown separately, per-model `--breakdown` | Not described | Not described |

## Where a peer beats Perun (honest losses)

1. **Per-output compression.** RTK, context-mode, Headroom and caveman's "Read less" shrink what a tool returns before the model sees it. Perun has none and removes nothing. It does measure tool-result size (length only) and, when Bash output past the cap is a large enough share of the session, ranks a `bashOutputMaxChars` lever and points at the host setting. A cap truncates, which is not the same as compressing, and the saving is an estimate; Perun does not measure how much any peer's compression would save.
2. **Output voice and less code.** caveman and ponytail change what the model writes; Perun points to them and does not measure it.
3. **Spend over time.** ccusage reports by day, week, month and billing block; `token_report.py` takes one session and a `--since` cut.
4. **Applying the fix.** caveman's `learn implement` edits your setup with approval; Perun prints the lever and the setting.
5. **Same problem, other fix.** caveman's Warm cache attacks idle cache expiry by keeping the cache warm; Perun's estimate assumes the 1h TTL pin. Neither is measured against the other here.

Unverified: whether any peer finds the lane-tail or compaction levers outside what its README describes, and how any of these estimates compare with a real bill. Real-session prevalence of each lever is not shown by this fixture.
