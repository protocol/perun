# Fast agentic delivery — merge-queue cadence and train landing

Read this when: draining a ready queue or a single merge seat, landing a train (`merge_train.py`, `train_land.sh`, `land_train.sh`, the review gate), scoping an auto-merger, hitting a permission asymmetry or a human-run escape hatch, staggering ready-flips, rebasing a moving base under stacked lanes, offloading a heavy gate to CI, an opt-in throughput lever, the window's not-red admission check, an independent-PR queue cascade, draft-gated heavy checks, fleet delivery rules (footprint-sized trains, one merge at a time), or an OOM-killed train.
Part of the `fast-agentic-delivery.md` ledger (index and sources there); an "above"/"below" pointer to a missing section is in `red-gate-triage.md` or `worktree-isolation.md`.

---

## Sweep the whole ready queue on every trigger, not just the triggering item

The Conductor's attention is correctly event-driven, not polled — but a Conductor that reacts only to the
specific thing it is waiting on (one lane's own completion, say) can sit through several such events while a
**different, already-green, already-mergeable** PR sits idle in the same queue, simply because nothing about
that other PR generated an event. The fix: whenever the Conductor's attention *is* triggered by any of the four
named events, spend one cheap pass over the **entire** ready queue (a status check per candidate PR) before
returning to waiting — not only the item that triggered the check. This is a completeness fix to what a
checkpoint covers, not a change to the event-driven model itself.

## A serial queue-drainer must advance past a blocked head, not re-select it — head-of-line starvation

A serial auto-processor — a **merge-drainer, a retry queue, a task poller** — that picks the **first eligible**
item each cycle and retries it will **spin forever on one item blocked for a persistent reason**, starving
everything queued behind it. The tell is a loop that looks **idle** but is actually **starving**: an auto-merge
drainer picks the first **green + mergeable** PR each loop, but that PR is refused by a **stricter final gate**
(a PR-body lint, say) it cannot pass as-is — so the drainer re-picks the *same* head every cycle and never
reaches the others. The **cheap pre-filter is not the final admission gate**: an item can pass
*green + mergeable* forever while failing the final gate, so "retry the front of the queue" is a starvation bug,
not a queue.
- **Iterate all candidates per cycle; on a refusal, advance to the *next*** — never break the loop and re-select the same head. This completes the *sweep
  the whole ready queue* rule above: that says *scan the whole
  queue* (don't miss a ready item); this says *don't let one blocked item stop the drain* (don't get stuck on
  the head you did find).
- **Keep a cooldown / skip-set** for persistently-refused items so cycles aren't burned re-checking them, with
  **periodic re-evaluation** — the block may clear (the refusing gate gets fixed, a dependency lands).
- **Log the outcome per item** — `refused → advancing` vs `merged` vs `cycle idle` — so a spin is visible at a
  glance instead of reading as healthy idle (the *idle, say so loudly* discipline below, at the item grain).
- **🚩 tell:** a drain/retry loop that `break`s or `return`s on the first refusal, or re-selects `queue[0]` each
  cycle; or a *cheap* pre-filter (green + mergeable) used as the loop's selection key while a stricter final
  gate does the real admission.
- **Fixed-quota schedulers starve the tail the same way.** A scheduler that each tick picks the first unit "not yet run today" never reaches the last units when units outnumber ticks per day (14 lanes never ran in the field). Pick the **least-recently-run** unit, and test with more units than ticks.

## An auto-merger scopes by a manufactured ownership signal, not by author — shared identity makes authorship useless

The drainer above iterates the candidate set; this decides **which** PRs are *in* it. An auto-merge (or
auto-rebase) system must act on **agent-produced** PRs and **never** on a **human's own** (a human may be
mid-work, want to self-review, or own the domain — a large design build). The obvious scope — "only merge PRs
**authored by the bot**" — **fails when agents authenticate as the human**: agent lanes run `gh` under the
owner's token, so every PR, agent- or human-made, shows the **same author**. Authorship is then useless as a
discriminator, and an auto-merger keyed on it merges a human's unfinished PR the moment it goes mergeable
(observed: a drainer excluded a risky set by PR *number*, but a human-owned design PR shared the agent author —
only a semantic read of branch / diff / subject told them apart).
- **Give agents a distinct identity** — a bot account or a separate `GITHUB_TOKEN` — so authorship is a *real*
  discriminator. The clean fix.
- **With a distinct identity, filter by the author-identity match itself — never hand-maintain a list.** Once
  agents have their own account, the reliable ownership signal *is* the author field: scope the auto-merger to
  PRs whose author **positively matches the automation's own account** and default-deny every other, so a
  human's PR is out of scope *by construction*, not by having been listed. Do **not** substitute a hand-kept
  exclusion/allow list of PR numbers or branches for that match — a manual list is only as current as its last
  edit, and the PR it never learned about is the *next* human PR, so it goes stale and eventually auto-merges a
  human's mid-review work the moment that unlisted PR is mergeable. A list is the right tool only in the
  shared-identity case below, where there is *no* author signal to key on; where a distinct identity exists the
  author match strictly dominates it. Verify the match against the PR's real author, not an assumed token
  identity (a green-looking identity is a floor, not proof).
- **If identity must be shared, key the auto-merger on an explicit convention** — an allowlist of agent-created
  PRs, a denylist of human-owned branches, a label (`agent-mergeable`), or a branch prefix (agents `bot/*`,
  humans `feat/*`). **Default-deny anything not positively marked agent-owned;** never act on a PR you cannot
  *positively confirm* is agent-owned and safe.
- The general rule: automation acting on **shared artifacts** needs a **reliable ownership signal**, and when
  identity is shared you must **manufacture** one (a convention/label), never infer ownership from a field every
  actor shares.
- **🚩 tell:** an auto-merger scoped by PR author (`author:@me` / `gh pr list --author @me`) in a repo where
  agents run under the owner's token; or any auto-merge/auto-rebase with no positive agent-ownership mark (label
  / branch-prefix / allowlist) and no default-deny; or, where agents **do** have a distinct account, an
  auto-merger keyed on a hand-maintained exclusion/allow list of PR numbers or branches instead of the
  author-identity match — a stale list that auto-merges the next human PR it never learned about.

