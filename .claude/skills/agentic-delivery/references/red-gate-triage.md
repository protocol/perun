# Fast agentic delivery — red-gate triage

Read this when: a gate, union, or CI check is red and you must decide whether it is real: attributing a red union (check the bare base first), a load-flaky or contention-red check, a fleet-wide external finding, an absent (uncomputable) check, or propagating a landed flaky-test fix to queued branches.
Part of the `fast-agentic-delivery.md` ledger (index and sources there); an "above"/"below" pointer to a missing section is in `merge-queue-worktrees.md` or `worktree-isolation.md`.

---

## A third gate-epistemology case: a correct, external, fleet-wide finding

Principle 3 separates *the check could not run* (`UNVERIFIED` — never a pass, and a *required* missing check
still blocks its gated action) from *a real defect the diff introduced* (fail closed). A newly-published,
correctly-detected dependency-vulnerability advisory is neither: the gate is right, the finding is real, and it
is shared across every open change **and the mainline itself**, with no relationship to any one diff. One
observed instance: a real advisory reddened the mainline and every open PR in a queue at once with zero code
change from any of them; the fix that actually unblocked the fleet was
**one coordinated dependency-lockfile bump**, landed as a fix-forward, after which the rest of the queue needed
to resync against the new mainline rather than each independently rediscover the same fix. Name this case
explicitly — it saves the diagnosis time of treating a fleet-wide, external-cause red as N unrelated
regressions. It is a **diagnosis shortcut, not a new merge authority**: it does not license merging onto a red
mainline beyond whatever narrow, human-approved change-control path a project already has for exactly this case
(one reviewed, unblocking fix).

Before merging while another machine's union is in flight, run `scripts/union_overlap.py --base origin/main --mine <PRs> --other <PRs|ref>`: exit 1 lists shared files (serialize), exit 2 `COULD_NOT_CHECK` is not a pass.

## A red union is not automatically the first PR's fault: attribute it, and check the bare base first

Three train-failure shapes look like a PR failure and are not. **(1) Culprit attribution:** when a union fails a
ratchet (a file-length or count limit), dropping the first PR drops the wrong one when a later PR's diff is what
exceeds the limit; measure each PR merged **alone onto the current base** and drop the one that fails. **(2) Stale-base
measurement:** a PR can be under a line limit on its own stale base and over it once the current base is merged in,
so measure ratchets only after merging the current base. **(3) Red base:** a new advisory or a broken base fails the
audit gate in every train; run the audit on the bare base first and report `BASE RED` instead of blaming a PR.
`scripts/train_land.sh` implements (1) and (3) behind optional `RATCHET_CMD` and `BASE_AUDIT_CMD` (tested in
`scripts/test-train-scripts.sh`); (2) is the same measurement taken on the merged result.

**Before a flaky-test fix, list the open PRs that touch that test file** (`gh pr list --state open --json number,headRefName,files`) and add the fix to the holder's PR rather than opening a second one; the pre-push hook runs `flake_holder.py`, which warns naming the holder (warn, never refuse).

**Never store a poisoned baseline.** Store a baseline only through `python3 .claude/skills/agentic-delivery/scripts/baseline_guard.py --fails F --rerun 'CMD {id}' --out B.json --normal N`: it re-runs each failure solo (a solo pass is load, dropped), records the 1-minute load at start, and refuses a run with far more failures than normal. **A quarantine entry needs a ticket and an expiry** (`flake_ledger.py quarantine --ticket T`); a full list (`--max`, default 10) exits 1 and `--file-issue` files a P0, it is not a note for a human. **A freeze is a file, not a message**: see `references/flow-guards.md` (Freeze).

