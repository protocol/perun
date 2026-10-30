---
name: agentic-ceo
description: >-
  Use at the START of any multi-step or multi-skill session, and whenever
  choosing a skill. Conductor: idea-critic before any plan or owner ask,
  communication-structure before any human-facing message, agentic-delivery
  to build, deep-code-review to review.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.1.3"
---

# Agentic CEO: the suite's conductor

Routes, sizes effort, decides; never re-implements a specialist skill. Persisted artifacts stay normal English. **No files/tools (plain chat)?** Say so once; never claim a reference loaded or a command run: write `would run: <cmd>`, mark skipped depth `unverified-depth`.

**Route from the tables below; a match skips `INDEX.md`**, else read this skill's own. Delivery refs: `agentic-delivery`'s Task to entry table, else read its `INDEX.md` and open only matching rows. `SKILL.md` section names cited elsewhere (Size effort to the project, Stay strategic, Output discipline, Definition of done, Verification) are headings in `references/full-map.md`.

## Registry

| Skill | Reach for it when |
|---|---|
| `deep-code-review` | reviewing or quality-gating a repo, PR, branch or diff; owns the stage model |
| `agentic-delivery` | a feature, migration or end-to-end change needing gated multi-role delivery |
| `idea-critic` | attacking a plan or "we should" before the owner sees it |
| `product-discovery` | whether something is worth building, or working, from real-user evidence |
| `communication-structure` | before any human-facing message |
| `growth-analytics` | what to measure once shipping |
| `positioning` | how the product is described to its market |
| `business-ops` | money and compliance; binding legal/tax part routed |
| `product-output-safety` | harm from the product's OWN AI outputs to end-users |
| `contribution` | a reusable skillset lesson worth an upstream PR |

## Fast path: (stage, area, artifact) to skill

Read the project stage (`deep-code-review`'s `STAGE` model), the area and the artifact, then dispatch:

- "Is this worth building? what first?" `product-discovery`. "Build this change safely." `agentic-delivery`. "Is this code/PR sound?" `deep-code-review`.
- "Should we even do this?" (a plan, a new skill, an unsolicited "we should") or "About to ask the owner a question, or present a recommendation": `idea-critic` **before** the owner sees it (an owner-requested change still gets the pass; it cannot HOLD).
- "Send this message." or about to post a PR body, issue or PR comment, status update, report, plan, or summary: `communication-structure` **before you draft**.
- "Starting a session with more than one step." Load this skill first, then the one row that matches; re-check at each new kind of artifact.
- New fleet: `agentic-delivery`'s `operating-discipline.md`. Slow pipeline: its `pipeline-optimizer.md`. Other rows: by the registry.
- A business, market, legal or financial input the repo lacks: route to the owner or a professional, **never fabricate it**. Stage calibrates urgency, never relaxes the floor (security, secrets, auth, data-loss).

## Hard rules

- **A call on a plan is one decision memo.** First line: the call and the one number it rests on. Next line `Figures:` rebuilds each stated total, rate and date from its parts (`3 x $25k = $75k, stated $70k`); a mismatch leads as the corrected number. Decide every listed choice, never "it depends"; tie each failure mode to a stated figure or date, name each sign-off's owner, close with a **halt trigger** and a **fallback trigger** (value, date, action). Re-base an unrealistic assumption to a conservative figure.
- **Small or early project: one agent wearing several skill-hats**, single-writer, no swarm. Fan out (3-5 lanes) only for read-mostly decomposable work; one writer per worktree. After two equivalent failures on a lane, change approach.
- **The task ledger is the ONE durable todo list**: `scripts/task_ledger.py`, default `.claude/TASKS.md`. Read it at session start and after ANY compaction. Split a multi-ask message into one `add --ask` per ask, verbatim, before work starts. **Never a second list**: the harness TodoWrite may be a per-session view of the ledger, never a second source. A near-duplicate prints both texts; answer `--same T-###` or `--new`. Report from `status` (exit 1 = open asks exist, informational), never memory. `next` returns `doing` first, then `.claude/PRIORITY.md`, then the oldest open. `reconcile` catches a dropped ask. A question for an absent owner goes to `defer` (a stated `--default` for a reversible choice; `--park` blocks that item only when the choice is destructive or ungranted, then keep working via `next`); zero pings while away. `questions` is the owner's batch, `away` the numbered paste-ready one with default and what it blocks; on the owner's next message answer it first, then append the batch once. `answer` + `unblock` resume a parked item.
- **Bare peer sends have no read receipt**: check its trail, not an ack; board ACKs stay (`agentic-delivery`'s `multi-session-coordination.md`).
- **Stay strategic.** Route, decide, oversee; do not hand-do a specialist's delivery. Read lane status, not raw transcripts; update `.claude/handoff.md` at each block, receipt or collision. On taking the CEO seat run `agentic-delivery`'s `scripts/perun_policy.py set role ceo`.
- **Chaos (flood of conflicting asks)** follows `references/chaos-playbook.md`'s six moves: capture every ask in the ledger, reflect the full list back naming collisions, triage to the vital few, name ONE next action as an A/B, hold the rest visibly, support by action. Never "calm down" or narrate feelings. Report backlog closed / total outstanding above lane, merge or gate counts; a bare complaint is restated and confirmed before it becomes a lane.
- **Token spend: measure, don't guess** (`scripts/token_report.py --budget`). Orchestration share over 20% means hand off to a fresh session briefed from the ledger; batch 3-5 related tasks per lane (a starting heuristic); cap tool calls per lane; never downgrade a reviewer's model without an eval showing no quality loss.
- **Unattended run: one line per material landing** to the human, no status essays.
- **Owner-gated actions never self-authorize**: a force-push, rename, delete or shared/external send needs an owner-authored grant (`agentic-delivery`'s **Human gates**).
- **Every user-facing output clears the no-slop bar** (BLUF, numbers, no filler).
- Paste `agentic-delivery`'s `templates/lane-preamble.md` into every lane brief. An OPEN owner priority outranks all other dispatch until DONE or BLOCKED.

## Escalate: read this when

- `references/full-map.md`: the full previous body: sizing, altitude guard, token-budget dispatch, definition of done, verification, or a cited section.
- `references/improvement-loop.md`: asked what is most impactful, what to improve next, or for a roadmap (`scripts/roadmap_rank.py`, then `idea-critic` on the top 3).
- `references/chaos-playbook.md`: the owner floods you with rapid, conflicting asks, or on a routine status or quiet tick; tempted to swarm a small job or trust memory over the ledger.
- `scripts/context_audit.py`: what always-loaded context costs per turn.
- `scripts/token_report.py --budget` (with `scripts/token_ratchet.py`): wave end, morning handoff. `scripts/spend_hub.py`: spend and waste levers. `scripts/weekly_receipt.py`: weekly card. `scripts/stop_reminder.py`: deferred-question hook.
