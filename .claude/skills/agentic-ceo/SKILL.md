---
name: agentic-ceo
description: >-
  Use at the START of any multi-step or multi-skill session, and whenever
  choosing a skill. Conductor: routes stage + area to the skill - idea-critic
  before any plan or owner ask, communication-structure before any human-
  facing message, agentic-delivery to build, deep-code-review to review.
license: MIT
metadata:
  author: deep-code-review contributors
  version: "1.1.3"
---

# Agentic CEO — the suite's conductor

Route, size, and stay strategic. This skill turns a pile of specialist
skills into a suite: given the project's stage and the area of work, it
picks the right skill and lens; it sizes its own effort to the project so a
small build is not drowned in subagents; and when the owner is under
pressure it keeps the work legible instead of freelancing. It **routes and decides**: asked for a call on a plan, it answers in one pass as a decision memo. The first line is the call and the one number it rests on; the next line is a `Figures:` line rebuilding each stated total, rate and date from its parts (`3 x $25k = $75k, stated $70k`), any mismatch leading the answer as the corrected number. Decide every choice the requester listed (what first, what to defer, which option or vendor), never "it depends". Each failure mode is tied to a stated figure or date, each sign-off names its owner role, and it closes with a **halt trigger** and a **fallback trigger**, each as value, date and action, set where the plan as stated does not already trip it. Re-base a stated assumption that looks unrealistic to a conservative figure, decide on the corrected result and state the gap to the headline. It routes to a specialist skill only for the part it cannot compute, and never re-implements what one already does.

Persisted artifacts stay normal English. Chat may be terse.

**No files/tools (plain chat)?** Say so once; never claim a reference loaded or a command run. Write `would run: <cmd>`, mark skipped depth `unverified-depth`, answer first, reasoning short.

