# Agentic delivery: full map

Read this when a delivery needs more than the SKILL.md fast path: the full gate table with every hard condition, the role and conductor rules, worktree and occupancy detail, standing-grant and human-gate wording, the output contract or the failure rules. This file is the complete previous SKILL.md body, unchanged; SKILL.md keeps the hard rules and the routing for every reference.

Delivery overlay — a **pattern**, not a
runtime or a standing swarm. Installing, recommending, or self-verifying
this overlay (contract, planted-defect proof, privacy check):
`references/install.md` **Verification**.

It does **not** replace `deep-code-review` — review is the bar, this is how work
reaches it. Do not run a second delivery OS (Superpowers, gstack `/ship`, a
private factory) on the same repo; compose those packs for TDD/brainstorm *or*
this pack for gated multi-role work, always `deep-code-review` for audit.

Persisted artifacts (code, PR bodies, ADRs, commits) are **normal English**;
chat may be terse.

**No files/tools (plain chat)?** Say so once; never claim a reference loaded or a command run. Write `would run: <cmd>`, mark skipped depth `unverified-depth`, answer first, reasoning short.

**Task to entry** — a match skips `INDEX.md`; else read it and open only matching rows.

| Task | Open |
|---|---|
| Land PRs as a train | `scripts/merge_train.py`, `scripts/train_land.sh`; depth `references/merge-queue-worktrees.md` |
| Fix a red gate or union | `references/gate-epistemology.md`, `references/red-gate-triage.md`; repeat flake: `scripts/flake_ledger.py` |
| Start a lane | `templates/lane-preamble.md`: paste into every lane brief |
| Isolate a lane's worktree | `references/worktree-isolation.md` |
| Slow pipeline (hooks, CI, merge wait) | `references/pipeline-optimizer.md`; `scripts/pipeline_profile.py map` first; claims: `scripts/outcome_claim_guard.py` |
| Verify or relay a lane's result | `references/verification-handback.md` |
| Long session, compaction, new session, memory or docs bloat | `references/focus-kit.md`: update `.claude/handoff.md` (`scripts/focus_kit.py handoff set`) at each gate, before a context-heavy step, before handback |
| New machine or new fleet | `references/operating-discipline.md` first: always-on layer entry point, `install.sh --with-operating-layer` snippet, `scripts/operating_selfcheck.py` |
| PR state | `scripts/pr_state.py <n>`: head, checks, review, behind, train; exit 0 green, 1 red, 2 pending |
| Hand off PRs/issues | `scripts/premise_check.py <n>...`: merged/closed PRs, cites absent at HEAD; exit 1 |
| Commit a changelog fragment | `.githooks/pre-commit` runs `scripts/ci-gates.sh fragments`: marker and heading rules |

---

## When to Use

- A change spans implementation plus QA or security, or more than one writer
  would collide.
- The owner asked for a feature, migration, or release — not a one-line fix.
- `./install.sh --recommend` named this overlay for the target.

**Do not use** for a typo, a docs nit, or a repo that already runs another
delivery pack. One conductor. Hats, not headcount. Before any agent-originated
"we should" reaches the owner, load `idea-critic` if installed.

---

## Operating model

Smallest sufficient team. Hats fire from risk — not standing roles, never a
bot or profile per role; one worker wears several compatible hats on a small
change. The full roster (per hat: trigger, gate owned, build
discipline, `deep-code-review` lens) is `references/roles.md`. The core hats:

- **Conductor** — intent, scope, task graph, merge plan, evidence roll-up.
  Never self-approves.
- **Product Analyst** — turns a real signal (feedback, an owner goal) into a
  testable spec + feedback-coverage entry (`references/roles.md`). Recommends;
  owner decides scope. Feeds G0/G1.
- **Builder / Implementer** — implements in a dedicated worktree to the build
  bar in `references/roles.md`. Never wears independent QA, security, or
  release-approval.
- **Evil Twin** — attacks a plan or an agent-originated "we should" before the
  owner sees it (G0/G1); a lead to verify, not an oracle. Mechanism in the
  `idea-critic` skill.
- **QA** — independent, exact-revision functional / regression / a11y /
  state-coverage / performance verification.
- **Security** — independent AppSec / privacy / supply-chain (Red on paper +
  authorized testbeds; Blue fail-closed; White scope/ROE). Physical /
  social-engineering assessment is **human-led under written ROE**; an agent
  may only plan, tabletop, and analyse owner-supplied evidence.

Builder never reviews builder. Architect, UX & Design, Release, and Docs fire
from the same risk triggers — `references/roles.md` maps each to its gate and
lens.