## An auto-mode permission gate that denies the orchestrator but allows a sub-agent is a false "stuck"

An unattended orchestrator draining a queue of green, mergeable, un-held PRs can hit a permission classifier
that **denies its own `merge`** ("merge without review") while
**allowing the identical merge from a spawned sub-agent**. The loop then runs every tick and lands nothing — the
operator sees "stuck / not pushing" when the work is done and gated only by the classifier, and all real
throughput is silently forced onto sub-agent delegation (fine for a *clean* merge of a PR that already
independently passed the gate — but delegating a **workaround** for an action the orchestrator was just denied
is itself catchable as laundering, not a loophole, and a single-PR merge does not warrant a heavyweight
isolated-worktree lane). The asymmetry is the trap: it is surprising, usually unlogged, and reads as a pace
regression rather than a gate. Resolve it explicitly instead of letting the loop burn ticks retrying a
structurally-blocked call: (1) a **preflight-keyed allow-rule** — permit the orchestrator to merge a PR whose
repo-defined green-gate / `merge_preflight` has just passed deterministically (the deterministic portion of the
review the classifier wants already ran); or (2) **symmetry + transparency** — if merges must be delegated, deny
them for sub-agents too and surface the reason ("merges routed to a delegated lane in auto mode") rather than a
bare denial the loop swallows; and (3) **document the routing** so the orchestrator delegates merges by design,
not by trial-and-error. **🚩** an auto-mode loop whose merge tick runs but lands zero PRs while sub-agent merges
succeed — a classifier asymmetry, not a slow agent.

**A second, compounding denial: the dirty-working-tree preflight (and its bypass flag) is itself denied to the orchestrator.**
An orchestrator that must hold uncommitted state for its own work — a WIP commit, edits mid-task — while also
draining the merge queue can face two stacked denials, not one: the classifier above denies its own `merge`, and
a dirty-working-tree preflight (plus whatever flag would skip it) is *also* orchestrator-denied. Both routes
close on the same tick, and the orchestrator can **land nothing across many ticks** while the queue sits green
and ready — the same classifier-denies-orchestrator asymmetry, compounded rather than resolved by either single
fix. The doctrine fix (not a script):
**delegate the merge itself to a subagent in its own clean, isolated worktree.** This does not need a second
laundering test: the existing carve-out just above already covers the merge itself (these PRs already
independently passed the gate); what the clean tree adds is the other half — its dirty-tree preflight predicate
becomes genuinely true rather than skipped through a passed-along bypass flag, so nothing is laundered there
either. Don't let this become a heavyweight lane per PR either — the caution above still holds:
**size the delegated lane to the batch, not to one merge.** Amortize one clean-worktree lane across 2-3 small,
disjoint, already-green PRs that merge in sequence through it, rather than spinning a fresh isolated worktree
per PR. Whether that batch also clears the project's own merge-authority bar as a train or a cascade is the
cascade section's question (below), not this one — this only sizes the lane doing the merging, never the
authority that admits what merges.

