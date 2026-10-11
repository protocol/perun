# Fast agentic delivery — verification and handback discipline

Read this when: delegating visual/parity work by measured number, running or finalizing verification, writing a
lane's definition of done, recovering a stranded PR, judging a lane's liveness or a plugin's forks, timeboxing an
open brief, verifying a release head or a delegated green, carrying a `Verify:` line, joining a fan-out review,
relaying a subagent's findings, checking a brief's prohibition against its effect, or briefing a context-inheriting fork. Part of the
`fast-agentic-delivery.md` lesson ledger — its index, sources, and cross-references live there; an "above"/"below"
pointer to a section not in this file resolves through that index.

---

## Chunk verification batches

A big verification batch handed to one lane fails: lanes stop after a few items. Split it into chunks of about 10 items per lane, each item with its own browser check.

---

## Confirm a reported gap exists in the code before briefing a fix lane from it

A peer or the owner reporting a gap from the **running app** ("this editor doesn't autosave") is a lead, not a
confirmed defect — the report names a symptom observed at one entry point, and the conductor briefing a fix lane
straight from it skips the same evidence step *An acceptance criterion with no test is `unverified`* already
requires on the review side (`roles.md`). One observed run: a conductor briefed a fix lane from exactly this kind
of report; the lane spent about 40 minutes and found the named component already autosaved (restore on reopen,
save on keystroke, clear on submit, all pinned by tests) — the report had most likely described a different entry
point or a transient state.

- **Spend one search before dispatch.** Grep the named component for the feature's storage key, hook, or handler
  — cheap, and it turns the brief from an adjective ("it's missing") into evidence.
- **Brief the lane with that evidence, not the raw report:** `"absent: no reference to <X> in <Y>"`, or
  `"present in <Y>; reproduce the failing entry point first"` — never the bare complaint.
- A lane that opens by **reproducing** the gap is cheap regardless of outcome. A lane that opens by **building the
  fix** can burn its whole budget proving there was nothing to fix.

## Delegate visual / parity work by measured number, not adjective

A qualitative brief for visual/parity work handed to sub-agents ("make this match that") does not converge: each
lane guesses at values and returns output that needs repeated re-fixing — the same eye-tuning oscillation a
single reviewer would have had, now distributed across lanes. Convert the acceptance criterion to
**measured numbers up front** — the reference's rendered device-pixels, the scale ratio between the two
renderers, the exact target per property (cross-ref `deep-code-review`'s `rendered-parity.md`, "match by
measured device-pixels, not user-space units"). Hand the lane those numbers plus the instruction to
**match by measurement, not tune by eye**; the lane derives values deterministically and returns a measurement
table. The coordinator confirms that table against the reference's rendered output — never a lane's
self-assessed "matches now." If you cannot state the number, the orientation step is to **measure it**, not to
delegate "make it look right."

## Run verification in the foreground — a backgrounded gate loses its verdict

A sub-agent told to run the gate suite that launches the long command **in the background** and then ends its
turn "waiting for it to finish" loses the result: a sub-agent's own background task does not reliably notify the
**parent** once the sub-agent has exited, and the turn ended before the run completed — the verdict lands in a
buffer nobody reads. Run gate/verification commands in the **foreground (blocking)** so the result is in the
agent's own report, or redirect output to a file the parent **explicitly reads after** the process ends. Never
end a turn waiting on a background task whose completion notifies only the exited turn. A machine-readable
last-run status file (some runners write one) lets the parent read the verdict without re-running.

## Land the fix, then finalize separately — a helper process or a retry loop must not orphan a draft PR

A lane that opens a **draft PR early**, then does async finish-work (screenshots that need a dev server, a
changelog fragment, evidence capture), can leave an **orphan draft** — code green, but no evidence and never
promoted to ready — when the finalize tail never completes: a lingering child process (a dev server holding the
turn open) or a retry loop on a flaky step burns the turn before the promote step runs. The draft reads as
abandoned, and its banked work is invisible until someone adopts it.

- **Decouple fix-landing from finalize.** The moment code + gates are green, ready the PR (or open it
  non-draft); make finalize (evidence, changelog fragment, promote) a
  **separate, idempotent step any actor can complete** — not a tail the same turn must reach or the work is
  lost.
- **Kill a lane-owned helper the moment its step ends**, never deferred to end-of-run where it can hold the turn
  open past finalize (teardown mechanics — own a process group, terminate by pgid — in `deep-code-review`'s
  `concurrency-shared-state.md`).
- **Bound every flaky finalize step** to N attempts / a wall-clock cap, then **fail to a report** (the diff + a
  text `Verify:` note) rather than loop — a can't-run is not a found-problem (principle 3), and a retry loop
  must never stand in for delivery.
- **Orchestrator sweep:** a lane that reported done, or was killed, while its branch has a draft PR missing
  changelog/evidence is **adopt-and-verify or explicitly discard**, never left to rot. (Sibling to
  *run verification in the foreground* above: there a **verdict** is lost to a background task; here the
  **promotion** is.)

## A "stop when fixed" / minimal-patch contract truncates the lane's definition of *done* — fold the post-fix process steps into acceptance, or own them explicitly

The section above orphans a draft when a **process** (a lingering server, a retry loop) burns the turn before
the finalize tail runs — the lane *tried* to finalize and was cut off. This is the adjacent failure with a
different root: the lane **stops on purpose**, having met a definition of *done* that never included the
finalize steps. A lean-build / minimal-diff / "stop when the fix is in and tests pass" contract — a compression
or cost policy applied to the lane — defines completion as **code-fix + gates-green** and treats everything
after as out of scope. So the lane opens a draft PR, greens the fast gates, and **stops** — skipping the
required post-fix *process* steps (write the changelog / release-note fragment, flip draft→ready, attach the
evidence) even though the brief listed them. The PR is left **stranded**: draft, and red on the
missing-changelog check, with a correct fix banked behind it.

Why the brief alone does not save it: a standing process-policy default ("minimal patch, stop when fixed") is a
**stronger, always-on** instruction than one line buried in a task brief, and where the two conflict the lane
follows the default and drops the brief's tail. This is the mirror of
*a prohibition in a delegate's brief is a soft control* (below) — a **required** step dropped rather than a
forbidden one taken — so naming the steps in the brief is necessary and **not** sufficient.

- **Fold the process steps into the lane's acceptance / definition-of-done, so "fixed" is not "done" until they are done.**
  The Work-item contract's *Done-when* (`SKILL.md`, *Output contract*) must enumerate the changelog fragment and
  the ready-flip **as acceptance criteria**, not as a post-script — a lane whose *Done-when* is "the fix and its
  process artifacts are all in, PR ready" cannot satisfy its own contract by stopping at green code. Change what
  *done* **means** for the lane; do not merely repeat the steps.
- **Or the orchestrator owns the process tail explicitly.** If lanes are deliberately kept minimal, make the
  changelog fragment + ready-flip the **orchestrator's** named job (the same small, mechanical finalize the
  *stuck self-polling lane* rule, below, has the orchestrator finish directly), assigned to one owner. One of
  the two must own the tail; the failure is when **neither** does.