**Load flakes must not sink a train.** A train that is all-or-nothing under load can merge nothing for hours: failures that
looked new all passed when re-run alone. With `RERUN_CMD` (and optionally `BASELINE_FAILS`), `train_land.sh` re-runs each
new `FAIL <id>` from the browser gate alone up to 3 times (`train_flake.sh`); an id is real only when it fails all 3,
a flake lands only if it also fails once in 3 solo base runs (else `CANT`, exit 3: it may be an intermittent regression), and
only PRs that fail the real ids merged alone onto the base are
dropped before the rest re-verify and land. While the gate runs it holds the exclusive machine-wide heavy lease
(`perun_policy.py heavy-exclusive`), so `heavy_gate.py` denies other heavy commands with "gate running: wait" and lanes stop
adding load; pushes go through one serial queue (`train-push.lock`). The lease is valid while its pid is alive and its mtime is
fresh; the train renews it at each step. Waits use the `_lock.sh` mkdir lock, never a process-name match; a lock that looks
stale is reported with the command to clear it by hand and is never moved or deleted automatically. A red browser run lands
only when every new listed failure re-ran as a flake and the runner's own `FAILURES <n>` count is not above the listed `FAIL`
lines. **CANT rule:** the per-PR bisect re-runs each real id through the same flake triage (never one run), blames a PR only
when it fails the id alone, and a failure that passes alone for every PR (`FLAKY`, no blame) or is not pinned to a culprit makes the train print `CANT` and exit 3 with nothing landed. Tests: `scripts/test-train-resilience.sh`, `test-peer-pains-2.sh`, `test-train-flake-base.sh`.

**Rerun and batch rules.** Re-run a failing title solo with one worker, never with the suite's parallelism; 2 of 2 solo passes is a flake. Before any bisect, run the same title on the base at the same load (a paired base run) so load is not blamed on the PR. Size the batch with an AIMD window rather than a fixed cap: start at 4, add 1 after each green train, halve after a red one. Test: `scripts/test-train-flake-cleanup.sh`.

**Split on an unattributed red (`TRAIN_SPLIT_DEPTH`, default 2; `0` restores plain CANT).** At roughly 5 merges an hour, one red train that names no culprit used to land nothing and stall the whole queue. Now, when the per-PR bisect finds no culprit (`no culprit pinned` or `real failure(s) not pinned`, after any pinned culprits are dropped) and at least 2 PRs remain, `train_land.sh` splits them into two halves. Each half re-runs the full gate (verify plus browser, with the same flake and base-red triage) stacked on the fresh base and lands only when its own gate is green, so unverified code never lands. The left half lands first and the right half is gated on the base that now holds it, after redoing the push-lock and lease waits; a half whose base moved before it landed is a CANT leaf. A red half splits again until the depth is spent; a leaf (a single PR, or the depth floor) keeps the old CANT and FLAKY meaning and lands nothing: it prints `CANT leaf #...`. Only a CANT leaf continues the split; an infra or policy failure (exit 2, 4, or 126 and up) stops it. The run always ends with `SPLIT done: landed #...; CANT (not landed) #...; gates=<n>`, where landed is what `land_train.sh` actually merged and every other PR (dropped culprits included) is not landed. It exits 0 only when everything landed, otherwise 3 (or the abort code). The flake-on-base CANT (`flake ... never fails on the base`) never splits, because re-running a possible intermittent regression in halves would only re-roll the dice. A split does add independent rolls of the same full gate, but only for a failure that already re-failed every solo re-run at the union (REAL), and each half still lands only on its own green gate. Cost: one full gate per half, so a split that cannot find a green half costs at most `2^depth` extra gates. Test: `scripts/test-train-split.sh`.

## A load-flaky required gate is not a confirmed red — bounded-rerun the same commit to reclassify it before concluding a regression