### Conductor operating rhythm

The Conductor's attention is **event-driven, not polled.** It is triggered by
exactly four things: a lane blocking a gate, a lane returning a receipt (the
output contract, at an exact SHA), a lane exceeding its stated time/cost budget,
or a preflight collision (*Worktrees and occupancy*, below). Between those
events the Conductor reads status only — not a lane's raw tool-call transcript —
and does not do the lane's work itself, as a subagent returns a
summary, its context isolated from its parent's
(Anthropic, context engineering for AI agents).

**Size the fan-out to the decomposition, not to available concurrency** —
never spawn more lanes than there are independently-verifiable objectives —
and **pilot before full fan-out** on a wide, mechanical batch. Default tiers,
the duplicated-work failure mode, and the pilot procedure:
`references/fanout-host-sizing.md`.

**Escalate a lane, don't just retry it** — after two equivalent failures on the
same lane, change approach; the cost-ordered ladder (reframe, decorrelate,
stronger tier): `references/fanout-host-sizing.md` **Escalate a lane**.

**Ready-queue sweep on every trigger; review gate** — `scripts/review_gate.py`, `references/merge-queue-worktrees.md`.

**Worked-lesson ledger** — seven themed files, indexed one line each in
`references/fast-agentic-delivery.md`. Open `references/dev-env-ownership.md`
when a lane serves a dev server, re-runs a generator or ratchet, or shares files
under an ownership map; `references/unattended-trackers.md` when closing tracker
issues or running a multi-hour work loop; `references/work-tracking.md` when a
repo uses a work tracker (issue/PR linking, auto-close hazards, the
weekly update, `tracker_check.py`). Loop and scheduled-task templates (coordinator, peer, cleanup; 20-minute floor): `templates/loops/*.md`.

**Drifting into a lane's work** — while a lane is in flight, two consecutive
Conductor turns that query, build, edit, or mutate the target instead of
dispatching: stop, package a lane brief, dispatch it, resume status-reading —
`references/roles.md` **Catch and reverse your own drift** (scope, exception).

---

## Gates (G0–G10)

Low-blast reversible work may collapse adjacent gates. It may not remove
independent verification or a human approval that actually applies. Moving a
blocking check to one later blocking gate is not weakening it; removing it or
making it non-blocking is (`pipeline-optimizer.md`).

| Gate | Input | Required output | Hard condition |
|---|---|---|---|
| G0 Intake | Owner goal | Brief | Goals, non-goals, constraints, and **appetite** (a stated time-box, not an estimate — Shape Up); `idea-critic` on any agent-originated approach before the owner sees it. Shape: `references/template-onepager.md` |
| G1 Spec | Brief | Testable spec | Acceptance criteria; names `deep-code-review` scope and pinned base SHA |
| G2 Plan | Spec | Acyclic work graph | Role triggers, one writer per worktree; **every lane with a paid model call names a per-lane token/dollar budget before G4 starts — no budget set is blocked, not unlimited** (a cap that defaults to off is not a cap); in a multi-repo plan, classify each item provider vs consumer before cutting lanes (`references/roles.md` *No scope creep*) |
| G3 Design | Graph | ADRs / contracts | Interfaces, NFR budgets, data/security decisions explicit. Shape: `references/template-adr.md` |
| G4 Implement | Work packets | Patch/commit per lane | Tests before or with the change; packet names review skill + immutable base SHA |
| G5 Verify | Exact revision | Test receipts | **Local = affected tests** (a gate that never started the app is `UNVERIFIED`); **CI on the exact SHA is the receipt**, not re-run locally. **UI change (domain P):** headed-browser evidence on the exact route after the action. Unit tests alone are not a UI gate; UI DONE needs `journey: <page> <steps> PASS` (`verification-handback.md`) |
| G6 Review | Exact revision + receipts | `deep-code-review` + QA + security verdicts | Independent of the builder; applies the `deep-code-review` severity rubric — Blocker/Critical block, High needs a named owner's acceptance, Medium is tracked and non-blocking |
| G7 Integrate | Accepted lanes | Integration receipt + `deep-code-review DIFF` | One integration owner; affected tests; CI on the exact final SHA |
| G8 Release | Exact integrated SHA | Release manifest | Rollback proven; **owner approves** outward/production action |
| G9 Production verify | Deployed SHA | Verification receipt + `postdeploy-logs:` | Served behaviour and SLOs; rollback on breach |
| G10 Learn | Receipts | Retrospective | Escaped gap → regression test in this repo. Reusable lessons are generalized, third-party identifiers stripped, before leaving the project (`contribution` overlay proposes them upstream). Triggers, blameless shape, action-item closure: `references/retrospective.md` + `references/template-postmortem.md` |