## When no autonomous path exists, surface the human-run escape hatch up front — don't narrate "holding"

Distinct from the delegation asymmetry above (where a sub-agent *can* act): when an agent is blocked from a
gated terminal step (a merge, a deploy, a paid call) and has **no autonomous route** — its own call denied *and*
delegation unavailable or also gated — a closed gate with verified work piled behind it is an
**escalation, not a hold** (distinct from "holding is a valid response" below: that rule forbids *manufacturing*
new work at a terminus; this governs what the *truthful status* must contain when banked-verified work is
stacked behind the gate). The failure mode is looping "gated / holding" every scheduler tick while banked,
green, mergeable work stays at **zero landed** — invisible to an operator who watches only the integration
branch, so a done-but-unlanded agent reads as slow or idle. On the **first** denial, convert the block into a
**one-action ask**: a single copy-pasteable command the human runs themselves (in host CLIs that provide a
user-executed shell prefix — e.g. Claude Code's `! <command>` — that command executes as the *user*, outside the
agent's own auto-mode classifier: a legitimate escape hatch, **not** permission-laundering, because the human
issues it — the agent must not run the prefix itself or re-route the denied action through any agent-controlled
path) or one GUI action, surfaced prominently and repeated, not buried under status ticks.
**Make the one action a query the human can re-run, not a snapshot list that goes stale.** A command hard-coded
to today's green PR numbers is correct once and wrong an hour later, forcing a re-issued command every batch —
the repeated pinging this section exists to stop. Hand over a **self-updating, idempotent** command instead:
discover the eligible set at run time (open PRs on the target branch, minus a named held/owner-gated set,
filtered to checks-green), merging each with a mergeability-recompute retry. This shifts what the human approves
from *this list* to *this policy* (merge whatever is green, now and on every re-run) — the named
held/owner-gated exclusion set is now the load-bearing part, since it is what the human is actually vetting once
they stop reviewing each PR number. The human runs the command once and re-runs it later to sweep whatever has
since turned green. **Track banked-verified vs landed**: when banked>0 and landed=0 for more than a tick or two,
escalate the human ask rather than re-reporting the block. Never let "the gate is closed" become a steady state
the agent narrates. **🚩** an unattended run reporting "holding / gated" across many ticks with a growing pile of
verified-but-unlanded work and no single human-runnable unblock surfaced.

## An independent-PR-queue cascade is a cadence choice, not a new authority

