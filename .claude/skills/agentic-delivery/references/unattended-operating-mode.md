# The unattended / autonomous operating mode

Read this when: an agent or a Conductor is granted a block of **unattended time to
work a backlog** — an overnight or multi-hour autonomous run — and needs the whole
run's shape: how the mode composes the other skills, the delivery loop it runs, the
run-start checklist and run-end self-audit that bound it, what "done" it may claim,
the default set of recurring loops, and the churn / priority-inversion / owner-focus gates. This
file **names and wires together** doctrine that already lives in the sections it
points to; it adds only the connective mode-framing, the run-start/run-end gate,
the default loop set, and the routing to the gate scripts. It does **not**
restate the depth it routes to — follow the pointer.

This is **not a new runtime or a standing swarm** (`SKILL.md` intro) — it is how
the same opt-in, one-Conductor, hats-not-headcount pattern operates *as a loop*
while no human is watching. Every gate (G0–G10, Human gates, Gate epistemology)
still applies unchanged.

## The mode: a default loop, and stopping is the exception

An unattended grant is a **work loop over a ranked backlog, not a single task** —
the substance is `unattended-trackers.md` **An unattended time budget is a work
loop, not a single task**. Frame it as the default stance:

- **Starting the loop never needs a reason; stopping does.** The loop runs until a
  **named termination condition** fires (backlog empty; every remaining item blocked
  on another party or on a Human gate no owner-authored standing grant covers
  (`SKILL.md` **Human gates**); the granted window / appetite spent; a
  resource ceiling hit), each reported **with the evidence that it holds** — never a
  drift into silence. Depth + the four conditions: `unattended-trackers.md` **An
  unattended time budget is a work loop** (termination-conditions bullet).
- **A go-faster tick is not a demand for busywork; holding can be correct.**
  `unattended-trackers.md` **A go-faster signal fires on a clock, not on state**.
- **A lane decides its own reversible choices.** An A/B hand-back for a reversible choice, or a "lanes never push
  to their own branch" rule, stalls delivery; the lane picks, states the choice in its handback, and pushes.
- **A question for an absent owner is deferred, not waited on.** Record it with
  `agentic-ceo/scripts/task_ledger.py defer --id T-### --question "<q>"`. A
  reversible choice takes a default (`--default "<choice>"`), stated in the
  handback. A Human gate (shared push, deploy, external send, secret/scope
  change) or a destructive/irreversible choice without an owner-authored
  standing grant: never default, always `--park`. Parking blocks that one item,
  not the run; `unblock` is refused until `answer` records the reply. Continue
  with `task_ledger.py next`, which skips parked items. The owner gets one batch
  from `task_ledger.py questions` and can still stop the run or answer at any
  time. Optional hooks (a model-visible turn-start line, an owner notice on
  `Stop`): `host-enforcement.md` **Deferred-question hooks**.
  **While the owner is away, `defer` alone — never a posted message**: a decision
  request posted mid-run scrolls past and is unfindable later; the ledger, not the
  chat, is the record. Before deferring, check `task_ledger.py questions` for a
  near-duplicate already answered, so a settled question is never re-asked. Before filing an issue, search closed issues and PRs by meaning; a hit is a regression to reopen, not a new filing. On the
  owner's **next** message, whatever it says, **answer it first**, then append the
  full open batch from `questions` — never lead with the backlog of asks. Once
  `answer` records a reply, the ledger drops that item from the pending batch (it
  stays in `QUESTIONS.jsonl` as the decided record — the decision ledger); no
  further pending prompt repeats it. A **peer session** (a spawned subagent, a
  sibling lane) routes its own deferred questions to the **conductor's** ledger,
  never messages the owner directly — one pending list, one owner-facing batch.
- **Measure delivery, not activity.** Report the **operator's own metric** and grade
  against durable output. Useful signals — **no** target thresholds (fabricated
  otherwise): merged-**to-default** per window, base-red **minutes-to-green**,
  **fix-forward share**. Routing: `fanout-host-sizing.md` **Report the artifact,
  not the activity** and `unattended-trackers.md` **reconcile status against the
  operator's open-issue metric**; DORA: `deep-code-review`'s `release-engineering.md`.