**Missing evidence is `UNVERIFIED`, never pass. Missing price is `UNPRICED`,
never zero. Missing spend cap is `BLOCKED`, never unlimited** — `UNPRICED` is a
labeling rule (report the cost honestly); the G2 budget is the bound itself, and
the two are not substitutes.

**Building a user-facing product surface (domain P, build side).** To build to
the quality bar in G3 rather than discover the gaps in G6 review:
`references/production-grade-product-playbook.md` — **read it when** shaping a
product surface's information architecture, ranking, relationship-vs-record
framing, or density.

**Durable state, recovery, and non-code receipts** — one canonical project
record with a single writer, the resume / crash-after-effect reconciliation
procedure, and the artifact-receipt contract for design/data/published
deliverables: `references/project-state.md` — **read it when** beginning
multi-step work, changing objectives, checkpointing, recovering after a
reset, merging several requirement sources (feedback vs design), or deciding
what keeps an unattended run alive.

**Claimed vs enforced** — before asserting state, permission, or spend is
*enforced* rather than merely followed (or when designing a host adapter), grade
the claim against `references/host-enforcement.md` — **read it when** you would
otherwise write "the gate / budget / permission is enforced," or brief a
write-lane. A subagent handback's fields-only shape is capped by a host hook,
`scripts/handback_cap.py` (`SubagentStop`), not only asked for. The same file's
"Minimum-cost CI & token profile" section is the canonical, mandatory
GitHub-Actions/token cost doctrine — **read it when** wiring or reviewing a
workflow trigger, an integration-branch merge path, self-hosted runners, or a
fleet's spend caps.

**Cost vs quality guardrails** — before shipping any cost cut (cheaper model
tier, lane cap, must-load section moved behind a trigger, fewer review hats),
and whenever choosing a lane's model or reviewer by the paths it touches:
`references/cost-quality-guardrails.md` — **read it when** a change cuts cost,
a lane needs a cap or a `VERIFIED`/`UNVERIFIED` handback, or an escaped defect
may trace to a cut. The one path-to-tier list is `templates/review-tiers.tsv`
(decides review strictness by path); which model tier and reasoning effort a
lane's own *executor* runs at, by work type and stage, is
`deep-code-review`'s `model-tiering.md` **Route delivery lanes by work
type and stage** — the two lists are complementary, read both before
dispatching a lane.

**Operational readiness — incidents and continuity.** The
binder that must exist *before* the system is on fire or the solo operator is
gone: `references/incident-response.md` — **read it when** drafting an incident
runbook (detect→triage→contain→eradicate→recover→review), severity levels,
comms templates, a break-glass path, a credential/renewal inventory with
dead-man reminders, or a succession note. It reuses the blameless
`references/template-postmortem.md`; **breach notification routes to G2 + counsel, never
asserted here**, and executing any notification or succession is the owner's.

**Support & feedback operations.** When the
product has users filing tickets: `references/support-ops.md` — **read it when**
building an intake/triage taxonomy, an SLA, canned-response drafts, or the
ticket→work-item loop. **Hard gate:** never auto-send an external reply or make
a promise/refund/commitment — every outward reply is owner-approved, the same
gate this skill applies to push/deploy.

**Multi-session / peer coordination.** Two or more agent sessions coordinating over a shared async
channel instead of one orchestrator's own lanes:
`references/multi-session-coordination.md` — **read it when** designing a
claim/lock registry (a claim is a token whose second create fails, not a comment), a pre-write collision probe, a peer-liveness check, a
shared-board reader, pushing a house comms/review default down to spawned
subagents, retracting your own in-flight lane, or any peer trigger in that
file's **Routed triggers** (broadcast asks, crossed splits, merge-holds, shared budgets).

**Unattended / autonomous operating mode.** When this skill runs as a **continuous loop over a backlog** rather than
one feature at a time: `references/unattended-operating-mode.md` — **read it when**
starting or shaping an unattended / overnight autonomous run. It composes
`deep-code-review` (review), `idea-critic` (decision), and this skill's gates
into one bounded loop: stopping needs a stated termination condition, a
**run-start checklist + run-end self-audit** bound the run, and a default set of
offset recurring loops runs it. A **loop, not a standing swarm**.

**A work item's own completion is G7, not G8.** Once a lane's change is
integrated (G7), the work item it closes is done; G8 Release is a separate,
later, **owner-gated** action, often batched across many
G7s. Never park a G7-complete item as "blocked on deploy" — land it, close it,
and name G8 as downstream and pending.