This expands `gate-epistemology.md` principle 3 ("if the shape matches a known-flaky
browser/probe/hydration check, rerun and recheck **before** reverting") to the verdict an
**autonomous merge-drainer** draws from a required check's pass/fail bit after each merge. Principle 3 carries
the discriminator — identify the failing job **and step**, match it against a known-flaky signature, revert only
once the failure **reproduces** and is causally tied to the change — and the rerun **mechanics** live in
`merge-operations.md`: diagnose a slow/stuck shard by its log, **rerun at most once, only after**
diagnosis, no *rerun-storm*, and retry only an indeterminate result (an `UNKNOWN`), never a **definite**
failure, as if it were transient. Neither is restated here. What the drainer case adds is the **verdict layer**:
a first red is not a regression conclusion, the premature *halt* is as costly as the premature *revert*, and an
auto-rerun that keeps working is itself a tracked defect.

The trap is specific: a required gate that shells out to an external probe under a tight timeout is
deterministic in isolation but **load-sensitive** under merge volume, so a busy runner reddens the trunk with no
code change from any diff. From the bit alone the drainer cannot separate this **load-flake** from a real
regression, and both naive reactions are wrong — **halt** the whole queue (throughput collapses and an innocent
PR is blamed, sometimes auto-reverted) or **force through** (a genuinely broken trunk is hidden for the next
contributor). Principle 3 governs the premature *revert*; the premature *halt* is the other face of the same
misread and is just as costly.

- **A first non-green is a candidate to reclassify, not a verdict.** If its shape is on the known-flaky list,
  rerun the gate on the **identical commit** — never a silent rebase, which changes what is tested and can
  launder a real failure into a "pass" — within the bounded rerun budget §5's slow-shard-diagnosis rule sets
  (para 1). Green on rerun confirms the flake; proceed. This is how a first red *becomes* a **confirmed** red:
  only after the bounded reruns still fail is the trunk a confirmed-failing base, at which point the
  **red-base discharge floor** applies (a confirmed red is a real deadlock needing a proven union to discharge —
  the floor above, and `merge-operations.md`) and a revert is warranted — name the candidate commits.
  The first red is never itself the confirmed red.
- **Only a known-flaky shape is a rerun candidate; everything else is real immediately.** A shape *not* on the
  list — a real assertion, a type error, a lint — is deterministic and reproduces, so it is a real regression on
  the **first** red; never rerun it blind. This is §5's
  *retry only an `UNKNOWN`, never a definite `CONFLICTING`* rule read at the required-check layer (and the
  lane-level twin, `fanout-host-sizing.md` **a sizing bug, the spawn gate omitted disk**). The cap does double duty in
  the drainer: past it the verdict **flips** to suspected regression — it does not merely stop the retrying.
- **The auto-rerun is a stopgap, not the fix — track it as a defect.** File the flaky gate for a **durable fix**
  (make the probe fail-open on a can't-check, widen the timeout, or de-parallelize it) and watch the
  **fraction of reruns that go green**: a rising ratio means the flaky-signature list is outgrowing the fixes
  and the drainer is leaning on a crutch, each entry a gate that still needs its own repair.

Distinct from **"bound every flaky finalize step"** (below): there the bound's expiry falls back to a text
`Verify:` report and the change still lands; here the bound's expiry **flips the verdict on the code** — flake
to suspected real regression — and gates the halt/revert decision itself. Distinct too from the
**fleet-wide external advisory** (above): that is a *real* finding shared by every open change, fixed by one
coordinated bump; a load-flake is **not a real finding at all**, and the remedy is a rerun, not a fix-forward.

**🚩** a drainer that concludes "regression" — halts the queue or auto-reverts the last merge — on the **first**
non-green of a load-/infra-shaped required check without a bounded same-commit rerun; or one that reruns a
**deterministic** assertion failure instead of treating it as real; or a rising rerun-went-green ratio nobody is
converting into durable gate fixes.

## A local pre-push gate reddened by machine contention is not a regression — re-run the failing check in isolation before concluding one

The load-flaky-required-gate rule above is the CI/merge-drainer sibling of this one: it reads a
*required check's* pass/fail bit and reruns the **identical commit** to reclassify a first red. The same
discipline governs the **local build/test/lint gate** several lanes — or peer sessions
(`multi-session-coordination.md`) — run before push on **one shared machine**, with one constraint the CI
wording leaves open: the rerun must also be **isolated**, because the contention that reddened the gate is
*on that box*, so a same-commit rerun taken while the other heavy lanes still run reproduces the contention, not
the code. The canonical rule — a failure appearing only under fan-out concurrency is contention, not a defect,
until reproduced at low concurrency, and its "re-run the specific failing check in isolation" step — is
`parallel-audit.md` §0 (in the `deep-code-review` sibling) and is **not restated here**; this applies it to the
delivery gate's own verdict.

- **A first red under aggregate load is a candidate to reclassify, not a regression conclusion — and bypassing the gate is not the alternative.**
  Several full local gates at once can exhaust the shared box's CPU / RAM / file descriptors, so a
  headless-browser render times out, a latency/timing assertion trips, or a suite flakes — indistinguishable,
  from inside one lane, from a real regression the diff introduced. Concluding "regression" burns a fix cycle
  chasing a non-bug; `--no-verify`-ing past the red defeats the gate. Do neither on the first red.
- **The disambiguator is a rerun *in isolation*, not merely on the same commit.** Quiesce the box first — pause
  or kill the other heavy lanes, shedding the test runner's own browsers but not the app's dev server
  (`merge-queue-worktrees.md` *CI-offload the heavy gate*) — then re-run the **specific failing check** on the identical commit. A
  pass on the quiesced box proves the red was contention; only a failure that
  **still reproduces at low concurrency** is a candidate regression and enters the fix queue. A same-commit
  rerun taken *without* quiescing is not a valid disambiguation: under sustained contention it keeps failing and
  wrongly flips the verdict to "regression" — the exact wasted cycle the load-flaky rule's bounded rerun assumes
  it has already ruled out.
- **Prevent the misread by sizing, not only by diagnosing it after.** Throttle heavy gate lanes by *measured*
  load (free RAM + the swap trend, `fanout-host-sizing.md` *Gate on free RAM and the swap trend*; the peer-aggregate form is
  `multi-session-coordination.md`'s shared heavy-lane reservation), and run locally only the gate CI actually
  enforces (`merge-queue-worktrees.md` *CI-offload the heavy gate*) — so fewer contention-flakes reach the verdict step at all.
- **A rebase or merge-conflict resolution is unverified code, not a confirmed pass.** `git rebase --continue`
  never re-invokes `pre-commit` on the replayed commits, so re-run the lint+unit tier explicitly right after
  conflict resolution and before `git push`; `templates/pre-push-verify.sh` (`deep-code-review`) can enforce this
  mechanically (and refuses every push while `<git-common-dir>/DCR_HOLD` exists — an operator freeze), but a hook is self-report, not the control — `branch-and-merge-hygiene.md`'s "Self-report ≠
  control" is the trusted-evidence rule (not restated here).
- **After fixing a hit from a gate that scans the index, stage the fixed file again.** A pre-commit gate reads
  the staged content, not the working tree, so an unstaged fix leaves the old hit in place and the same
  failure repeats. Re-add the file, then rerun the gate.

Distinct from *Gate on free RAM and the swap trend* and `merge-queue-worktrees.md` *CI-offload the heavy gate* (#935): those decide
**whether and how heavily** to run the local gate (sizing) — prevention; this decides
**how to read a red the gate already produced** — interpretation. Distinct from the load-flaky-required-gate
rule above: that is the CI required-check verdict with a same-commit rerun; here the shared-machine gate's rerun
must *also* be **isolated**. **🚩 tell:** a lane opening a fix or reverting on the **first** red of a heavy local
gate — or bypassing the gate — while other heavy lanes are live on the same box, with no isolated re-run of the
failing check to separate contention from a defect.

## A landed flaky-test fix only protects a branch that already has it — rebase every queued branch onto it, don't wait for each to re-discover the failure

A pre-push (or pre-commit) hook tests the tree being **pushed**, not the tree
on the base branch, so fixing a flaky test on the base does nothing for a
branch that was cut before the fix landed: it keeps re-running the old, still-
flaky test on every push until that branch is rebased onto (or merged with)
the commit that carries the fix. In parallel delivery many branches are cut
before any given fix lands and stay open for hours, so left implicit each one
either burns time re-diagnosing a failure that already has a known fix, or an
agent works around it locally — skipping the test, bypassing the hook — in a
way that quietly weakens the gate instead of fixing the actual staleness.

- **Land the fix, then find every open PR head that doesn't have it yet —
  propagate it, don't wait for each branch to discover it.** Once the fix
  lands at `<sha>`, list open-PR heads
  (`gh pr list --state open --json headRefName`) — never a raw ref sweep,
  which also returns `origin/HEAD` and merged or abandoned branches — keep
  each where `git merge-base --is-ancestor <sha> origin/<head>` exits
  non-zero, and tell its **owning lane** to rebase before its next push;
  rebase it yourself only when no one is writing to that branch. This runs on
  the **landing** of the fix, not on the next flake report, and it is Ops /
  Merge-Guard plumbing (`roles.md`) — not a Conductor-level decision.
- **A branch that cannot rebase right now scope-skips that one test, never
  disables it.** A documented, temporary deselect of the specific test for
  local pushes only, with a pointer comment to `<sha>`, while CI keeps running
  it; the fix commit itself never disables or skips the test, and the hook is
  never silently bypassed (`--no-verify`).
- **Track the queued-branch list so the fix actually reaches them.** A fix
  landed on the base and never checked against the open-branch list is the
  same silent-drop failure the *feedback-coverage map* (`roles.md`) exists to
  catch on the product side — the branch list isn't closed until each entry is
  rebased or explicitly scope-skipped with its `<sha>` pointer, not merely
  landed and left to chance.

**🚩 tell:** a branch pushed after a known flaky-test fix landed still fails on
that exact test, or a skip/deselect for that test sits in a diff with no
commit pointer, in place of a rebase.

Distinct from *A load-flaky required gate is not a confirmed red* (above):
that section is about diagnosing and reclassifying a flaky test the **first**
time a drainer sees it; this is about **propagating a fix that already
exists** to every branch that has not received it yet. Distinct from *A
rebase or merge-conflict resolution is unverified code, not a confirmed pass*
(above): that says re-run the lint/unit tier after a rebase's conflict
resolution; this says rebase in the first place, specifically to pick up a
landed fix, before the branch's next push.

## Absent checks are a third state, not a slow "pending" — an uncomputable merge ref suppresses the run; bounded-wait then re-trigger, never wait forever

The `merge-queue-worktrees.md` *not-red* section and this one are how an autonomous drainer reads a check-state bit at two of the places it reads one:
the *not-red* section sets the **base-admission threshold** (a base run still in flight is admissible — pending
is not a hold), and the *load-flaky* section sets the **red-verdict rule** (a first red is a candidate to
reclassify, not a regression conclusion). This is the third place — a **member PR's own** readiness — and its
rule is that **absent ≠ slow**: a PR reporting *zero* checks (none at all — not one in flight, not one red) is
not a check that is merely early, and a drainer that treats it as one waits forever.

The mechanism is that CI runs against a **computed merge ref** (the PR merged into its base), not the raw head.
When the PR is non-mergeable — `mergeable_state=dirty`: a real conflict, or its base advanced past what it last
merged — the forge **cannot compute that ref, so it never dispatches CI for the head at all** (a runner-queue
backlog can suppress the dispatch the same way, transiently). The PR then shows **no checks**, which is fatally
easy to misread: a human or drainer sees "no failures" and reads it as *still pending*, or even *clean*, when in
fact the run never started and never will for that SHA without intervention. A drainer whose rule is "poll until
the checks appear and go green" then polls a PR whose checks will never appear — the same starvation as the
`merge-queue-worktrees.md` blocked-head case, but from a head that was never *checked* rather than one checked and *refused*.

- **Read `mergeable` / `mergeable_state` alongside the check list — it is the discriminator.** Zero checks +
  non-mergeable (`dirty` / `CONFLICTING`) = **stalled**: the run was suppressed and needs a re-fire. Zero checks
  + `MERGEABLE` = **genuinely just-triggered**: a bounded wait is correct. The two act on
  **different fields, and neither is wait-forever**: poll the *mergeability* field until it settles (the brief
  `UNKNOWN`-while-recomputing state `merge-operations.md` bounds to 2–4 tries), then apply
  bounded-wait-then-re-fire to the *check list*. The check list alone cannot split stalled from fresh; the
  mergeability field is what does.
- **A non-draft PR with zero check suites: inspect the head commit message first.** A bracketed CI-skip token anywhere in
  it (body included; a bare mention counts), or a final `skip-checks: true` trailer, makes GitHub skip every workflow for that
  head, and a green-checks gate refuses the PR forever. Waiting and re-running cannot help; push one new commit with a clean
  message. `surface_check.py checks` names the token as the likely cause (a ref with no CI or path filters also leave zero checks).
- **Recover by re-triggering, not waiting.** A fresh fetch + merge-of-base + push (or a rebase) recomputes the
  merge ref; if the re-merge is conflict-free, `mergeable` flips and CI fires within seconds — the rebase /
  re-run-CI mechanics are `merge-operations.md`'s, not restated here. A true `dirty` from a real
  conflict needs that conflict resolved first; either way the move is an **action**, never more polling.
- **Time-box zero-checks, and never read it as a verdict.** Past a short dispatch-delay threshold **and** while
  non-mergeable → escalate to a re-merge; do not keep polling. Never interpret zero-checks as an implicit
  **pass** (the run never ran) or as a stable **pending** (it will never resolve on its own). Track PRs sitting
  at zero checks while non-mergeable past a normal dispatch delay — a nonzero count is work stalling invisibly
  on uncomputable merge refs.

Distinct from the **config-unsatisfiable required check** (`merge-operations.md`'s
*a required check must be satisfiable* rule, the #262 *no-status* case): there a required check **name** never
gets a job to report because the workflow is wired wrong (a path filter, a trigger-event gap, a missing
`on.pull_request.branches` base entry), and the fix is **config-side** and permanent — a pass-through job or a
corrected `on:` block. Here the workflow is correctly wired; a re-merge makes the *same* job fire. Same surface
symptom (no status looks like pending), opposite remedy — a config fix vs a re-trigger. Distinct too from the
**serial-drainer spins on a blocked head** rule (`merge-queue-worktrees.md`): there the head is green + mergeable but refused by a
*stricter final gate*, so the drain **advances past** it; here the head was never checked at all, so the drain
**re-fires** it — advance-past abandons a genuinely-blocked item, re-fire rescues a never-started one.

**🚩** an orchestrator turn history that is a run of near-identical "still waiting for CI" ticks on a PR that
shows **no checks at all** and is non-mergeable — the *emit-on-transition-only* tell (below) applied to a state
that will **never** transition without a re-merge; the loop is not waiting, it is stuck, and the run it is
waiting for was never dispatched.

**Cheap gates first.** Run `python3 scripts/preflight.py gates.json` before a long commit or push hook cycle: it runs every `cheap` gate without stopping at the first failure, prints all failures together, runs expensive gates only if the cheap ones pass (or `--all`), and a gate that cannot start is `COULD_NOT_RUN`, never a pass. Timeouts kill only the direct child, not its process group.

## Green main has one owner, and a red with no owner within an hour is an alarm

Reserve one slot (a lane or a named person) as the owner of red main; while main is red its only job is the red. Every red test gets a fix PR or a named owner within one hour of going red; a red nobody has claimed is the failure, not the red itself. `scripts/red_main.py` reads the list of reds (`.claude/red-main.json`: `id`, `since`, optional `owner`/`fix`) and prints `reds=N uncovered=U oldest_h=H`, where uncovered means no owner and no fix past the 1h grace. It exits 1 at policy `red_uncovered_max` uncovered reds or when the oldest red reaches `red_oldest_h` hours (both default 0 = off), and 2 on unreadable input. The landing watchdog runs it each tick when a threshold is set and `.claude/red-main.json` exists, so the alarm needs no one to remember to ask; with a threshold set, a missing or unreadable list is itself an alarm (green unknown), never silent green.

## A test that passes alone and fails in every full parallel run is neither a flake nor a red: move it to the serial project the same day

Intermittent failures are flakes and consistent failures on one tree are real reds. A third case: the test passes every time it runs alone but fails in every full parallel run. It shares a resource (a port, a file, global state, a CPU-timing assumption) with its neighbours, so re-running it solo proves nothing and quarantining it hides a real isolation bug. Rule: move it the same day to the serial (one-at-a-time) test project, and treat any failure there as a real bug, not a flake. `flake_ledger.py serial [--n N]` lists the candidates from the existing ledger (`SERIAL-CANDIDATE id`: failed in the suite and passed solo on at least N distinct trees, never failed solo on any tree); it exits 1 when any exist. `flake_ledger.py serial-move ID...` records the move (`serial-project.txt`): the id leaves the candidate list, is never quarantined, and `check` reports a failure there as `BLOCKING` (a real bug, no flake excuse). The ledger only records membership; the repo's own test runner config runs the serial project one test at a time.

## Admission must run every test class that can refuse the batch, and the spec-selection map needs an owner and an age alarm

If per-PR admission runs only typecheck and unit tests, a browser/e2e spec that fails in the batch refuses every PR in it, and the author learns it late. Admission runs every class the batch runs, with the browser/e2e specs scoped to those the change affects. The path-to-spec map that does the scoping rots silently: a stale map under-selects, and the gap only shows when the batch goes red. It therefore has a named refresh owner and a maximum age. `scripts/admission_check.py` reads `.claude/admission.json` (`batch_classes`, `admission_classes`, `map_owner`, `map_refreshed`, `map_max_age_h`), prints `MISSING class` for each batch class admission omits, `MAP-NO-OWNER` and `MAP-STALE` rows, and exits 1 on any; a missing or malformed file, a blank owner or a future refresh date exits 2, because an absent config is not a pass. `train_land.sh` runs it (and `host_accept.py`) whenever the base branch carries the config, reading batch_classes from the base so a PR cannot drop a class by editing its own file, and refuses the train (exit 2) on any non-zero.