## Why sessions stop after one item, and how to run autonomously

Read this when an owner says "autonomous run" and the agent does one piece of work, then waits for input.

The host ends a turn when the model returns. Nothing in prose doctrine (this file, a handback rule, a ledger) can make a finished turn continue: a doctrine that says "keep going" is advisory, and a loop template that says "run once, then stop" ends the session by design. Continuation has to come from the host:

- **Self-paced `/loop`** (the owner types `/loop <goal as given>`): the model re-enters itself each tick and picks its own delay. The plugin's `commands/perun-run.md` (`/perun-run <goal>`) tells the agent to start this mode; if a command cannot start it in a given host, the command prints the exact `/loop <goal>` one-liner for the owner to run. The command ships with the plugin only; `install.sh` does not copy `commands/`, so script installs use the `/loop <goal>` one-liner directly. Whether a slash command can start a loop is host-dependent and was not tested end to end (`unverified`).
- **An owner-started schedule** (a recurring job the owner creates), for work that should wake on a clock.
- **A wakeup tool inside a loop** (for example `ScheduleWakeup`, where the host provides it; `unverified` outside dynamic loop mode), as a delay of about 20-30 minutes when the only thing left is waiting on an event. Bound it: after a tick or wall-clock ceiling (the command uses 24 hours or 100 ticks) park the item and end the run with a report.

Each tick picks one item with `agentic-ceo/scripts/task_ledger.py next --check`, does it, and records it. Exit 3 means drained: the queue holds no non-gated item and the run may end, but blocked rows and pending questions are still reported on the way out. Gated items are parked with `task_ledger.py defer --park`, which removes them from `next`, so a run never stalls on them. A run takes an irreversible action only when the owner's own message granting it is quoted in the ledger row and covers that action; otherwise it parks.

What not to do: do not add a `Stop` hook that returns `decision: block` to force another turn. It removes the owner's ability to end a run, it fights the host's own continuation cap, and it can trap a session on an item that needs a human. The owner starts the run and stops it by interrupting the session or telling it to stop; the agent checks for that at the start of each tick.

## What it composes (three skills, three gates, one bounded loop)

The mode is not new machinery — it is the suite's existing gates run continuously:

- **`idea-critic` = the decision gate.** Every agent-originated approach choice
  (a new approach, an A/B fork) is attacked before it is acted on — not routine
  execution or gate confirmations (`idea-critic` **Don't use for**) — with
  **premises verified against live data, not memory** — `SKILL.md` G0/G1 + Gate
  epistemology principle 3 (a surprising conclusion re-fetches the state) and
  `fanout-host-sizing.md` **A remembered constraint-state is a guess**.
- **`deep-code-review` = the review gate.** Independent of the builder at G6
  (`SKILL.md` Gates; `roles.md`).
- **`agentic-delivery` = the gated delivery.** G2–G8 with the Human gates intact.
- **The default autonomous-run profile — one grant, not a per-brief
  restatement.** An unattended grant carries a standing profile so the owner
  never restates it: terse chat/reasoning with persisted artifacts (code,
  commits, PR/issue bodies, docs) always in normal prose — add
  [caveman](https://github.com/JuliusBrussee/caveman) for the former — plus a
  minimal-code bias for plumbing/fix/tooling lanes via
  [ponytail](https://github.com/DietrichGebert/ponytail), **design-port lanes
  exempt** (`README.md`); absolute-minimum chat output — no narration, state
  changes/blockers/the result only, nobody is reading live
  (`cost-quality-guardrails.md` §6 **Critical work only**). Propagated the
  same way as any other standing default — baked into the agent definition or
  a host/user-scope mechanism reaching every spawned subagent, never a
  per-brief instruction alone — and verified the same way too: confirm a
  spawned subagent's own context actually carries it before claiming the
  profile is universal (`multi-session-coordination.md` **Enforce the
  default**, whose "bridge in-flight agents" rider and reach test apply
  unchanged here).
- **A decision that would otherwise wait on the owner is attacked by
  `idea-critic` before the reversible-choice default above is taken, not
  defaulted blind.** Record the hat's verdict as the reason the default was
  safe to take. Only a genuinely irreversible/shared-state action, or one a
  Human gate blocks, still `--park`s for the owner — every other deferred
  question gets the attack first, then the default.

The **bounded-and-reversible spine** holds throughout: every gate **fails closed**
(a gate that cannot run is `UNVERIFIED` / could-not-check, never a pass — `SKILL.md`
Gate epistemology principle 3), and nothing irreversible or outward happens without
the reversibility boundary or a human tap (`SKILL.md` **Human gates**).

## The delivery loop (five rungs — depth routed, not restated)

Each rung is a name and a pointer; the mechanism lives at the pointer.

1. **Keep the base green.** `red-gate-triage.md` **A load-flaky required gate
   is not a confirmed red** + `deep-code-review` `merge-operations.md`
   **Red base: discharge the deadlock with a train**; `SKILL.md` principle 3.
2. **Land every green PR** — a **single merge seat**, back-to-back inside one
   not-red window (default a small batch, ~3-ready), a **union-proven train** when
   members might interact. `merge-queue-worktrees.md` **Parallelizing the merge
   seat backfires**, **The window's admission check is not-red**, **An
   independent-PR-queue cascade is a cadence choice**; `SKILL.md` principle 6;
   `merge-operations.md` Merge trains.
3. **Turn red / conflicting PRs green by conflict TYPE, not file count** —
   already-applied vs diverged vs regenerable-artifact vs true textual conflict,
   each resolved by its type. `deep-code-review` `branch-and-merge-hygiene.md` §4
   decision tree, `merge-operations.md` **Never hand-resolve a conflict inside a generated file**;
   `merge-operations.md` **Merge trains**; the zero-checks / `mergeable_state` re-fire case is
   `red-gate-triage.md` **Absent checks are a third state**.
4. **Deliver open issues in verify-first waves** — the fix may already be on the
   base. `unattended-trackers.md` **An open tracker issue is not proof the fix is
   absent**, **reproduce an inbound bug on current HEAD**; `verification-handback.md`
   **A hard-to-write test must not hold a ready fix hostage**.
5. **Fill to measured machine headroom** — free RAM + swap **trend**, not `load1`;
   spawn one, re-sample, keep a burst reserve; cheap read-only lanes effectively
   unbounded. `SKILL.md` **Environment probe** + `fanout-host-sizing.md` **Gate
   on free RAM and the swap trend**.

**Two sequencing rules over the rungs:**

- **FREEZE-THEN-TRAIN** — while a resolver rebases a cluster against the base,
  freeze merges into that base and land only non-overlapping surgical merges
  meanwhile. `merge-operations.md` **freeze the sweep while a resolver
  runs**; `merge-queue-worktrees.md` **Parallelizing the merge seat backfires** and
  `dev-env-ownership.md` **An ownership map blocks a dual write, not dual work** (a shared artifact in
  flight blocks only the lanes that touch it).
- **SIZE-TO-MEASURED-HEADROOM-AND-SCALE-UP** — the ceiling is a **back-off trigger,
  not a licence to under-fill**; a chain of individually-correct holds must not
  ratchet the machine to idle. `unattended-trackers.md` **The owner's message
  cadence is not the loop's clock**, **A chain of individually-correct holds can
  still drift the machine to idle**, and `fanout-host-sizing.md`'s free-RAM **veto,
  not a licence** rule.
  On a shared host, read the gates as **machine-wide aggregates**
  (`multi-session-coordination.md` **Every peer honoring its own heavy-lane cap
  still oversubscribes the machine**).

## Two mechanical gates on what the loop ships: churn and priority inversion

A loop graded on activity drifts to cheap, visible work. One private audit
(generalized): 86% of commits reworked earlier work, 26 files were fixed ten or
more times at a median 22.5 h apart, and presentation PRs rose to 48% while
feature work fell to 9%, with every P0 / mechanism issue still open and cited by
zero PRs. Attention caught neither drift. Two opt-in stdlib gates make each a
blocking fact (`--selftest`; fail closed on unresolvable input; wired into a
target's CI behind env flags by `deep-code-review`'s `templates/dcr-gates.sh`):

- `scripts/refix_gate.py` — **use this when** a lane re-touches a file a recent
  `fix:` commit touched. A range doing so inside `--window-hours` (default 72)
  must add a test/eval path matching `--class-glob` or carry a `Refix-Reason:`
  trailer; output names the file, prior fix SHA, and age. It forces a
  class-level artifact to exist; it cannot judge class completeness (that stays
  the reviewer's — `deep-code-review` `method.md`, class discipline).
- `scripts/priority_gate.py` — **use this when** ordering dispatch or reviewing a
  presentation PR (by label, or every path matching a presentation glob). It
  fails that PR while any P0 / mechanism issue older than `--min-age-hours` has
  no other open or merged PR citing it; `--budget` caps the presentation share of the
  last 24 h of merges. Pure over a JSON document (`--labels-json`), or fetched by
  paginated `gh api` (`--repo`). It proves a citing PR exists, not that the PR
  advances the issue.

## An open owner priority outranks every other item

Fleets left the owner's main priority before it was done: every move-on rule —
*pull the next item*, *self-source rather than stop*, refill an idle slot, the
go-faster tick, *every remaining item blocked* — read as permission to leave it.
This section is the one binding over all of them (`unattended-trackers.md`
defers here):

- **An OPEN owner priority outranks every other item** — backlog rank, a
  self-sourced finding, a cheap cosmetic fix. "The next item" means the next
  item **inside its scope**.
- **Work outside it only when it is DONE or BLOCKED.** DONE = the owner's
  acceptance command exits 0 on a clean checkout, never a lane's "mostly done".
  BLOCKED = an owner-accepted row naming **another party** plus an evidence
  link; a hard sub-problem or a red test is not a blocker. Neither → keep at it
  (split, re-approach, spike) and report OPEN with the acceptance output.
- **The record is owner-authored** — the owner's own commit to
  `.claude/PRIORITY.md`, the standing-grant rule (`SKILL.md` **Human gates**).
  An agent never creates, widens, narrows, closes, or deletes it; a change is an
  ask.
- **Design alignment is done** only when `deep-code-review`'s parity differ
  reports inventory MATCH for every in-scope screen (`rendered-parity.md`) —
  never a size, height, or screenshot judgement. That is its acceptance command.
- `scripts/focus_gate.py` — **use this when** picking the next item, dispatching,
  or reviewing a change. `status` prints state and evidence; `check` (item,
  paths, or commit range) is NO-GO outside scope while OPEN. Fails closed: a
  non-owner record or deletion, a `**` scope, or a trivially-true acceptance is
  never DONE; no record ever → GO with a notice. CI: `DCR_FOCUS_GATE=1`
  (`dcr-gates.sh`).

## The run-lifecycle gate: a run-start checklist and a run-end self-audit

This is the genuinely-new normative addition — everything the items reference
exists; the **bundling into a run-lifecycle gate** is what this section adds.

**Run-start checklist** (before the first lane; each unset item fails the start
closed):

- **Spend ceiling** — a per-lane token / dollar budget for any paid call; a lane
  with a paid call and no budget is **BLOCKED, not unlimited** (`SKILL.md` G2; "we
  will watch it" is not a budget).
- **Reversibility boundary** — the actions that need a human tap, restated for
  this run (`SKILL.md` **Human gates**).
- **Durable state confirmed** — the ranked backlog **and** the ask-ledger (one row
  per owner request) live in a file / tracker, never only in scrollback, so a
  compaction or reset loses nothing (`project-state.md`; `unattended-trackers.md`
  **An unattended time budget is a work loop** and the ask-indexed read-first
  ledger bullet).
- **Concurrency cap** — sized from a live environment probe, not habit (`SKILL.md`
  **Environment probe**).
- **Held-lane roster** — before broadcasting any new rule or status update, list
  which lanes are currently held (a memory hold, a quota hold, a merge freeze);
  do not message them — any message resumes a held lane with its full context
  and last plan (`multi-session-coordination.md` **Bridge in-flight agents**).
- **Wake model** — event-driven (task-notifications + a heartbeat), **no idle
  polling**; a monitor emits on transition only (`SKILL.md` **Conductor operating
  rhythm**; `unattended-trackers.md` **A monitor emits on state-transition or
  terminal state only** and **A loop's own wake/poll cadence is not the work
  cadence**).

**Run-end self-audit** (at every termination and at hand-off):

- **What landed** — on the **canonical surface** (merged-to-default SHA or a live
  URL), never a proxy.
- **What is staged / in-flight** — pushed branches, open PRs.
- **What is blocked, and on whom** — each owner-gated next step named.
- **Spend used vs the ceiling.**
- **Net removal vs a protected baseline** — the checks above measure
  activity, not value; diff the run's cumulative surface and data inventory
  against a committed must-keep baseline each cycle, and flag a cycle that
  removed more than it added as a regression to reverse, not progress to
  report — removal needs a logged acknowledgement, never a silent side effect.

Depth: `unattended-trackers.md` **If the loop is idling, say so loudly** (report
the window, not the item) and the honest-reporting ladder below.

## Honest reporting: running ≠ merged ≠ live

A proxy is never a completion claim. Keep the three rungs distinct, each verified
on its own surface:

- **running** — a spawned / computing lane is **not started** until it has a durable
  artifact (`unattended-trackers.md` **Progress is a durable artifact, not a
  spawned lane**; `SKILL.md` **Failure** — a running lane is not a finished one).
- **merged** — integrated is G7, and a merge **off the default branch is
  done-in-tree but still open** (`SKILL.md` — *A work item's own completion is G7*;
  `unattended-trackers.md` **An open tracker issue is not proof the fix is
  absent**).
- **live** — rendered on the owner's own surface and verified there, not inferred
  (`SKILL.md` Gate epistemology principle 11; G9).

## The default loop set (distinct loops at offset cadences)

The genuinely-new **architecture**: run a set of **distinct recurring loops at
offset cadences** so one stalled thread never stalls delivery — a stalled producer
must not hold up merges, a stalled merge must not hold up hygiene. A cadence is the
**maximum latency before that thread is re-checked, not the work quantum**: on any
wake, take **every** currently-admissible action of that loop's kind before ending
the turn — never one action per tick (`unattended-trackers.md` **A loop's own
wake/poll cadence is not the work cadence**). A worked default set:

| Loop | Cadence | On each wake (routed rule) |
|---|---|---|
| PUSH | ~10m | push ready branches / open PRs — **Progress is a durable artifact, not a spawned lane** |
| MERGE / train-drain | ~15m | single-seat drain of the green queue — **Parallelizing the merge seat backfires**; **A serial queue-drainer must advance past a blocked head** |
| PRODUCER | ~15m (phase-offset from MERGE) | pull the next backlog wave (an OPEN owner priority's scope first), verify-first — **An open tracker issue is not proof the fix is absent** |
| HYGIENE | ~30m | worktree / process reaping, stale-claim reconcile — **A worktree is a resource with a lifecycle** |
| QUALITY / UX-VERIFY | ~20m | central browser / UX verification of landed UI — **Draft-gated heavy checks hide a UI-regression wave** |
| LEARNINGS | ~2/hr | capture standing findings as tracked items — **Research is not delivery**; `SKILL.md` G10; project bugs go to the project tracker, suite lessons upstream via `prefile_check.sh` |

- **Same-period loops carry an explicit phase offset** (MERGE and PRODUCER both
  ~15m wake roughly 7m apart) so they do not land on one tick; when loops *do*
  co-fire, **consolidate the fires into one reconciliation pass**
  (`unattended-trackers.md` **A go-faster signal fires on a clock** — the
  multiple-loops-compound / consolidate-overlapping-fires paragraphs).
- **Add a non-overlapping loop rather than raise a loop's frequency** to close a
  gap; the operator-visible loop set is **add-only** unless a decrement is named
  (`unattended-trackers.md` **The loop set is add-only when the operator asked
  for "more"**).
- A degradation workaround inside any loop is **temporary by default** — tie its
  removal to the blocker clearing (`unattended-trackers.md` **A degradation
  workaround is temporary by default**).

## A loop that duplicates another loop's scope is a design defect — collapse it, don't stagger it

Phase offsets and fire-consolidation fix loops that land on the same tick, not
loops that sweep the same scope at different cadences: every wake past the
tightest one is a guaranteed no-op that still burns a full sweep. Run that scope
at its own tightest useful cadence and drop the duplicates at design time. The
add-only policy (`unattended-trackers.md` **The loop set is add-only when the
operator asked for "more"**) does not protect them: a same-scope duplicate was
never a separate job.

## A stuck trivial change gets one recovery attempt, then is recorded and passed — never a nursing loop

**A small change failing to commit/push on an environment issue (a hung hook, a
missing binary, a worktree race) gets exactly one recovery attempt from the main
loop; on a repeat failure, record the item (ledger / state record: what, the
failing command as evidence, the next step) and move to the next item — never
another retry, never silently drop.** A fault that blocks every commit (a hung
hook) is systemic: escalate it as a blocker with one root-cause lane, not a
per-item skip. The original failure plus the recovery are `SKILL.md`
**Failure**'s two equivalent failures; the recorded item satisfies the logged
acknowledgement the run-end self-audit requires. Same bound as
`verification-handback.md` **Bound every flaky finalize step**, applied to the
loop's own commit/push; recovery spend must not exceed the change's worth.

## The Human-gate boundary (unchanged)

The mode changes **what stopping requires a reason for**, never **what needs a
human**. An item whose next step is a Human gate (push, merge, deploy, external
send, secret / scope change) is **parked, not self-authorized**, and the loop
continues on the rest — surface a one-action, self-updating human escape hatch up
front rather than narrating "holding". The autonomous **PUSH** and **MERGE** loops
above are the un-gated half only — a lane's own **feature-branch** push and the
**G7 integration** merge. A **shared-branch** push or a **merge-to-default**
stays a Human gate unless an owner-authored standing grant covers it — never one
the agent wrote, widened, or re-dated, and never a merge that triggers deploy or
publish; a deploy or an external send stays gated always (`SKILL.md` **Human gates**);
`merge-queue-worktrees.md` **When no autonomous path exists, surface the human-run
escape hatch** and `unattended-trackers.md`'s termination-conditions bullet. Never silently reverse a
dated / ratified decision (`SKILL.md` Gate epistemology principle 12).

**Owner-opt-in deploy mode (never a default).** Agent-driven deploy is gated by default. Only the owner may
enable an exception, by their own authored artifact (the standing-grant rules in `SKILL.md` **Human gates**),
and only when all of these hold: the deploy key is scoped to one project and environment and lives in the
secret store, never in the repo or a recipe; every deploy and status poll is written to an audit trail; and
the agent verifies the served result after the async deploy API returns (for example a 202, then polling
status until done). Record the recipe, never the key. Absent the owner artifact, the deploy stays a Human gate.

## Less talk, more work

Default to **one line per material landing**, no status essays; raise verbosity
only when the operator cannot otherwise see enough. An idle loop still **says so
loudly** — silence reads as working. `communication-structure` (BLUF);
`fanout-host-sizing.md` **Report the artifact, not the activity** and
`unattended-trackers.md` **If the loop is idling, say so loudly**.

## Cross-references

- `SKILL.md` — Gates (G0–G10), Human gates, Gate epistemology (principles 3, 6,
  11, 12), Environment probe, Conductor operating rhythm: the invariants this mode
  runs as a loop.
- `references/fast-agentic-delivery.md` — the index of the five themed lesson
  files (concurrency, merge cadence, verification, ownership, work loop) every
  rung and loop above points into.
- `references/multi-session-coordination.md` — when the unattended run is one of
  several peer sessions on a shared host / account.
- `references/project-state.md` — the durable backlog / ask-ledger the run-start
  checklist requires.
- `deep-code-review`'s `branch-and-merge-hygiene.md` + `merge-operations.md` — the conflict-classification,
  merge-train, and red-base mechanics rung 3 and FREEZE-THEN-TRAIN route to;
  `release-engineering.md` — the review-side delivery-metric (DORA) depth.