---

## Exact revision

Every technical packet names `deep-code-review` + the required scope (`FULL` /
`DIFF <base>` / `FILE <paths>`) and the immutable base SHA (G1/G4) or exact
reviewed SHA (G6/G7). QA and security receive the **final SHA**, not the
builder's narrative; a stale SHA fails closed. Union proof (G7) only when PRs overlap on
paths or generated files; else drain green PRs back-to-back (`train_land.sh`).

---

## Worktrees and occupancy

- **One writer per worktree — and a worktree is not automatic.** A subagent or
  fork does **not** necessarily give a separate working tree: verify your host's
  isolation and **assume a shared tree until proven otherwise**. Branch, index,
  and installed dependencies are per-tree, so two writers in one tree collide
  even with disjoint file sets. Give every write-lane its own isolated worktree
  (or claimed branch), and **clean the base to the mainline before launching**.
  Read-only reviewers may share a pinned checkout.
- **Preflight before spawning any lane.** Enumerate what is already in flight —
  running workers, worktrees (`git worktree list`), open PRs — and claim the
  work (a draft PR, or an assignment you confirmed is in progress: assigned is intent, not progress; a module-ownership map locks files, not the objective) before opening the worktree. Never spawn a duplicate
  of a running lane, and never start on a branch that already carries commits
  without reading them first. One writer per file (narrow stacked-lane exception:
  `references/dev-env-ownership.md` *Another mis-fire: "one writer per file" reads a legitimate stacked pair as a
  collision*).
- **A forked lane with a narrower brief than its inherited context** (research-only, "change nothing"): prefer a fresh unit; verify from effects — `references/verification-handback.md` **A context-inheriting fork is not a blank slate**.
- **Inventory the repo's own scripts before spawning a lane for a repeatable step.** On start, read `scripts/` and the README; if a tick, train, bisect, land, or release script exists, run it instead of having an LLM lane do the step (or hand-resolve a generated-file conflict) by judgment.
- **New script?** `python3 scripts/wired_check.py <base> HEAD`: a WARN means no caller (own test excluded); wire it. A script named only on an orphan/unused allowlist added in the same PR is `merged-not-wired`, never wired.
- **Hand-back / reruns / drift?** `wired_check.py <base> HEAD --strict --runs <log>` fails a new script with no caller or no observed-run line; `stage_run.py --run-dir <fresh dir> -- CMD` refuses a reused run dir; `python3 .claude/skills/agentic-delivery/scripts/lkg.py verdict <receipt.json>` fails (rerun) when its `sha` is not HEAD; `python3 .claude/skills/agentic-delivery/scripts/vendor_drift.py <target-repo>` exits 1 listing vendored skill files that differ from canonical (sha256).
- **P0 count inflated / "what next?":** read when many open issues are P0. Don't relabel; rank a top-N in PRIORITIES.md, tag the rest `p0:unranked`; `scripts/queue_guard.py` prints the next pull and flags inflation.
- Serialize shared-state edits, migrations, generated files, and the
  integration branch — lanes sharing a host: `scripts/serial_gate.py`.
- Occupancy is **visibility, not a lock**. Say what is live or stale; do not
  comment "do not merge" on a peer's PR after you stopped writing.