Gate epistemology principle 6 (union proof only on overlap) runs as `scripts/merge_train.py`. A related,
distinct situation: a **queue of PRs that are each already independently green**, with no known interaction
between them (typically right after the single common blocker above is fixed and the whole queue needs to
resync). Landing that queue does not need a new, lighter-weight merge authority — it needs **cadence**: run the
project's own merge-authority check against every queued PR on a short interval, rather than merging one PR and
waiting for the mainline's full CI resolution before even looking at the next.
**The one thing this must not become:** a second, separate pre-check (e.g., asking the forge "is this
mergeable?" through a different call than the authoritative merge gate itself) that races the platform's own
status — mature merge tooling names this exact anti-pattern from a past incident and refuses it by design,
calling only the one authoritative gate, every attempt, never pre-checking through a second path. A cascade is
**weaker evidence than a union-proven train**: a train proves the *combination* is sound before any member
merges; a cascade only proves each member was independently green and re-confirms that at each step. Defensible
specifically right after a single common blocker clears and every queued PR was already independently green —
not a general substitute for a train when queued PRs might still conflict with each other.

## Parallelizing the merge *seat* backfires under a base-sensitive gate — single-seat back-to-back draining is the real lever

The scaling reflex — more agents doing the bottleneck action (merging) ship more PRs per minute — is **wrong**
when the merge action is not merely contended but **self-invalidating for the whole queue**. Every merge
advances the base head, and every *other* open PR's base-diffing gate state is valid only against one specific
`base.sha`. A **second merger** does not halve the work — it **doubles the rate of base-invalidating events**
hitting every other open PR, compounding two failures: (a) a base-sha-sensitive gate that **fails closed** (a
misleading "no result," not an honest "stale — recheck") when it cannot cleanly resolve its diff against a
rapidly-moving base, and (b) concurrency-cancellation groups discarding in-flight check runs that were about to
pass, as competing merges churn shared state faster than runs complete. Net **slower**, not faster. The real
merge-rate lever is **single-seat, back-to-back draining**: one merger takes **all** currently-green PRs inside
one green-base window (many in a short burst — the wait only bites *between* windows; what the window's own
admission check does with a base run still in flight *between* members is sharpened just below), plus CI
speed-ups, plus a **union-proven merge train** (above) where queued PRs might still conflict. Keep the merge
seat a single `exclusive_role` in the claim registry (`multi-session-coordination.md`) — a second seat is not
throughput, it is base churn. Distinct from `merge-operations.md`'s
*freeze merges while a resolver is active* rule — that is merger-vs-**resolver** (protecting the resolver's own
just-computed rebase); this is merger-vs-**merger** (protecting every *other* open PR's base-diff gate and
in-flight runs). This is the flip side of the merge-train rule: back-to-back draining from *one* seat is the
win; a *second* seat is the loss. **🚩 tell:** two agents offering to "split merge duty to go faster," then a
wave of PRs failing a base-diff gate closed and in-flight runs cancelled — the seat was split, the
base-invalidation rate doubled.

## The window's admission check is not-red, not fully-green-between-members — a base run still in flight is not a hold

This sharpens the single-seat, back-to-back draining lever above: that lever names *who* holds the seat and
*when* it drains (one green-base window — it **opens** on a known-green base and **closes** on the post-batch
green re-confirmation below), not what the window's own admission check does, in its interior, with a base run
still in flight *between* members. Pending is admissible *inside* the window; only its open and close are
required to read green. It is not a new claim so much as the same logic `merge-operations.md`'s
merge-train section already states for the *union* branch's CI: treating "union CI still pending or red" as a
reason to hold members that are each already green re-serializes the very wait the train exists to remove.
Applied here to the **integration base's own post-merge run** instead of a union's: a shared base commonly
triggers a multi-minute CI run on every new head. If the seat's admission check demands that run
**resolve green** before it will admit the *next* member, the seat pays the base's own CI cycle once per merge,
and throughput serializes at (batch size) / (CI-cycle time) — the identical per-PR base-CI wait the merge-train
lever (above) exists to remove, reappearing *inside* the single seat instead of between competing seats.

The fix is the admission predicate, not a new draining mechanism: gate the window on the base reading merely
**not red** — pending / in-progress is admissible, only a **confirmed-failing** check on the base blocks — and
drain every member that is (a) own-green on its own required checks and (b) still mergeable, re-checked per PR
since a sibling landing can flip one to `CONFLICTING` (`merge-operations.md`'s
mergeability-is-a-snapshot rule; not restated here). Where the queue might interact, prove the union once up
front, exactly as the merge-train lever above already directs (`SKILL.md` gate epistemology principle 6; not
restated). Close the window with **one post-batch check**: re-confirm the base actually resolved green after the
drain, so a combination that reds it despite every member's own green is caught and fixed forward — never
assumed safe merely because no single merge paused to watch its own run resolve.

This does not loosen the **red-base discharge** floor: a base already **confirmed** red is a deadlock that needs
a proven union to discharge (`merge-operations.md`), not a not-red-gate bypass — not-red admission
covers the ordinary *pending* case that rule doesn't address, never a base already known to have failed. Nor
does it touch *cadence* (the independent-queue-cascade section above, on how **often** the seat re-evaluates the
queue) — this is the check's **threshold** (which base state admits the next merge); the two **compose** — a
not-red threshold applied at whatever cadence — they do not overlap. It is exactly as narrow as the
serial-fallback carve-out already states: wait for the base between merges only where a true dependency stack
cannot share one union.

**🚩** a seat that requeries the base's full check suite to **green** before admitting each next member — paying
a base-CI cycle per merge inside what was supposed to be one draining window — or a batch that closes with no
post-drain check confirming the union of merges actually landed green.

## Flipping the whole draft stack to ready at once floods the shared runner pool without feeding the serial seat any faster — stagger the ready-flips

The two sections above govern the merge **seat** — one serial holder, admitting the next merge on a not-red
base. This governs the step *upstream* of the seat: the draft→ready flip that makes a PR eligible in the first
place. The reflex, once a wave of lanes is done, is to flip **every** draft to ready at once "so the seat can
start merging them" — but that buys no throughput and courts an incident.

- **The flip is not the merge, and the seat is the bottleneck.** Readying a PR does not merge it; it only makes
  it a *candidate*. The seat still merges one at a time (*single-seat, back-to-back draining* above), so the
  merge rate is capped by the seat and the base's CI cycle, not by how many PRs are ready. Twenty ready PRs and
  four ready PRs drain through one serial seat at the same rate.
- **What flipping to ready *does* fire is the heavy CI suite — per PR, into a shared pool.** Draft PRs commonly
  run only the fast tier; the browser / a11y / visual / E2E matrix is gated on ready-for-review or a label
  (*Draft-gated heavy checks*, below). So flipping N drafts to ready at once dispatches
  **N heavy check-suites into a shared runner pool simultaneously**. The pool has a fixed concurrency, so the
  surplus past it **queues**: every check on every PR sits `pending` for many minutes, the fast checks that
  would have gone green quickly are stuck behind the flood, and the seat is *starved* anyway because nothing
  reaches green promptly. Pushed far enough it is a self-inflicted **runner-drain incident** — the shared pool
  is exhausted for every other lane and repo on the account, not just this queue.
- **Stagger the flips to a small in-flight window; drain, then flip the next.** Hold the count of *ready*
  (CI-running) PRs to a small window sized to the runner pool — a low default such as 3–4 — flip that many
  draft→ready, let their suites finish and the seat drain them, then flip the next batch. Same eventual
  throughput (the serial seat was always the cap), a steady green pipeline the seat consumes at its own rate,
  and no pool exhaustion. This is the WIP-cap-by-landed-artifacts discipline (above) applied to the
  **ready-flip** admission point and bounded by the **runner** budget rather than local RAM.

Distinct from *single-seat, back-to-back draining* and *the window's admission check is not-red* (both above):
those govern the **merge** action — how many *seats* (one) and which base state admits the next *merge*
(not-red, so "take all currently-green in a burst" is right *for merging*). This governs the **ready-flip**
action upstream of the seat — how many PRs have their heavy CI *in flight* at once — whose cost falls on the
shared runner pool, not the base-diff gate; readying all at once and merging all already-green at once are
different actions on different resources. Same shape as
*a shared API/model quota is a fan-out ceiling no local probe can see* (above) — a shared external budget a
local box cannot observe — but the resource is the **CI runner pool** and the lever is staggering
**ready-flips**, not narrowing model lanes, and the failure is checks **pending** (queued), not lanes
**erroring** on a rate limit. **🚩 tell:** a wave of lanes finished, all drafts flipped to ready in one sweep "so
the seat can merge them," then every PR's checks sit `pending` for many minutes while the serial seat merges
them one at a time no faster than a staggered flip would have — and other work on the account stalls on a
drained runner pool.

## A moving base under a stack of dependent lanes: merge it in, don't rebase onto it — and verify a self-reported "rebased" claim

The `red-gate-triage.md` section on a landed flaky-test fix rebases a **single** queued branch onto a landed fix — safe because nothing downstream depends
on that branch's SHAs. A **stacked** lane (a child branched off a parent's still-unmerged branch, `SKILL.md`'s
*A stacked/child lane branches off the parent's LOCAL ref*) is different: rebasing the parent onto a base that
keeps moving rewrites every SHA the child already built on, so each parent rebase forces every child to redo its
own rebase, and a base that moves repeatedly compounds this. One observed run: the base moved 3 times in 2
hours under a stacked set of lanes; agents reported "rebased" without it being verified — a merge (or a straight
force-push with no actual rebase) is indistinguishable from a genuine rebase in a self-report. **Rule: merge the
moved base into the stack, never rebase the stack onto it**, while lanes are
stacked — a merge commit preserves every SHA the children already reference, so no child needs to redo anything;
reserve rebase-onto-base for an unstacked, single branch. **Check:** `git merge-base --is-ancestor <old-head>
<new-head>` — non-zero exit on a claimed "merged" update means the old head was **not** kept reachable (a
disguised rebase or a force-push, not the claimed merge), and the reviewer treats the claim as unverified until
this passes.

## An opt-in throughput lever is inert until the default path takes it — attribute the gain to what runs by default, not to the merge

The throughput-lever instance of `SKILL.md` G2's "a cap that defaults to off is not a cap": when a CI/delivery
optimization ships as an **opt-in** capability — a `test:affected` script, an `--affected` flag, a gate mode
gated behind an env var — *merging* it speeds nothing up. The number moves only once the capability is wired
into the **default** path the pipeline actually runs: the CI job, the default gate script, the drainer's own
gate invocation (the diff-affected lever named above is the concrete case this attaches to — run only
diff-affected tests **by default**, not as a flag a caller must remember). This is the general
**beware-the-proxy** discipline — a merged PR is a proxy for the outcome, not the outcome itself
(`deep-code-review`'s `report-format.md`; gate epistemology principle 11 lists "Integrated to the mainline (G7)"
among the same proxy states) — applied to a throughput lever specifically, not a restatement of it. The
identical shape already gates a *safety* control elsewhere in this suite: "a shipped default or an opt-in
example — a demo gate that lives in `examples/` and is never loaded is not a control" (`deep-code-review`'s
`security-ai-agents.md`). An opt-in throughput lever left unwired is the same non-control, priced in CI minutes
instead of risk.