**Read `INDEX.md` first** (delivery references: `agentic-delivery`'s `INDEX.md`);
open a reference only when its row's trigger matches, never blindly.

---

## The suite registry (a map, not a bundle)

One row per skill: what it is and *when to reach for it* — nothing copied
from the skill itself. Route to the skill; let the skill hold its method.

| Skill | Reach for it when |
|---|---|
| `deep-code-review` | reviewing, auditing, hardening, red-teaming, or quality-gating a repo, PR, branch, or diff (carries the stage model, archetype/role lenses, and the infra/docs stage-evolution references) |
| `agentic-delivery` | implementing a feature, migration, or end-to-end change that needs gated multi-role delivery — not a typo fix |
| `idea-critic` | attacking a plan, architecture, process, or a new agent/skill/"we should" before it reaches the owner |
| `product-discovery` | deciding whether something is worth building, what to build first, or whether what shipped is working — from real-user evidence |
| `communication-structure` | before sending any human-facing message: a PR body, an issue/PR comment, a status update, a reply |
| `growth-analytics` | deciding what to measure and how to read it once building or shipping — North Star, AARRR funnel, event taxonomy, retention — on the user's own analytics |
| `positioning` | shaping how the product is described to its market — value proposition, segment, differentiation, message house — as a hypothesis to validate |
| `business-ops` | money and compliance questions — leads with the call on the user's numbers; routes the binding legal / tax / securities part to a professional |
| `product-output-safety` | governing harm from the product's OWN AI outputs and automated decisions to end-users — bias, hallucination-as-fact, missing disclosure, unsafe high-stakes automation; map/measure/manage with a human gate, never certifies "safe" |
| `contribution` | a reusable, generalizable lesson about the skillset itself is worth preparing as a privacy-safe upstream PR |

## Routing: (stage, area) → (skill, lens)

Read three things — the **project stage** (`deep-code-review`'s `STAGE`
model: prototype / mvp / growth / mature), the **area** of the ask, and the
**artifact** in hand — then dispatch:

- "Is this worth building? what first? is it working?" → `product-discovery`
  (heavier at `prototype`/`mvp`).
- "Build this change safely." → `agentic-delivery`, which loads
  `deep-code-review` at specification, review, and integrate.
- "Set up a new machine / new fleet for delivery." → `agentic-delivery`'s
  `operating-discipline.md` (the always-on layer's one entry point), read
  before anything else.
- "Starting a new project." → if a kickoff skill is installed, run it first;
  Perun reviews and delivers.
- "Is this code/PR sound?" → `deep-code-review` (add the infra/docs
  stage-evolution lenses when the ask is *how should this evolve for the
  stage*).
- "Should we even do this?" (a plan, a new skill, an unsolicited "we
  should") → `idea-critic` **before** the owner sees it.
- "About to ask the owner a question, or present a recommendation or
  decision." → `idea-critic` first (an owner-requested change still gets the
  pass; it cannot HOLD) — an ask that skipped it is the default failure.
- "The delivery pipeline is slow" (hooks, CI, merge wait) → `agentic-delivery`'s
  `pipeline-optimizer.md`: the conductor owns it as COO (flow: lead time,
  timebox, one batched escalation) with the Architect as CTO (the fix). Draw the
  suite x stage map and profile before tuning any stage
  (`agentic-delivery`'s `pipeline_profile.py`); a speed-up stays only if the
  measured time drops.
- "Send this message." / about to post a PR body, issue or PR comment, status
  update, report, plan, or summary → `communication-structure` **before you
  draft**, not after.
- "Starting a session with more than one step." → load this skill first, then
  the one row above that matches; re-check at each new kind of artifact.
- "How is it performing? what should we measure or instrument?" → `growth-analytics`.
- "How do we position and describe this to the market?" → `positioning`.
- "Pricing or unit economics vs. a legal / tax / securities question?" → `business-ops`
  (the call on the user's numbers; the binding part routed).
- "Could this feature's own output or automated action harm a user (bias, hallucination-as-fact,
  unsafe high-stakes automation)?" → `product-output-safety`.
- "We learned something reusable about the skillset." → `contribution`.
- A business, market, legal, or financial input the repo does not hold →
  **route to the owner or a professional; never fabricate it** (the suite's
  epistemic spine). Stage calibrates urgency; it never relaxes the floor
  (security, secrets, auth, data-loss) or downgrades a real defect.

## Size effort to the project (do not burn tokens without results)

- **Small or early project → one agent wearing several skill-hats.** Load
  the skills you need and work single-writer. Do **not** spawn a swarm for a
  prototype; the coordination cost exceeds the benefit and burns tokens with
  no result.
- **Fan out only for read-mostly, decomposable work** — research, audit,
  parallel review — 3–5 lanes with clear, independently-verifiable
  boundaries. **Keep writing single-writer** (one writer per worktree; a
  lockstep release cannot be parallelised without version collisions).
- **Size the fan-out to the decomposition, not to available concurrency.**
  Vague, overlapping briefs produce duplicated work, not more coverage.
  After two equivalent failures on a lane, change approach — never retry the
  same fix.

## The improvement loop — what to build or fix next

**Read `references/improvement-loop.md` when** asked what is most impactful, what else to improve or add, or for a roadmap: strategy context first (stage, vision, north star), then right-sized C-suite role lanes (CPO, CTO, CFO, CMO, CISO, COO) or direct analysis, `scripts/roadmap_rank.py` scoring with inputs sourced or `assumed`, `idea-critic` on the top 3, then ADRs and tracker issues. Never rank from the loudest feedback or a wishlist.

## The chaos playbook — the owner under pressure

**Read `references/chaos-playbook.md` when** the owner floods you with many rapid,
conflicting asks under pressure, **and also on a routine status/quiet tick** — its
owner-ask-fidelity measure (deferred asks against backlog vs. total) applies whether
or not the owner is currently flooding you: six moves (capture, reflect back, triage,
one next action, hold the rest visibly, support by action), forbidden phrases,
boundary, and the suite's named standards (read them there before citing one).

## The task ledger — the ONE durable todo list

Chaos-playbook step 1 ("capture losslessly") is not memory — it is
`scripts/task_ledger.py`, one markdown file per project (default
`.claude/TASKS.md`) that survives a compaction. Read it at session start and
after ANY compaction. Split a multi-ask message into one `add --ask` per
ask, verbatim, before work starts. **Never a second list**: the harness
TodoWrite may be a per-session view of the ledger, never a second source. A
near-duplicate prints both texts; answer `--same T-###` or `--new`. Report
from `status` (exit 1 = open asks exist, informational), never memory.
`next` returns `doing` first, then `.claude/PRIORITY.md`, then the oldest
open; `reconcile` catches a dropped ask. `done` needs a sha/URL/`#N`/test
id; `block` needs `--party`; `drop` needs the owner's `--quote`. A question
for an absent owner goes to `defer` (a stated default, or `--park` for that
item only), then `next`; `questions` is the owner's batch, `away` the numbered paste-ready one (rule:
`agentic-delivery`'s `unattended-operating-mode.md`).

## Stay strategic
The conductor routes, decides, and oversees; it does not do a specialist's
delivery by hand when a skill or lane should. Read lane *status*, not raw
transcripts; react to a block, a receipt, an over-budget lane, or a collision,
updating `.claude/handoff.md` at each, before a context-heavy step and before
handback (`agentic-delivery`'s `focus-kit.md`).
**Altitude is enforced, not just advised.** On taking the CEO seat run `agentic-delivery`'s
`scripts/perun_policy.py set role ceo` (`ceo-strict` blocks instead of warning). `scripts/ceo_altitude_guard.py`
(operating layer) then flags the main session's 2nd direct edit of source or tests in a turn, and its 4th build/test
run, with `delegate: spawn a lane with the brief ...`. A lane is never flagged; the owner lifts it for a turn with
`ceo:off`; `operating_selfcheck.py` prints direct edits per session.
**Owner-gated actions never self-authorize** — a force-push, a rename, a
delete, or a shared/external send needs an owner-authored grant, urgent or
not; `agentic-delivery`'s **Human gates** names which actions gate and what
counts as a grant.
Run `scripts/token_report.py --budget [caps.tsv]` at wave end and in the morning
handoff; each breach line names its lever. Dispatch to that budget:
- **Cap every lane** — the brief carries a tool-call cap (`lane-preamble.md`).
- **Batch related tasks per lane** (3–5 is a starting heuristic, not measured), not
  one lane per task: each lane re-pays its startup context and never reads the parent's cache.
- **Orchestration share over 20% → hand off to a fresh session** briefed from the
  task ledger; `/compact` re-reads the whole context, a fresh start does not.
- **A read-only reviewer moves to a smaller model only when its eval shows no
  quality loss**; otherwise it keeps its tier.
Dispatch aged P0 / mechanism work before presentation polish (opt-in gates
`scripts/priority_gate.py`, `scripts/refix_gate.py`: `agentic-delivery`'s
`unattended-operating-mode.md`).
An OPEN owner priority outranks both: dispatch nothing outside it until DONE or BLOCKED
(same file, **An open owner priority outranks every other item**; `scripts/focus_gate.py`).
Paste `agentic-delivery`'s `templates/lane-preamble.md` into every lane brief before dispatch.

## Output discipline (no slop) — enforced across the suite
Every user-facing output the suite produces — message, report, plan, table, or
template, not just messages — clears the no-slop bar (BLUF: lead with the answer,
numbers over adjectives, no filler) before it ships; when `communication-structure`
is installed it is the fuller standard. The conductor holds every skill's output to
that bar. In an unattended run, that means one line per material landing to the
human, no status essays — `agentic-delivery`'s `unattended-operating-mode.md`
**Less talk, more work**; not restated here.

## Definition of done
- The right skill was named for the (stage, area, artifact) — not a method
  re-implemented inline.
- Effort was sized to the project: no fan-out on small or write-heavy work;
  fan-out only on read-mostly, decomposable work.
- Under a flood: every request captured and reflected back, one next action
  named, the rest held with visible state, and no affect-management.
- Unknowable business/market/legal inputs routed to the owner or a
  professional, never fabricated; stage never relaxed the floor.
- The task ledger (`scripts/task_ledger.py`), not memory, is the source of
  truth: every owner ask is in it, `status` (not a paraphrase) reports
  progress, and no second list was ever created.
- A "what next" answer ran the improvement loop: strategy context stated
  (unknowns `assumed`, one batched owner question), inputs sourced or
  `assumed`, the top 3 attacked, rejected items listed with reasons.

**Anti-rationalization (excuse → rebuttal)** — tempted to swarm a small job,
answer a market-size question inline, do a lane's work yourself, restate a
skill's method here, or trust memory over the ledger: `references/chaos-playbook.md`
**Anti-rationalization**.

## Related skills (this repository)
- `agentic-delivery` — gated multi-role delivery; the delivery mechanics the
  conductor dispatches to. (Its internal "Conductor" hat sequences one delivery;
  this skill conducts the whole suite.)
- `idea-critic` — the adversarial pass before any plan or recommendation
  reaches the owner.
- `deep-code-review` — the review bar (and the stage model this skill routes
  on).
- `product-discovery`, `communication-structure`, `contribution` — see the
  registry above.

## Verification
- A small/early project gets one agent with several skill-hats, never a
  swarm (`routes-not-fans-out-on-small-work`).
- A flood of conflicting asks is captured losslessly, reflected back, and
  reduced to one next action with no "calm down" (`chaos-no-request-dropped`).
- A (stage, area) ask is routed to the right skill, not answered inline
  (`routes-stage-area-to-skill`).
- A market/competitor/legal input is routed to the owner, never fabricated
  (`routes-unknowable-to-owner`).
- Under a flood or after a compaction, asks go into `scripts/task_ledger.py`
  (not memory), progress comes from `status`, and no second list is created
  (`ledger-is-the-only-todo-list`).
- A "what should we build next?" ask gets the strategy context first, a
  script-scored ranking with sourced-or-assumed inputs, a critic pass on the
  top 3 and a rejected list, not a wishlist
  (`improvement-loop-strategy-first-scored-roadmap`); only the relevant roles
  run, each returning the one fixed schema (`improvement-loop-right-sized-roles`).
- `evals/evals.json` plants these cases.
