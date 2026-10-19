# Token cost tips for teams

**BLUF:** the biggest savings come from sending less context, using the cheapest model tier that
clears its own gate, and measuring before you cut. Each tip below carries a number already
measured in this repository; adapt the settings to your own fleet and re-measure.

1. **Load less method text.** Must-read method files for a review dropped from 65,903 to 28,025
   estimated tokens (FULL repo review: 87,137 to 36,096, about 57% less), and CI blocks growth.
   See [README](../README.md), "What you get".
2. **Cap what every turn resends.** Set `bashOutputMaxChars` (start at `10000`) and
   `skillListingMaxDescChars` (start at `300`, default `1536`); use `"name-only"` for skills a
   project never needs. See [`host-enforcement.md`](../.claude/skills/agentic-delivery/references/host-enforcement.md), "Per-turn token levers".
3. **Default to the cheapest tier that passes its gate.** Mechanical steps get the cheapest tier at
   low effort; build and audit lanes get mid; only verify and judge stages get top at high effort.
   See [`model-tiering.md`](../.claude/skills/deep-code-review/references/model-tiering.md), "Route delivery lanes by work type and stage".
4. **Do not use the cheapest tier for judgment.** A cheapest-tier dedupe lane matched 13 of 23
   findings to unrelated issues by keyword and reported comments as posted that did not exist; a
   mid-tier lane found zero such comments. Same file, same section.
5. **Do not let every lane consult a stronger model.** Parallel lanes' own consults were the
   dominant top-tier spend, about the cost of 3 to 4 mid-tier lanes per consult. Omit the consult
   tool from lane toolsets. Same file, same section.
6. **Cache inside one model.** Cache reads cost 0.1x base input on most models (writes 1.25x at a
   5-minute TTL); switching models mid-task forfeits the cached prefix. See
   [`model-tiering.md`](../.claude/skills/deep-code-review/references/model-tiering.md), lever 2.
7. **Keep hand-backs short.** Lane narration multiplies across a fleet; cap hand-backs and report
   status first. See [`host-enforcement.md`](../.claude/skills/agentic-delivery/references/host-enforcement.md), "Subagent handback".
8. **Fewer, longer-lived lanes.** Each subagent start pays the project's instruction files again;
   resume a worktree instead of spawning short lanes. See `model-tiering.md`, same section as tip 3.
9. **Measure per session, then per project.** `agentic-ceo/scripts/token_report.py --session
   <transcript> --budget` reports main versus subagent tokens and flags lanes over their caps;
   `/perun:cost-retro` turns that into "what would have been cheaper". Add `--advise` for rule-based
   advice (each rule is one measured signal, one lever, one link back here); a lever you already set is never recommended.
10. **Attribute spend before capping it.** Name keys `<tracker-project-id>-<handle>`, prefer one key
    per project, set alerts first, caps last, and total an export with
    `agentic-delivery/scripts/spend_report.py`. See [`operating-discipline.md`](../.claude/skills/agentic-delivery/references/operating-discipline.md), item 9.
11. **Compact on your schedule, not mid-task.** `/clear` between unrelated tasks, `/compact` at
    natural breaks, and set the auto-compact window (`/autocompact 200k`, or `autoCompactWindow` in settings; valid range
    100K to 1M) so a long session compacts before it gets expensive. Every compaction rewrites the cached prefix, and `/context`
    shows what fills the window. Docs: [Manage costs](https://code.claude.com/docs/en/costs), [Commands](https://code.claude.com/docs/en/commands), [Settings reference](https://code.claude.com/docs/en/settings-reference).
12. **Keep MCP tool definitions out of every turn.** Tool search defers MCP tool definitions by default, so leave
    `ENABLE_TOOL_SEARCH` unset (`false` loads them all upfront), disable servers this project never calls (`/mcp`), and
    prefer a CLI such as `gh` where one exists. Claude Code warns at 10,000 tokens of MCP output (`MAX_MCP_OUTPUT_TOKENS`,
    default 25,000). Docs: [MCP](https://code.claude.com/docs/en/mcp), [Manage costs](https://code.claude.com/docs/en/costs).

An estimate is not a billed total: mark anything you cannot price `UNPRICED`, never zero.