- **Attribute the gain to the default path, not the merge.** Confirm the actually-run surface takes the fast
  path **now, by default** — not merely that the capability exists behind a flag someone could pass.
- **Name the wiring-in as its own tracked deliverable.** If it is blocked — a held PR that owns the workflow
  file, an owner-gated config change — the merged capability is **inert**: real spend already paid, zero
  throughput gain realized. Say so; don't count an inert capability as the delivered speedup.
- **Measure before/after on the real job's window, not the capability in isolation** — the same
  p50/p95-of-time-to-green, attribute-the-percentile-to-a-stage discipline this suite already requires before
  adopting a build/CI platform (`deep-code-review`'s `release-engineering.md`; not re-taught here). If a speedup
  *did* show up that session, trace it to a specific, named change before crediting the opt-in lever for it — a
  different change landing the same session is the more common explanation than an inert flag that nothing's
  default path invokes yet, and mis-attributing it buries the change that actually worked.

**🚩** a status update crediting "we shipped the `--affected` flag, CI is faster now" without ever confirming the
default job invocation passes `--affected` (or equivalent) — the merge got credited; the wiring, which is what
would have actually moved the number, did not happen.

## Affected-only test selection by import graph misses tests that read repo files by path string

A fast gate or train that runs only the tests "affected" by an import graph skips every test that reads a repo
file by path string: doc pins, ledgers, fixtures, size budgets. Edit such a file and the importing code is
unchanged, so the pinning test is never selected, goes unrun, and the base turns red on the next full run.

1. The selector also picks any test whose source contains a changed file's repo path (a plain substring match on
   the repo-relative path), in addition to the import-graph picks.