- **Key the changelog fragment by branch, not PR number** (unknown until the PR exists → a second push and gate):
  `changelog.d/$(git branch --show-current | tr / -).md`, and any fragment check keys off the head branch.
- **Host blocks "ready on green" as unreviewed?** `surface_check.py attested … && gh pr ready …` passes only on a
  non-author `board_post.py --type REVIEW` at the exact head (a push voids it); the host's decision stays final.
- **Once CI skips drafts and runs only on `ready_for_review`, gate the ready-flip on `attested` (review + finish
  criteria), never on green checks** — a draft sitting at zero check suites is the expected state under that CI
  config, not a platform anomaly to escalate; pass `--draft-skip-ci` to say so explicitly in the reason, and keep
  requiring green at the merge step (`checks`/`--wait`) regardless.
- **A draft red only on a missing changelog fragment is a stranded-by-contract signal, not a defect.** Read it
  as this pattern — the fix is sound, the process tail was truncated — and complete the tail (fold-in for future
  lanes, finish it now for this one), rather than re-reviewing the code for a fault that is not there.

Distinct from *Land the fix, then finalize separately* (above): there the finalize was **attempted** and
orphaned by a process / retry loop burning the turn — the fix is to *decouple* landing from finalize, make
finalize idempotent, kill helpers, and bound retries. Here the finalize was
**never in the lane's definition of done** — nothing crashed; the lane met its (too-narrow) contract and stopped
— so the fix is to **widen the acceptance contract** (or reassign the tail), not to harden a tail the lane was
never going to run. The two compose: a decoupled, idempotent finalize (that section) *plus* a definition of done
that actually requires it (this one). **🚩 tell:** a fix lane under a "minimal patch / stop when fixed" policy
that closes out at green code with an open draft PR red on a missing changelog fragment — the process steps were
in the brief but not in the lane's *Done-when*.

## A stranded PR has no live owner, so two actors both recover it at once — claim the *unstranding*, and assign it to one owner