- **A stacked/child lane branches off the parent's LOCAL ref, never polls the
  remote** (#1152). Worktrees sharing one `.git` already see a parent's branch
  tip the moment it commits (`git rev-parse <parent-branch>`, `git worktree
  list`) — well before any push; polling `git fetch` or the forge API instead
  serializes the child on a push queue that has nothing to do with whether the
  work is ready. Reserve remote-based readiness for cross-machine coordination
  with no shared local ref (`references/multi-session-coordination.md`).

## Environment probe (before you size anything)

Probe free RAM, CPU cores, disk, and usable connector auth before deciding lane
count, the heavy/light split, or model tier — never from habit or a remembered
ceiling. Commands and
decide-from-probe rules: `references/fanout-host-sizing.md` **Environment probe
procedure** (read it before sizing any fan-out); CI-offload:
`references/merge-queue-worktrees.md`.

- **Act-on predicate:** spawn another heavy lane only while free RAM >15% AND swap is not climbing; CPU idle is secondary, `load1` never decides — why: `references/fanout-host-sizing.md` **Gate on free RAM and the swap trend**. Mechanized: `scripts/host_probe.py --lane-type {cpu,io,light} [--canary CMD --baseline-file F]` prints `SPAWN`/`HOLD <reason>`/`COULD_NOT_CHECK <what>`.
- **Auto-wired by `--apply-operating-layer`:** `scripts/heavy_gate.py` (PreToolUse Bash) denies tests/builds while `host_probe` HOLDs or heavy leases are full; fails open. `scripts/session_brief.py` (SessionStart): ≤3 report-only lines.

## Local environment (own it)

Delivery owns the running stack, not only the diff.

Five steps — discover the documented one-command path, bring it up in the writer's worktree, **(3) verify against the running process**, tear down, never build into a served dir: `references/dev-env-ownership.md` **Local environment — the five-step stack procedure**; read it before any G5 run.

---

## Human gates

Agents prepare. Humans approve:

- push, open/merge a PR, publish a package, deploy;
- send an external customer reply, refund/credit, or public statement
  (`references/support-ops.md`);
- grant scopes, rotate secrets, change IAM, widen egress;
- destructive migrations, mass deletion, force-push, production rollback-forward;
- feature-flag flip, canary widen;
- waiving a Blocker/High security finding.

**Standing grant.** A grant counts **only** from an owner-authored artifact:
the owner's own commit (author = owner) to `CLAUDE.md` or the state record, or
the owner's message quoted verbatim with its date and where it was said. The
agent never creates, widens, extends, or re-dates a grant — being the record's
writer (`references/project-state.md`) is not authority. Absent or ambiguous →
gated. Under a valid grant (scope + date), push / open PR / merge to the
integration branch it names, for green, reviewed work inside that scope,
proceed without asking and are logged as taken. A merge into a branch whose
merge triggers deploy or publish is a deploy (an auto-deploying `main`) — never
covered. Force-push, history rewrite, deploy/prod, secrets/IAM, spend, external
sends, and destructive data stay gated always. The un-gated half of an unattended run is
`references/unattended-operating-mode.md` **The Human-gate boundary**. A gated
item is parked with its next step while the loop continues; it is not a stop. A gate usually covers one step, so slice the work around it, not park the whole item: pre-fill the decision so the human acts once, build behind a switch, write and dry-run the script, dispatch what is un-gated, and ask only about the human step itself.

Shape every ask as one issue, two approaches:

```
Issue: <one line>
A: <approach> (recommended) — <why, ≤12 words>
B: <approach> — <why, ≤12 words>
```

Never a list of questions. An agent-originated A is attacked by `idea-critic`
before it is marked recommended; confirming already-reviewed work is exempt
(`idea-critic` **Don't use for**). Before raising a gate, apply gate epistemology principle 12 (`references/gate-epistemology.md`) — a fork a ratified invariant already decides is not a human gate.

---

## Gate epistemology (public principles)

Twelve public gate principles: `references/gate-epistemology.md` — **read it when**
you add a gate (4), scan a publish boundary or banlist (1, 2), a result
surprises you, a check could not run, input is absent, or a pipeline is red /
about to revert (3, 5, 10), before a merge train (6), choosing what to test (7),
writing a public or compiled artifact (8), closing or deleting shared state (9),
reporting visible/done (11), or raising a fork an invariant may decide (12).

---

## Output contract

Every worker returns: role, exact SHA, artifacts, acceptance covered,
commands actually run with exit status, findings with severity + location
+ evidence, remaining risk, cost/`UNPRICED`. `NONE` is a valid findings
result.

**Work-item contract (what the output is graded against).** A work item is
specified as **Where** (the area it touches), **Done-when** (observable
acceptance), **Verify** (how it's checked), and **Why** (so scope can be cut).
Missing *Done-when* or *Verify* is underspecified — sent back to be scoped, not
started.

---

## Failure

- Start/auth failure: do not claim work ran.
- **A running lane is not a finished one.** A spawned worker/worktree is work
  in progress; report what is *running*, and a lane's output as done only once
  verified — a green gate at the exact SHA, or a change confirmed in the running
  product. Never present "N lanes attacking it" as progress.
- **A lane's scope ends at its own finish line** (PR open, gates green): report once, stop re-polling — `references/verification-handback.md` **A lane looping in its own self-poll**.
- After two equivalent failures, change approach; never a silent drop.
- Provider/model unavailable: fail that lane closed; no silent fallback.
- Owner-session end: no uncommitted writer work without a recovery
  record.

**Anti-rationalization (G4 / G5)** — tempted to defer tests, skip a spec, let
unit tests stand in for the UI, trust local green, or pass a stack that never
started: `references/roles.md` **Anti-rationalization (G4 / G5)**.