2. Unsure → full suite: a changed file the selector cannot map, or a selector error, runs everything.
3. A base-red fix rides a solo train, never inside a full train, so the red base is cleared by one change that
   is itself fully tested rather than hidden among other members.

**🚩** a green affected-only run on a diff that edits a doc, ledger or fixture, while the full suite on the
same tree is red.

## A heavy slot guards the contended stage, not the whole train

A per-kind slot (or lease) held from the start of a train to its end serializes trains on an idle host: the setup, union
build and lint stages do not contend for anything. Scope the slot to the stage that does (the browser or e2e run, one shared
database, one port range) and take it per stage with a bounded wait; `stage_run.py` is per stage (`train-verify`,
`train-browser`, each re-run), and `train_land.sh` drops its exclusive lease while it waits for a full slot. Check that a new
gate takes its lease around the contended command, not around the whole script.

**🚩** two trains queued on a host with idle cores because one holds a slot across stages that share nothing.

Cap live heavy trains, not just workers per train: a Kanban WIP limit on the contended stage, since by Little's Law lead time = work in progress / throughput, so extra concurrent trains past the host's capacity lengthen every train's wall time (a measured peer ran 5 at once, load1 113, a 25-min suite blew its 60-min box, landings fell to 6/day). Policy `train_gate` (`shadow` default logs WOULD-BLOCK, `enforce` holds; `heavy_trains`, default 1) lets one `train-browser` stage plus one prepared train run; the rest wait before compile/unit.

## CI-offload the heavy gate by default — lane weight, not lane count, drives memory cost

A lane that runs a project's full local aggregate gate — a real build plus the complete browser/E2E suite plus
any slow lint/audit step — boots many headless-browser processes per run and is the dominant memory cost on a
shared machine, not merely "one more lane." A lane running only the fast tier (lint, unit, type-check, at most
one targeted spec relevant to the diff) costs a small fraction of that. With several full-gate lanes running at
once, the machine's memory gets consumed even when each lane's own resource check passed at spawn time, because
the check ran before the browser-heavy phase started, not during it. Default a lane's own local verification to
the fast tier, and let CI's own — ideally already-parallelized — jobs carry the full matrix. This sharpens
"verify on CI, treat a local run as the pre-check, never the evidence": defaulting every lane to the light tier
is the actual concurrency unlock — it is what lets several lanes run inside the RAM budget one full-gate lane
alone would otherwise consume — not a smarter resource-gate formula (previous section).