The two sections above are how a PR gets **stranded** (a truncated finalize contract,
#967 just above; a finalize tail orphaned by a process) and that an orchestrator sweep
should recover it. This is the failure *in the recovery itself*. A stranded PR — draft, or red only on a missing
changelog fragment, its lane stopped and its worktree reaped — has **no live owner**, and an orphan with no
owner attracts **two** recoverers at once:

- the **producer**, whose own lane is resumed or redispatched to finish what it left (the
  *adopt-and-re-verify a prior generation's worktree/branch* path, above), and
- the **merge-seat holder**, which finds a nearly-green PR blocking its drain and **unstrands it to merge**
  (adds the missing fragment, flips it to ready) to clear the queue.

Both write the **same branch** to complete the **same** small tail, seconds apart — a dual **push** to one ref:
a non-fast-forward for whoever loses the race, a force-push clobber if either overrides, or two divergent
"finish" commits (one adding the changelog fragment, one flipping ready) that collide. It is not dual *work* on
disjoint files (*an ownership map blocks a dual write, not dual work*, below) — it is dual *write* to one
branch, exactly what one-writer-per-branch forbids, arising here because the branch's writer had **stopped** and
nothing re-established a single owner before two parties reached for it.

- **Recovering a stranded PR is an exclusive step — claim it before acting.** Unstranding is a write to a
  contested branch, so it takes the same claim any exclusive step takes: an entry naming the single current
  owner of *this PR's recovery* (the `exclusive_role` field of the claim registry,
  `multi-session-coordination.md`, applied to unstranding, not only to the merge seat). Check it and refuse to
  recover a PR another owner is already unstranding.
- **Assign unstranding to one role by default — the merge-seat holder is the natural owner.** The seat is
  already serialized and already touches the branch to merge it, so folding "finish the tail, then merge" into
  the seat avoids a second writer entirely; the producer, if resumed, reads the recovery claim and
  **stands down** on any PR the seat is unstranding. (Either owner works — the invariant is *exactly one*, not
  *which one*.)
- **Verify the in-flight write actually landed before concluding recovery** — never the recoverer's own "pushed"
  claim (the *confirm the write landed on the remote* discipline of the *stuck self-polling lane* rule, below),
  since a mid-race push can leave the branch partially updated.

Distinct from #967 just above (what **strands** the PR — a truncated lane contract) and from
*Land the fix, then finalize separately* (that a stranded draft must be **recovered**, adopt-and-verify or
discard): both establish *that* recovery happens; this governs *who* may perform it, because recovering an
unowned branch is itself a write that needs a single owner. Distinct from
*an ownership map blocks a dual write, not dual work* (below), which stops a duplicate lane spawning on a
**live** objective via an occupancy check — here the objective's lane is **dead/stopped**, so occupancy reads
empty and the collision is between two *recoverers* of the orphan, resolved by a recovery **claim**, not an
occupancy probe. Distinct from *shared VCS identity cannot attribute a PR* (`multi-session-coordination.md`),
which is *whose* PR it is under one shared identity — here ownership is not ambiguous, it is **absent**, and the
fix is to (re)establish a single owner of the recovery, not to attribute an existing one. **🚩 tell:** a stranded
/ draft PR that both a resumed producer lane and the merge-seat holder move to finish in the same window, ending
in a non-fast-forward, a force-push, or two divergent finish commits on one branch.

## A hard-to-write test must not hold a ready fix hostage — verify-first is a fails-before / passes-after floor, not a ceiling

Verify-first (the *Eliminate rework* lever above; the *test the failure* rule in `roles.md`) is a **floor**: a
bug fix ships with a proof that is **red on the current code, green after the fix**. It is **not a ceiling** —
it does not mandate maximizing test elegance, coverage, or realism. The failure mode is treating it as one. The
fix is small and correct, but its ideal test is disproportionately hard — a real DOM render, a fake timer racing
a framework scheduler, an async flush the harness won't cleanly await — and the lane keeps grinding the harness
past diminishing returns. The tree stays dirty, nothing is committed or pushed, and the correct fix has been
ready for most of that time. To an orchestrator watching only "no PR yet," a lane stalled *on the test* is
indistinguishable from one stuck *on the fix*.

- **Budget the test effort against the fix's value, separately from the lane's overall timebox**
  (*An open-ended brief…*, below). When the ideal test fights the harness past a wall-clock / attempt budget,
  **land the fix behind the cheapest artifact that still fails-before / passes-after** — a pure-logic port of
  the buggy control flow, a source-shape pin, a narrower assertion on the same behaviour — and open the PR. The
  full suite still gates the branch. A correct fix behind a **real, simple** proof beats a perfect test that
  never lands — the *smallest sufficient* instinct (`SKILL.md`) applied to the proof, not just the team.
- **The tracked follow-up is for the *fuller* test, never for *a* test.** Something that fails-before /
  passes-after ships **now**; only the DOM-level or real-scheduler version is deferred. This is why it is
  **not** the *"I'll add tests later"* anti-pattern (`SKILL.md`): the fix never lands with zero proof, so G4
  stays satisfied — the deferral is only the elegance the floor never required. Deferring *the proof itself* is
  the other failure and stays forbidden.
- **Hand the lane the known-hard-test escape hatch up front:** name the harness gotcha and point at the fallback
  pattern a sibling test already uses, so it doesn't burn the budget rediscovering the dead end.
- **Classify the stall by artifact, not by "no PR yet"** (same *judge by the product, not the clock* discipline
  as *A transcript's size or mtime…*, below): a **clean tree with a fix commit but no fuller test** is near-done
  — nudge *simplify the proof and push*; a **dirty tree with no commit** past the budget is stalled — nudge
  *commit the working fix, pin it with the cheapest assertion, push the draft*, which usually clears it in one
  round.

Distinct from *Land the fix, then finalize separately* (above): there the code is green and the **promotion** is
orphaned by a process or retry loop that burned the turn; here nothing crashed — the lane **voluntarily**
over-invests because verify-first reads as absolute, and its fallback is a **real G4 assertion**, not the
diff-plus-`Verify:`-note a can't-run *finalize* step falls back to. It extends `roles.md`'s *test-first* rule,
which states the proof requirement with no proportionality bound.

## Confirm a subagent is idle before dispatching a duplicate — a "completed" is not proof of terminal completion

The watcher-side complement to the foreground rule above. A coordinator that dispatches lanes off
task-"completed" notifications can be told a subagent finished **while it is still running**. The mechanism is
concrete, not mysterious: on a harness that fires "completed"
**each time an agent stops with no live background children of its own** — and can notify the
**same task-id more than once** — a subagent that has armed a background **monitor/watch** cycles stop→wake and
emits "completed" on **each** stop, none of them terminal until the agent truly exits. A single "completed" is
therefore **one of several**, not proof the work is done. **The tell:** a repeated/duplicate "completed" for the
**same task-id**, or the agent's own last report still saying "waiting." The **defensive invariant**: before
dispatching a duplicate lane for the "remaining" work, **confirm the agent is actually idle** — check its live
state and those tells, not merely that a "completed" arrived — especially when the duplicate would write into
the **same worktree**, where a collision corrupts the run. This is the dispatcher mirror of "a backgrounded gate
loses its verdict": there the *doer* drops a result; here the *watcher* acts on a not-yet-final one.

## A transcript's size or mtime is not a liveness signal — never kill a lane on staleness

The **inverse** error to the section above, with a worse blast radius. Judging whether a background subagent is
alive, stalled, or dead from the **`stat` of its transcript/output file** (bytes unchanged for N seconds, mtime
older than a threshold) reads a signal that is not there: a transcript can lag the working agent by
**many minutes** — a long tool call, a quiet reasoning stretch, buffered/flushed-late output — and can look
equally "recent" for an agent that has already exited. Acting on the stat cuts both ways — it
**kills a still-working lane** (destructive: its in-flight work and worktree state are gone) or
**trusts a dead one** and waits forever / dispatches onto a corpse. Judge liveness from the agent's
**actual product**: a fresh work-tree diff or new commit, a live child process, an owned port/PID, or a direct
**ping it answers** — never from the transcript file's size or age. Killing a lane is a
**destructive, shared-state action** (principle 9 — closing or deleting shared state needs evidence, not
presumption): confirm the agent is genuinely idle by a *positive* signal before terminating. If nothing but the
transcript is observable, the honest state is **`UNVERIFIED`**, not "dead." **`scripts/lane_liveness.py
--worktree <path> [--pid N]`** computes this positive-signal read offline — ALIVE/QUIET/UNVERIFIED/DEAD from a
live process, file/git-state mtimes, and a CPU-time sample, never a kill verdict — so "slow, not stuck" is a
checkable report instead of prose alone (#1070). The same asymmetry governs *reuse*, not just kill: resuming or
re-assigning a lane into a worktree its previous agent may still hold requires this verdict to be **DEAD**,
never QUIET or UNVERIFIED (#1116) — `scripts/lane_guard.py`'s lane-start check enforces that by import. Distinct
from the Conductor's
context-isolation rule ("read status, not the raw transcript" — do not consume the transcript as *context*):
this is not reading its **file stat** as *liveness*. And distinct from the idle-before-duplicate section above:
that is a false-**positive** "completed" leading to a duplicate dispatch; this is a false-**negative** liveness
read leading to a destructive **kill**. A **served UI's** freshness is a different axis again — not *is the
process alive* but *does what it serves match the merge* — `dev-env-ownership.md`'s *"Latest" means the process
restarted and a fetched page proves it* section covers that case; a serving tree's git HEAD is not evidence there
either.

## A plugin's host hook auto-spawns forks you did not — judge them by external effect, not by unexpected provenance

The two liveness rules around this one forbid killing a lane on a false read of whether it is **alive**. This is
the adjacent misfire on a *different* axis — killing a lane on a false read of whether it is **yours**. Enabling
a comms or augmentation plugin through the host's **native plugin hook** can auto-spawn the plugin's own
**bundled helper-agents as fork subagents**. They show up in the agent/task listing as forks the orchestrator
never explicitly spawned and, being forks, inherit the parent's **full context**. To an operator scanning the
fleet for runaways and context-leaks, an unrecognized fork carrying the whole parent context reads exactly like
the thing to kill on sight — so the reflex fires, and killing it breaks the plugin (or the lane it augments)
though no defect ever occurred.

- **"I did not spawn it" and "it holds my context" are provenance signals, and provenance alone does not make a fork a runaway.**
  A plugin-spawned helper is doing its job; its surprising *appearance* is expected once you know the plugin
  spawns it.
- **Judge a fork by its external effect, not by who dispatched it.** The kill-relevant question is whether it is
  doing damage — mutating shared state, opening PRs, burning budget without producing, holding a worktree it
  collides on — not whether it is on your own spawn ledger. Enumerate the effect surfaces the *refrained-action*
  check below already lists (remote refs, open PRs, the per-agent tool-call record); a helper touching none of
  them is not a kill candidate however unfamiliar. Killing is a destructive shared-state action (`SKILL.md`
  principle 9): the precondition is a **positive signal of harm**, never the mere absence of a spawn record.
- **Remove the surprise at the source.** When you enable such a plugin in a monitored fleet, announce on the
  coordination channel that it spawns bundled forks, so a watching operator or peer does not classify them as
  runaways in the first place — the provenance-attribution problem a shared identity creates
  (`multi-session-coordination.md`), here applied to *spawn* provenance rather than *authorship*.

Distinct from *a transcript's size or mtime is not a liveness signal* and
*don't conclude a lane is dead from an indirect signal* (both above): those stop a kill of a suspected-**dead**
lane on a false-negative liveness read — the question is "is it alive?" Here the fork is plainly alive and that
is not in doubt; the false trigger is "is it **mine**, or a runaway/leak?" — a provenance misread — and the
right test is harm-to-shared-state, not liveness.

**🚩 tell:** an operator or orchestrator terminating an unfamiliar fork solely because it was not on the spawn
ledger or because it carries the parent's context, with no check that it is actually touching shared state or
doing damage — especially just after a comms/augmentation plugin was enabled.

## A lane looping in its own self-poll can't receive a nudge — verify the state, stop, and finish the last step yourself

A worker that finishes its substantive work and enters a wrap-up phase where it
**self-polls a background job it started itself** — watching its own CI run, waiting for its own push to land —
before formally handing back can loop there a long time, in the worst case indefinitely. The mechanism is
specific: some agent runtimes check the inbox for
**new orchestrator messages only at the start of a fresh reasoning/tool round**, and a lane busy inside a tight
self-poll never reaches such a round. So a re-nudge queues **unread** behind a loop that will not yield to it
soon, or ever — **re-nudging is a no-op**, and waiting longer does not help, because the lane is not blocked on
missing information, it is blocked on its own polling loop. The orchestrator that reads each "done, but
background work still running" tick as "still in progress, give it more time" babysits a lane it can neither
reach nor speed up.

- **Detect cycling-*without-progress*, not just "still running."** If a lane's own externally-checkable state —
  branch head, PR existence, PR check results, files changed — is
  **identical across two or more consecutive self-poll pings**, treat it as a candidate stuck state; a
  genuinely-working lane usually shows some forward movement between pings. Repeating "completed, background
  work still running" with a frozen external state is the tell.
- **Verify the durable state directly, not the self-report.** Query the remote yourself — is the branch pushed,
  is the PR open, which specific step (if any) is actually missing — rather than trusting the lane's narration.
  The remaining work is routinely **trivial and does not need the lane at all**: the branch is already fully
  pushed, the PR is already open, and the only gap is a small mechanical step (a changelog/release-note
  fragment, a "ready for review" flip, one finalize command) — coordination and merge-plumbing steps are the
  orchestrator's own job anyway.
- **Escalate straight to *stop*, not another nudge — but verify before stopping.** Stopping a lane is a
  destructive, shared-state action (principle 9), and a lane may be mid-write. Confirm any in-flight write
  actually **landed on the destination** (the remote branch/PR), never the lane's own "the push succeeded"
  claim, before terminating; stopping mid-push can leave a partial or corrupt state behind.
- **Then finish the last mechanical step yourself.** Once the durable state confirms the only remaining work is
  small, well-defined, and low-risk, do it directly rather than keeping a whole agent — and its context and
  budget — alive, or spawning a fresh one, for a one-command finalize.

Distinct from **confirm a subagent is idle before dispatching a duplicate** (above: a false "completed" invites a
duplicate dispatch; here the lane is alive but unreachable, so stop-then-finish, never a duplicate); the
receiver-side companion to **a monitor emits on state-transition or terminal state only** (below). Finishing the
step yourself is not Conductor drift (`SKILL.md`): the lane cannot be nudged or re-dispatched, and the residual is
a minimal finalize step, the exception that rule already carves out.

**🚩 tell:** an orchestrator sending nudge after nudge to a lane whose externally-checkable state has not moved
across several pings while its own reports keep saying "done, background work still running" — the nudges are
queuing behind a self-poll that will never read them, and the trivial remaining step could have been finished
directly turns ago.

From `SKILL.md` **Failure** — the converse of *a running lane is not a finished one*, which that section keeps:

- **The converse: a lane's scope ends at its own finish line, not at the
  merge.** Once a lane's PR is open with its gates green, its job is done — it
  does not loop re-checking CI for a merge that is the Conductor's (or a merge
  guard's) job. Re-polling a green PR burns turns on unchanged news; report
  once, then stop — the "event-driven, not polled" discipline applied by a lane
  to itself.

## An open-ended brief gives the judge nothing to judge — timebox it and require an interim checkpoint

The section above says how to **judge** a lane once you're looking at it — from its actual product, never the
transcript's stat. This is the upstream half: a lane dispatched open-ended, with no stated
**wall-clock timebox** and no **required interim durable checkpoint**, can leave nothing to look at until it
finally reports — no pushed branch, no commit, nothing but a running transcript for however long it runs, which
is exactly the state the section above warns against trusting *or* distrusting on the stat alone. Brief every
open-ended lane with both up front: an explicit **wall-clock timebox** for the whole lane, and a
**required interim checkpoint** — a pushed WIP branch or commit at a named milestone inside that window, not
only a final one — so liveness and sunk cost are always judged the same way the
*progress is a durable artifact, not a spawned lane* rule (below, in the unattended-time-budget section) already
grades a lane: by artifact, never by elapsed runtime or transcript activity. Prefer decomposing an open-ended
lane into **smaller, checkpoint-able sub-lanes** over dispatching one long opaque one — each sub-lane's own
finish is then itself a checkpoint, rather than manufacturing an artificial one partway through a task that had
none.

## Release verification runs on a frozen, quiescent head — a discovery pass runs during integration

The heavy verification run (full browser suite + production build + audit) is the longest-lived task in a
fan-out, which makes it the most exposed to two things at once: the integration branch **moving underneath it**
as feature lanes fold in, and **resource starvation** from those same lanes. Dispatched *alongside* active
integration it maximises both — and a verdict about head `A` delivered when the head is `A+9` describes a tree
that no longer exists. It is not wrong, it is *about something else*, and it is **worse than no verdict**
because it reads as reassurance and gets quoted downstream as "we verified it."

Two activities run the same commands but are different contracts — do not conflate them:

| | Defect discovery | Release verification |
|---|---|---|
| Purpose | find problems early | certify a specific tree |
| Target | any recent head | one **frozen** head |
| Timing | continuously, during integration | once, after integration **closes** |
| A stale result is | still useful as leads (re-confirm at the new head) | worthless (it certifies nothing) |
| Resource priority | yields to feature lanes | gets the machine to itself |

- **Gate release verification on quiescence.** Do not dispatch it while the integration branch is still
  accepting folds; gate it on the integrator reporting **no outstanding branches**. Run *discovery* passes
  during integration instead, and label their output **discovery, not certification**.
- **Freeze and name the head.** The lane records the SHA at start and re-checks it at finish; if the head moved,
  the verdict is **`STALE — tested <sha>, head is now <sha>`**, never a bare pass/fail (a verdict without its
  sha fails closed — `SKILL.md` *Exact revision*; and #192's verification surface, `deep-code-review`).
- **Give the heavy run the machine.** Schedule it when the fan-out is quiescent, or explicitly cut sibling
  concurrency for its duration; a verification run starved into a stall returns **no** information — the worst
  return on the most expensive task (the swap-trend and WIP-cap gates above size that quiescence).
- **Split the long run so partial progress survives.** unit/type/lint → browser → audit → deploy-preflight, each
  reporting independently; a stall in one phase must not destroy the earlier phases' results.
- **Bound verification debt explicitly — don't defer it every tick.** Track it as the count of
  merged-but-unverified changes and the age of the oldest (e.g. at most 3 / 30min, not a fixed repo constant).
  When CPU-saturated build lanes make the machine look too busy to verify, deferring the re-verify every tick
  while still admitting new build work lets debt grow **without bound** while capacity never frees (#1129):
  when the bound trips, shed or pause build-lane admission until debt clears — verification outranks new
  building. Under load, run a **cheap tier** (the committed evidence at the merged SHA, one targeted probe of
  the changed surface) instead of skipping outright, but it MUST report **reduced confidence** — "spot-checked,
  not full verification" — never upgraded to a plain "verified": the same *worse than no verdict* asymmetry
  above applies to a narrow check silently presented as a full one. Report debt every tick, so a stakeholder
  reading the log sees "merged" is not yet "verified."
- **Discovery findings are durable as leads; a discovery verdict is disposable.** Harvest the defects a
  discovery pass surfaces, but **re-confirm each at the new head before acting on it** — a finding carried
  forward without a re-run is `unverified`, not still-open (`deep-code-review` `method.md`) — and
  **discard the pass/fail**, never filing it as certification.
- **A returning reviewer re-confirming at the new head reads a digest, not the whole tree.** Run
  **`scripts/review_digest.py --since <last-seen-sha>`** for commits, per-directory +/- counts, flagged
  test/CI/config paths, and the diff stat since their last pass; review the flagged hunks the digest names, not
  a full re-read (#1080).

This composes with *a worktree assignment is a path… an integrator on a shared branch detaches* above: that
fixes **where** the integrator merges (a detached tree at the tip), this fixes **when** release verification
runs against it (after the tip stops moving) — different axes, not competing schedules.

## A delegated "verify green" in an isolated worktree is a lead, not the authoritative gate — re-run the full-repo gate at land

In a **delegate → review → land** pipeline, a subagent that builds in an isolated worktree and reports `verify`
**green** ran whatever gate its **partial environment** could — routinely **narrower** than the authoritative
one. The worktree tends to run a **changed-files or package-local** check while the real gate at land is
repo-wide, so a green lane verdict can sit on top of failures the full gate catches:
- an **unused-import / lint** error the worktree's changed-files pass skipped but root
  `eslint . --max-warnings 0` flags;
- **formatter diffs on files the change never touched** that root `prettier --check .` fails on but a
  package-local pass never saw;
- **coverage / cross-workspace / design-system** checks the worktree **literally could not run** (missing
  hoisted deps, an absent sibling package) — a *could-not-run* silently folded into a "green" that only ever
  meant "what I could run passed."

So **the authoritative gate is the full-repo run at integration** — through the real pre-commit hook / CI, on
the **integrated** tree — not the subagent's env-limited pass. This extends **CI-offload the heavy gate** above
("a local run is the pre-check, never the evidence") from the RAM-tiering case to delegation, with the
load-bearing addition that the authoritative run is on the **integrated** tree, not any single lane's. Treat a
delegated green as a **lead** (a discovery verdict, above: useful to proceed to review, never the
certification); **land re-runs the full gate** and *that* verdict is the one of record — a lane's green is
`unverified` until the integrated tree confirms it (`deep-code-review` `method.md`), so
**budget a fix-and-recommit at land** — a delegated green predicts *less* rework, never *none*.
- **🚩 tell:** a lane reporting `verify: green` from a `--filter=<changed>` / package-local run, or a
  `land`/merge step that trusts a subagent's verdict **without re-running the repo-wide gate** on the merged
  result.
- **After applying a captured diff (3-way / context / cherry-pick), re-run the formatter on the changed files before the land gate.**
  The apply itself **can** shift bytes — reindented context, whitespace/newline normalization, a relocated hunk
  — so a diff whose *origin* was correctly formatted can still land unformatted and fail the repo-wide
  `prettier --check` / `gofmt -l` at integration. Re-run the formatter on the changed files post-apply (don't
  trust the source was clean). And
  **brief the lane up front with the root / repo-wide gate it will be judged by at land** — not a
  workspace-local subset: naming the narrow scope proactively is what stops a lane building green against a gate
  narrower than the one that actually gates.
- **Before relaying any lane PR, run `lane_guard.py handback --sha <head> --base <dispatch-base> --branch
  <lane-branch> [--cite <path>]… [--artifact-root <dir>]`** — it refuses a "parked" claim git does not back: a
  head with no commit beyond `<dispatch-base>`, a branch tip other than the cited sha, a cited file not
  committed at that sha, or an absolute artifact outside `--artifact-root`. Beyond that,
  a parentless root/orphan head, one with no `git merge-base` to `<dispatch-base>`, or any root commit
  reachable in `<base>..<head>` (an unrelated-history merge can pull a second root in through a merge commit
  that has parents and a merge-base with `<dispatch-base>`), diffs clean and passes CI (the
  forge compares trees, not ancestry) yet explodes into a full-tree conflict on rebase; the check also refuses
  a shallow clone (truncated history can't prove ancestry either way) and a repo with a grafts file present
  (parentage rewritten underneath it), and forces `GIT_NO_REPLACE_OBJECTS=1` on every git call so a replace ref
  can't mask a bad parent. Fails closed on any of these, never a pass. Recovery: a fresh branch from
  `<dispatch-base>`, `git checkout <bad-sha> -- <paths>`, commit normally, then a force-push with an explicit lease
  (owner/standing-grant gated, same as any other force-push here).

This is the **inverse** of the symlinked-deps section below and the provisioning-gap section above (a worktree
too *poor* to run a check yields a false **failure** — "could not run" misread as red); here a worktree too
*partial* yields a false **pass**. Both reduce to one rule — a verdict is only as wide as the environment it ran
in, so **name the scope and re-run the authoritative gate at land** (the *could-not-run ≠ found-a-problem*
epistemology applied to delegation). Distinct, too, from the stale-verdict case above: there the verdict is
current-scope but a *moved head*; here it is a *current head* but *partial scope*.

## A completion claim in a PR body or handback carries a `Verify:` line, or it is unverified

A delivery lane's PR body, handback, or status that asserts a **verified outcome** — "confirmed in the browser,"
"it renders," "tested and working," "manually checked" — is a **self-reported claim, not evidence**: the trusted
control is the forge run pinned to the reviewed SHA (`deep-code-review` `merge-operations.md`), and even
a delegated lane's bare `verify: green` is only a lead (above). What makes the claim **auditable** is a line
naming **how** it was checked — a `Verify:` line: the exact command run, the surface / URL exercised, the
two-principal or anon probe, the evidence link. Without it a reviewer or the next agent cannot tell a real check
from a hallucinated one, and a false "done" is the costliest rerun — trusted, built on, surfacing late, far
from its cause.

So a delivery artifact that claims a verified result
**and carries no `Verify:` line stating the method is treated as `unverified`** — the reviewer asks for the
method, not the adjective. This is the over-claim rule (**name the evidence surface**, `deep-code-review`) applied
to the delivery artifact — a **claim-quality** requirement, **not** a trusted control: a typed `Verify:` line
makes the claim checkable, it does not replace the forge run.

- Especially when PRs are **agent-authored and reviewed by people who weren't watching**, "the gates are green"
  is a claim about the *code*; the `Verify:` line is a claim about how the *interface* was actually exercised.
  Pair it with visual evidence — the screenshot shows *what* changed, the `Verify:` line shows *how* it was
  confirmed.
- **Gate on it only if the producers emit it.** Landing a `Verify:`-required merge gate strands every automated
  lane that does not yet write the line — co-evolve the lane template in the same change, or ramp it (the
  co-evolve-a-body-gate-with-its-producers rule, `deep-code-review` `merge-operations.md`).
- **🚩 tell:** a PR body / handback asserting "tested," "verified," "it works," or "confirmed" with no `Verify:`
  line naming the command, the surface, and the evidence — an unbacked completion claim, `unverified` until the
  method is stated (still self-reported after).
- **Mechanize the surface half:** `scripts/surface_check.py` — **use this when** a done / fixed / deployed claim
  rests on a served app or a remote branch. `served --url U --expect-sha S --probe header:NAME` passes only on the
  serving process's own build id — none found, a payload timestamp, a redirect, or a non-200 exits 2;
  `ref --branch B --expect-sha S` fetches and checks reachability on the branch the reviewer uses, never a stale
  local tree (`--require-clean`: an edit a rejected hook left uncommitted fails); `checks` reads each check's own
  latest run, never a rollup (#1066). Its `--json` is the `Verify:` evidence, bounded by its `proves` field
  (never "the feature works").
- **A link handed to a human is probed at the exact URL, on rendered content, never on HTTP status alone.**
  `surface_check.py served` above proves the running build's *id*; it does not prove the *route* a human is
  about to open actually renders the feature — a feature-flagged page with the flag off can 200 a dev server's
  not-found render, and a probe run against a variant URL (a preview query parameter, an extra cookie) says
  nothing about the plain URL the owner will click. Before a link reaches a human: (1) probe the **exact** URL
  they will open — no extra query parameter, no cookie the probe added and they won't carry; (2) assert on a
  **content marker** — a DOM id/text unique to the real page and absent from the not-found/error shell (e.g.
  `curl -s "$URL" | grep -qF 'data-testid="landing-hero"'` and `! grep -qF 'data-testid="app-not-found"'`), or a
  screenshot someone actually looks at — never the status code alone (this generalizes the *exact-surface*
  confirmation below from "the reviewer looked at the right page" to "the link itself renders the right page");
  (3) when the route sits behind a flag, state that environment's flag state in the same message the link is
  handed over in.

## "No defects found" names the exact surface reviewed and how that was confirmed to match the brief, or it is unverified

A `Verify:` line (above) can name a real, specific surface and still be reviewing the **wrong** one: a similar-
looking screen, a stale route, a different variant reachable from the same nav. The line looks compliant —
command run, URL exercised, evidence attached — while the brief's actual target sat unreviewed the whole time.
This is a sharper case than the generic surface-naming rule: naming *a* surface is not the same as naming *the
brief's* surface, and a clean "no defects found" is the report most likely to hide the gap, because it produces
no artifact (no diff, no finding) that a reader can cross-check against the wrong page. Observed: a lane reported
a clean pass; a follow-up found it had audited a different page than the one named in its brief, and the actually-
targeted page had unreviewed, pre-existing defects.

**Rule: before reporting a result, a review lane confirms and states the exact route/URL/component reviewed and
how it confirmed that matches the brief's target** — a visible marker unique to that surface (a heading, an id, a
`data-testid`, a rendered value that could only appear there), never just "I navigated from the entry point and
assumed I landed on it." **A "no defects found" report without that confirmation is treated as `unverified`, the
same as a completion claim with no `Verify:` line** — not scored as a pass, and not distinguishable from "never
looked."

**A review subagent's coverage verdict ("all X run", "every Y covered") is checked against live run status** (the scheduler's or CI's actual records), not against the agent's reading of the code. An unsupported "all run" verdict hid units that never ran.

## A fan-out review is not complete until every worker has joined — a partial aggregate can drop the tail's top-severity finding

The relay section below governs the *provenance* of each number a lane reports; this governs whether the **set**
of reports is complete before any of it is presented. An orchestrator that fans a review (or any decomposed
analysis) out to N parallel workers and hands its aggregate back the moment a **quorum** returns — two of three
forks in, the third still running — is presenting an incomplete set as final. The failure is worse than "one
finding missing," because findings are **severity-ranked and the slowest worker is not a random omission**: a
worker runs long precisely because its slice is the hardest or deepest, which is disproportionately where the
highest-severity finding sits (**tail-severity**). Observed: a security review fanned to three forks collected
two and handed back; the third's P0 outranked everything already gathered and surfaced only through a side
channel *after* the one-shot handback had refused a second call.

- **Barrier-join before you present.** Treat the review as **open** until every worker is **accounted for** —
  each has either returned its report or been **explicitly timed-out-and-noted** (a named, bounded wait with the
  gap recorded, never a silent drop). The aggregate's severity ranking is **provisional** until the join closes,
  because a later arrival can reorder the top; "N of M came back" is not "reviewed."
- **An abandoned worker's slice is an `UNVERIFIED` hole, not an omission** — name it in the aggregate (the
  skip-loudly bar, `SKILL.md` principle 5), so a reader sees the set was incomplete rather than reading a
  partial pass as a clean one.
- **A one-shot handback must not be spent on a set you know is incomplete.** When the aggregation step is a
  single non-resumable hand-off — it cannot make a second call to add a late finding — size the wait so the
  barrier **closes before** the hand-off fires; that constraint is what makes the barrier load-bearing rather
  than best-effort.

Distinct from `idea-critic`'s *Join before claiming reviewed* (principle 6): that governs **one** background
critic as a dependency of a claim — pending or missing stays `UNVERIFIED`. This is the
**aggregation barrier across a parallel fan-out of many workers**, plus the tail-severity reason a *quorum* is
not a join — the missing worker is the one most likely to carry the worst finding. Distinct from
*confirm a subagent is idle before dispatching a duplicate* (above), which reads a false-positive "completed" to
avoid a wasteful **dispatch**; here a complete-looking set drives a premature **presentation**. And distinct
from *relaying a subagent's measured findings* (below), which verifies or attributes each relayed number —
**completeness of the set precedes provenance of its members**: join first, then relay.

**🚩 tell:** an orchestrator presenting a fan-out review as complete, or stating "the top finding is X," with one
fanned worker still running or silently dropped rather than returned-or-explicitly-timed-out.

## Relaying a subagent's measured findings to a human: verify the cheap load-bearing facts, attribute the expensive ones — never restate them in your own voice

The sections above govern what a lane *did* and *didn't* do; this governs what the orchestrator does with a
lane's report when it **relays it onward to a human decision-maker**. A delegated lane's measured claims — a
merge-conflict count, "the audit gate is N findings across three shards, not the M the thread assumes," "shard 3
hit the CI timeout, not a test failure," "these three issues are already closed" — are **model output**,
carrying no more authority than any un-reviewed measurement. Relaying them verbatim in the orchestrator's own
authoritative voice **launders an unverified number into a human decision**: the orchestrator becomes the stated
source of numbers it never checked, and the human acts on them as if they were.

Split every load-bearing claim in the handback by **verification cost** and by **whether a human acts on it**:

- **Cheap to check *and* a human will act on it → spot-check it yourself before amplifying.** A "drop/close
  these items" claim earns a check because a human acts by closing or ignoring them; verify it directly (the
  issue state; the PR's current head SHA and mergeable status) so amplifying is safe. A "the analysis still
  holds — the PR hasn't moved" premise is the same: confirm the head SHA before passing it on.
- **Expensive to re-measure → attribute it to the lane *with its evidence trail*.** Present the full-conflict
  count and the multi-shard breakdown as **the lane's** measurement, carrying the run ID, the job IDs, and the
  head/merge-base SHAs, so the human can chase it — never folded into the orchestrator's own "I found N
  conflicts."

**Prioritize the spot-check by the human action it triggers, not by how surprising the number is:** a "drop
these" claim gets verified because a human acts on it; a large-but-inert number is attributed. Net: every fact
reaching the human is either orchestrator-verified or lane-attributed-with-receipts, and none is a laundered
guess.

This is the multi-agent case of the over-claim / **name-the-evidence-surface** discipline and the
**downgrade-a-caveated-status** rule (both in `deep-code-review`): the measurement was made by *another agent*,
and the relay step is exactly where the "it's the lane's number, not mine" caveat gets silently dropped.
Distinct from **a delegated "verify green" is a lead** (above): that is the orchestrator trusting a lane's
*pass/fail verdict* for a merge/land decision, resolved by re-running the authoritative gate; here the artifact
is a *measured number* relayed to a *human*, and you often cannot cheaply re-run a conflict count — hence
verify-or-attribute, not re-run. Distinct from **a completion claim carries a `Verify:` line** (above): that
obliges the *lane's own* artifact to state its method; this obliges the *orchestrator* to verify-or-attribute
when passing the lane's claims up. And unrelated to the classifier-permission asymmetry (above; and the peer
case in `multi-session-coordination.md`), which is about who may *act*, not the provenance of a measurement.

**🚩 tell:** an orchestrator status to the owner that states a subagent's measured count ("N conflicts," "M
findings across three shards") in the first person, with no attribution and no evidence trail, and no spot-check
of the cheap claims the human is about to act on.

## A prohibition in a delegate's brief is a soft control — verify the refrained action against the effect surface, and expect drift on idle or long runs

The mirror of the two sections above: they verify what a lane *did* (a delegated green verdict, a "tested"
claim); this verifies what a lane was told **not** to do. A build-only or read-only worker instructed "do not
push," "do not open a PR," "do not bump `VERSION`/`CHANGELOG`/`SHA256SUMS`," or "return a report, change
nothing" has been handed an instruction, not a locked door. The line constrains the worker's *intent*, not its
*capability*, so on some fraction of runs the forbidden action happens anyway: a misread scope, a
broadly-trained reflex ("consult the reviewer / just fix it before finishing") outweighing one line of prompt,
an idle stretch where a blocked worker reaches for something to do, or a retry that takes the long way. Keep the
prohibition — it measurably lowers the rate — but **it does not drive the rate to zero**, so it is not a
completion check. The protocol-vs-host-enforced grading and the hard-control fix are in `host-enforcement.md`,
and are worth it where the misuse is costly or irreversible.

Neither is the worker's own "no changes made / read-only as instructed" line proof — that is a self-report, and
a clean self-report is not evidence (the `Verify:`-line rule above is the positive-claim form; this is its
negative-constraint twin). Confirm compliance from **what the lane actually did**.

The catch that makes this its own discipline: a refrained-action claim has an
**unbounded verification surface**. A positive "verify green" claim has one authoritative source — re-run the
gate. "It did nothing forbidden" has none; it is a **union of effect surfaces**, and a clean check of one clears
none of the others. `git status`/`git diff` in the worktree proves only that no *tracked file there* changed —
nothing about a branch or tag pushed to the remote, a PR opened, an issue filed, a comment or message sent, or a
paid tool called (the context-inheriting-fork section below makes the same point for the narrow-brief
fork). So enumerate the surfaces the brief actually named and check each: the **per-agent tool-call record**
where the harness exposes one; **remote refs** (`git ls-remote`) for a pushed branch or tag; **open PRs**; and
the **diff scope** — did `VERSION`/`CHANGELOG`/`SHA256SUMS` move when the brief said "build only, stamps later"?
The honest verdict is *"no forbidden effect on surfaces A, B, C,"* never a bare *"complied"*; a surface you did
not or could not inspect stays `UNVERIFIED`.

**Where the drift clusters.** It is not uniform across the run — it concentrates at **idle moments** (a worker
blocked on CI or a slow step, filling the gap) and on **long runs** (more turns, more chances for a reflex to
fire). Two consequences: give a waiting worker an explicit *"while blocked, do nothing / end the turn"* line,
since that is where the reach happens; and weight the post-hoc effect-surface check toward long and idle-heavy
lanes, re-checking on resume after an idle gap. This is a different use of "idle" from
*confirm a subagent is idle before dispatching a duplicate* above — there idleness is a
**precondition to check before acting**; here it is a **predictor of when a delegate drifts past its brief**.

## A context-inheriting fork is not a blank slate — a narrow brief does not erase the inherited wider one

Moved from `SKILL.md` **Worktrees and occupancy**; "the tree-sharing risk above" in the rule below is that section's first bullet (a subagent or fork is not automatically a separate worktree).

- **A context-inheriting fork is not a blank slate — a narrow instruction to
  it is ambiguous by construction.** Distinct from the tree-sharing risk
  above: a fork hands a subagent every prior instruction, not only the newest.
  A lane earlier told "file an issue for anything you find" and later forked
  with "return a table, create or change nothing" inherits both — the narrower
  ask does not erase the wider one still in its context, and it can act on the
  old brief. Two mitigations, both required for narrow or research-only work:
  prefer a **fresh, non-forked** unit (no inherited brief to fall back on);
  when a fork genuinely needs the parent's context, state the prohibition
  explicitly *and* verify compliance from what the lane actually called, not
  its own summary — `git status`/`git diff` proves no tracked file changed and
  proves nothing about an issue filed, a comment posted, or a message sent
  (`parallel-audit.md` §2 covers the read-only fan-out case; this is the
  general-lane case).


A hand-back pastes the test runner's exact count string (for example `Tests: 219/219`), not a paraphrase of it.

## Done means verified

Merged + tests green + deploy ready is a proxy, not delivery: buttons did nothing, comments landed on the wrong
page, a header clipped, and an integration returned 4xx for days while every handback said "live".

- **Journey receipt (UI).** A user-facing UI change is DONE only when QA ran, on the page where the request
  originated, control clicked → effect persisted → page reloaded → persistence asserted, and the receipt holds
  `journey: <page> <steps> PASS`. `lane_guard.py handback --receipt FILE` refuses a diff touching UI files
  (tsx/jsx/vue/svelte/html/css/scss/...) when the line is absent or says anything but PASS.
- **Post-deploy log check.** After every deploy, read runtime logs for the first ~5 minutes for errors and
  integration 4xx; record `postdeploy-logs: clean | <errors>`. No record = "deployed, unverified", never "live".
  `lane_guard.py handback --deployed --receipt FILE` refuses a missing line or any value but `clean`.
- **Say the state you have.** merged, deployed and verified-on-<page> are different words (`communication-structure`).
- **Secrets and env.** Before asking the owner for a secret, check what the platform and its config already store.
  A required-env list names only variables that already have values; an empty required field blocks deploy forms.
- **QA on a fresh database per branch.** Run QA against a database built from that branch's migrations, never a
  shared or long-lived one: a stale or other-branch schema passes a branch whose migration is broken, or fails one
  that is fine. Record the DB identity in the receipt.