- **Run neither less nor more than the gate that actually admits your change.** The offload above trims a lane
  *down* to the fast tier; its converse trims *out* a suite CI does **not gate merges on at all**. A heavy local
  suite (a full browser/E2E run) absent from CI's required-check set is not a merge gate anywhere — running it
  locally as a blocking lane gate is **pure thrash**, spending the machine's scarcest resource (the
  headless-browser processes that drive the swap trend, *Gate on free RAM and the swap trend* above) for zero
  merge-safety (#935). Mirror of the delegated-green rule below (brief a lane with the **root** gate it is
  judged by at land): there a lane runs *narrower* than the real gate and false-passes; here it runs *wider*
  than any gate and thrashes. Match the local blocking gate to CI's **actually-enforced** set — no less, no
  more.
- **When a heavy run still thrashes the box, shed by process class, not blindly.** A lane tearing down its
  **own** helpers the moment their step ends (*kill a lane-owned helper*, below) has a selection rule to get
  right under memory pressure: the test-runner's **managed/headless browser** processes are the disposable mass
  to kill, while the **app's own dev server** is load-bearing for the UX gate and must be
  **protected by its port/PID**, never swept with them. This adds only **which** processes are safe to shed on a
  lane's own live-teardown path; the **orchestrator-level** sweep of *orphaned* processes stays advisory and
  approval-gated (*the orchestrator also owns reaping orphaned heavy processes*, above), and the kill mechanics
  (own a process group, terminate by pgid) stay in `deep-code-review`'s `concurrency-shared-state.md` — not new
  authority to kill.

## Draft-gated heavy checks hide a UI-regression wave — run them somewhere while the draft is open

The section above offloads the heavy gate to CI — but CI commonly runs those expensive jobs (headless-browser,
a11y, visual/hydration, UX audit) only on ready-for-review or a label, with drafts running the fast tier alone.
When a large change lives as a long-lived **draft** across many sub-lanes, every lane reads fast-tier-green
(lint / unit / type-check) while a whole class of **browser-only** defects — responsive breakage, focus-visible
/ keyboard, truncation without an accessible name, SSR hydration mismatches — accumulates unobserved. Flipping
to ready then surfaces the whole wave at once, late, as a regression. Fast-tier-green is **not UI-correct**; no
unit/typecheck gate observes those signals. Two fixes: (a) run the heavy/browser gates on the
**integration branch periodically** while the draft is open, or (b) explicitly
**budget for a late regression wave** and never present a stack of fast-tier-green lanes as demo-ready.
Browser-only signals are the **coordinator's** to verify centrally on the rendered page, not delegated to lanes
whose own gates cannot observe them.

**An OOM-killed train moves, it does not retry in place.** A train killed with SIGKILL during the unit-test step will be killed again on the same loaded machine. Move the train runner to the least-loaded machine and re-run the union there.

**Every PR gets an independent review before it merges.** Field data: 2 of the last 40 merged PRs in a fleet had any
non-author review. The default is now a deep-code-review DIFF pass plus an evil-twin check by a reviewer other than the
author, recorded as a receipt for the exact head being merged. `scripts/review_gate.py` runs inside `land_train.sh`
per member PR (so `train_land.sh` inherits it) and accepts either `.perun/reviews/<pr>.json` (write it with
`review_gate.py receipt <pr> --reviewer R --author A --head SHA`) or a PR comment containing
`<!-- perun-review reviewer=R author=A head=SHA diff=pass evil-twin=pass -->`. The reviewer must differ from the author
and the head must match, so a review of an older push never covers a newer one. It proves an independent review RUN on the current head, not a different human (agent reviewers often share the author's
GitHub token, so the gate logs "same-account review: run-id separation only"), and is a process receipt, not a
signature. Policy key `review_gate` in `.perun/policy.json`: `warn` (default; **warn-only for this release**, prints a
WARN and merges anyway), `enforce` (skips the PR; `land_train.sh` prints `REFUSE #N no independent review`), `off`
(opt out). Expect `enforce` to become the default in a later release.
Policy key `lockfile_skip_review` (`on|off`, default `off`): with `on`, `review_gate.py check <pr> --head SHA --audit-clean` passes a PR with no
receipt when every changed file (and every rename source) is a lockfile from a fixed list (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`,
`poetry.lock`, `Cargo.lock`, `Gemfile.lock`, `go.sum`, `uv.lock`, `composer.lock`, matched by exact basename), the PR's current head equals `--head`,
and the PR has fewer than 100 files; any other case fails closed to the normal receipt check. `--audit-clean` is the caller's assertion that
the dependency audit diff for that head is clean; the gate does not run the audit.

## Releases publish right after each land, from the lander's box, not a CI runner

Tags and GitHub releases lag main when publishing is a manual afterthought (the latest tag sat 21 versions behind). The
lander runs `scripts/land-release.sh publish` immediately after each merge lands on `origin/main`. It is a no-op unless
`origin/main` is at this checkout's version; otherwise it pushes the annotated tag (as `tag` does), then runs
`gh release create v<X> --title "Perun v<X>" --notes-file <file> --verify-tag --latest`, the notes being the CHANGELOG
section for `<X>` plus a link to the full CHANGELOG. Re-running is safe: an existing release only has its notes updated
(exit 0), and an existing tag is never moved (a tag on another commit, local or remote, is refused). Batching option:
policy key `release_every` in `.perun/policy.json` (integer, default 1 = every merge) publishes only when the minor
version is a multiple of N, so `release_every: 5` releases every fifth merge; skipped merges are covered by the next
release's CHANGELOG section. Publishing every merge needs no GitHub Actions minutes, so `github_actions=off` stays off.

## Fleet delivery rules: keep the gate real, size trains by footprint, merge one at a time, pin every guard

- **Never swap a slow or hanging gate for a weaker proof.** Replacing the browser run with unit-only let about 900 merges
  through while trunk accumulated 110+ unseen browser failures. Fix the gate (affected selection, sharding, caching).
- **Train by footprint.** A change outside the app needs no browser run, app batches stay small, and a lockfile or
  framework bump lands alone.
- **Under high merge churn, resolve, push and merge each PR one at a time, immediately**; a batch of resolved PRs goes
  stale before the last one lands.
- **Pin every guard with a contract test that fails if the call or rule disappears**, and prefer symptom alarms
  (trunk-green %, merges per day, gate p50 drift) over a check that only proves the guard exists.

## Make the train the only voucher: require `perun/train-gate` (one-time, owner step)

An agent that self-merges on unit-only proof bypasses the train and can turn the integration branch red. In the real
`merge_train.py merge --apply` path, right before each member's merge, the train posts commit status `perun/train-gate`=success
on that head (overwritten with `error` if the merge fails; dry-run and `verify` post nothing; `--no-status` opts out; a failed
post prints `WARN ... NOT posted`). Once, in the repo's branch protection or a ruleset on the base branch, add
`perun/train-gate` as a required status check; nothing here creates it. Then only train-verified heads can merge.
`operating_selfcheck.py --base <branch>` prints `WARN: train-gate` when the base does not require it, and
`COULD_NOT_CHECK` (never green, never "not required") when protection or rulesets cannot be read; it matches the name only.

**Trains self-limit; external stops are human-only in agent hosts.** An agent host refuses agents that kill or cancel a running workload, so a train bisecting a red base can run for hours until a human steps in. `train_land.sh` therefore stops itself: a wall-clock budget (`train_budget_min`, default 90) and a cap on whole gate rounds (`train_max_bisect_rounds`, default 8; the first gate plus split halves, not per-PR bisect steps), each stage timeout clamped to the budget left. On exhaustion it releases its locks and leases, prints the culprit-suspect PRs and exits 5 (DEFER; exit 4 stays "lease held, nothing built"); `BASE_RED_FAILFAST=enforce` ends a train on a red base at once with no bisect (default `shadow` until replay evidence). `merge_train.py verify` takes `--budget-min` and `--max-rounds` with the same exit 5.

**Roll pipeline-script updates by draining, not killing.** CI pins the pipeline definition per run; for a train what is pinned is the `train_land.sh` private copy and the loaded `merge_train.py`, while helper scripts (`land_train.sh`, `perun_policy.py`, gate commands) are re-invoked fresh from disk. A running train therefore finishes and lands on its own version; `STALE_SELF_EXIT=enforce` is checked only before a gate starts (a shadow log for an edit made mid-bisect now appears at the next cycle start). An urgent stop is explicit (`touch <log>.cancel` for `train_land.sh`, honored at every tick and right before landing; `<run-id>.stop` for `merge_train.py`, honored in every poll and gate; both exit 6) and belongs to the human operator or an owner-approved tool, never an agent cancelling a peer's train.

**A fixes-only train lands only if its union fixes every red title on the base.** `train_land.sh` reads a `FIX_MAP` (`<pr><TAB><red title>` per line) against the base's red set (`BASELINE_FAILS`); a red title with no fix PR in the batch is uncovered, so no train starts: it prints those titles (lane them first) and exits 4 (DEFER). `FIXES_COVER` is `shadow` by default (logs the would-DEFER), `enforce` acts. It checks coverage only; fixes-first ordering is `feeder_order.py`.
