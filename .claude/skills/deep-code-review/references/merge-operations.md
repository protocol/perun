# Merge operations — landing PRs and merge-gate mechanics

Read this when landing or sequencing PRs, before recommending or executing any branch-triage row (delete, close, conflict resolution, subset absorb, automated or irreversible step), or when a merge gate or required check is stuck, stale, red, or in question. Split from `branch-and-merge-hygiene.md`; its triage, decision tree, and safety rails apply first, and every § number below refers to that file.

### Merge trains — landing several ready PRs without a platform merge queue

When several independently-green PRs are ready at once and no merge queue is available, merging one at a time
and waiting for the base's CI between each serializes for no benefit — the base was already known-green before
each subsequent PR's own checks ran. A **merge train** verifies the *combination* once instead:

1. Build a **throwaway integration branch** off the target with every candidate PR's head merged in. Resolve
   any collision **keep-both**, never dropping one side — a generated/compiled-file collision follows §6's
   regenerate-don't-hand-splice rule.
2. **Run cheap, union-only checks first** — a file-size/count ratchet, a lint pass, anything that needs no build
   — before the full aggregate gate. A union-only failure (two PRs each grow the same file within its own
   allowance, but together push it over the cap) is usually a seconds-long, no-build check; surfacing it only
   after the full parallel gate run (which can run tens of minutes) turns a fast RED naming the file into an
   expensive one. Run the full aggregate gate **second**, only once the cheap checks are clean.
3. Run the **full aggregate gate once** on that union. Green means the combined tree is sound.
4. Merge the member PRs **individually and back-to-back**, preserving each one's own commits and issue-closing
   keyword. **Never squash the union into one commit** — that orphans every member PR's own issue and review
   thread instead of closing them.
5. Discard the integration branch; it's never itself merged.

**A squash or amend that collects several lanes' work must keep each closing keyword scoped to its
own PR — a stray one silently closes someone else's.** Step 4 above already preserves each member's own
commits and its own issue-closing keyword by never squashing the union; the same discipline applies to
*any* squash or amend that consolidates multi-lane work into one commit (a merge-train squash fallback, a
maintainer's "clean up the history" squash, an agent amending a commit message) — a keyword copy-pasted or
left over from a different lane's message closes an issue or PR that has nothing to do with the landing
change the moment it reaches the default branch, and the close is attributed to whoever pushed, so it reads
as intentional and nobody re-checks it (issue #1121). Strip a closing keyword the landing PR does not itself
own before the squash/amend lands. `closes_lint.py` (deep-code-review's `scripts/`) mechanizes this: given a
commit range and an allowed set of (repo, number) references (`--allow`, or `--pr-body` naming the landing PR's own
body, whose own closing keywords define the set), it fails on any `close[sd]?` / `fix(e[sd])?` /
`resolve[sd]?` + `#N` / `o/r#N` / URL reference outside that set — opt in via `DCR_CLOSES_LINT=1` in the installed
`dcr-gates.sh`. **Treat "PR closed, not merged, and its head is not an ancestor of the target branch" as an
incident, not a shrug**: check the close event's actor and source (a keyword-triggered auto-close vs. a
human decision) before assuming intent, and reopen it — the mirror, for the cross-PR case, of
`unattended-trackers.md`'s over-fire rules (a quoted mention, an umbrella issue) that don't cover a keyword
landing from a wholly unrelated commit.

**The union verifies the combination; it is not on the critical path.** Its CI aggregates every member's
checks, so it concludes no sooner than the slowest member and usually later — treating "union CI still pending
or red" as a reason to hold members already green re-serializes the very wait the train exists to remove. Once
the aggregate gate is green the proof is in hand: merge the green members (step 4) and **close the union with
a pointer to where they landed**. "Wait for union CI, then squash/merge the union" fails twice over — the wait
is redundant and merging the union orphans its members' issues (step 4).

**Sequence a gate-adding PR last within the batch.** A PR that adds a new required gate, merged first, forces
every other PR in the batch to retrofit a gate that didn't exist when it was authored — extra round-trips for
no benefit. When triaging several ready branches at once, check whether any changes required-CI/gate
configuration and put it at the back of the landing order.

**A union that fails a numeric ratchet/cap: attribute the overshoot to the member that owns it, never raise the
cap to pass.** When the aggregate gate above is a numeric ratchet/cap (a disallowed-pattern count, not a
build/test pass-fail) and the union is red on it, failing on the total alone costs whoever investigates a manual
bisect across every member. Attribute per member instead, using the same own-merge-base delta
`dev-env-ownership.md`'s *gate on the delta, not the tree total* rule already computes for a single PR: for each
member M, `delta(M) = count(M's head) − count(M's merge-base with the target)`. Print one line per member —
`#N +D marker=[present|none]` (`#N` the PR/change number, `D` the delta, `marker` whether that member's own
commit range carries an explicit `<ratchet>-raise: <path> <old>→<new> <reason>` annotation, the same
`size-budget-raise` convention this repo's own size-ratchet gate uses) — and route the fix to every member with
`D > 0` and `marker=none`; a member with `D > 0` and `marker=present` raised the count deliberately and on
record. **State the scanner's counting rule explicitly** — a match inside a comment or string counts, or only a
live occurrence does — so `count()` is reproducible across members; an implicit rule makes deltas incomparable
and the attribution untrustworthy. This is attribution, not a new admission path: it names which member to fix,
never licenses a member merging *because* it carries a marker, and is not a per-change fragment file that
pre-splits the cap to dodge a merge conflict — that remedy was rejected (`dev-env-ownership.md`'s *never raise
the ceiling to pass*). The union still owes the same gate everything else does: pass the ratchet/cap, or don't
merge.

**Isolating a culprit member: hold the others out for the suspect's full verification cycle, or bisect.**
When the failure needs an actual isolation run (a flaky interaction, a build-only break the ratchet can't
compute per-member), the parking must **survive past that one retry**: park for at least two cycles (one to
run the suspect alone, one to hold the rest out while that result is read), never "eligible again on the next
tick", which rebuilds the same failing union forever and reads as flaky instead of attributable (issue #1119).
A suspect that fails alone is parked **for real** until its head changes; one that passes clears itself, and
an interaction becomes the next hypothesis. **Bisect the member set** when one at a time is too slow. After a
park, **rebuild the union at once**: a sleep per conflicting member turns N conflicts into N cycles (issue
#1134). **One fix, one PR:** when members park on conflicts because each lane carries its own copy of the same
fix, `merge_train.py dupes` names the earliest PR canonical and the rest drop their copy and rebase on it.
**Merge only onto the base the union proved.** A base that moved since verify means re-plan, never a
silent re-verify; a proved head that is no longer an ancestor of the fetched head means a rewrite, so halt for
a human, or the train restores history someone removed on purpose (issue #1137). **Compare only refs this run
fetched:** a forced refspec (`+src:dst`) into names unique per run (never a cycle counter a restart reuses),
any non-zero fetch stops the cycle, and each fetched SHA must equal `git ls-remote` and the head the plan
checked (a member that differs is skipped, not the cycle), or a reused name keeps stale content and parks
mergeable PRs as false conflicts (issue #1139). `merge_train.py`
(agentic-delivery's `scripts/`) runs this section: plan, one union verify, bisection, `#N +D marker=…`
lines, flaky retry with bounded backoff, and a dry-run merge that halts on a moved base and never pushes.
`--apply` still needs the integration owner or a recorded standing grant.

### Bisect by single-PR merge and the narrowest failing spec set — never a full train re-run per guess

When a regression surfaces in a broad suite (browser/UI specs, an end-to-end run) rather than the
numeric ratchet the ratchet-attribution paragraph above already covers, re-running the whole train per
guess costs a full cycle (tens of minutes) for one bit of information. Cheaper: merge each suspect PR
**alone** onto the proven base and run only the specific spec files the regression named — a few minutes
each, not a full re-run — before reaching for the whole-train bisect machinery. Test **pairs**, not only
singles: some failures appear only with two specific PRs merged together (an interaction neither
introduces alone), and some are load flakes from concurrent runners that pass in every isolated
configuration — a suspect that passes alone and in every pairing it's tried in is not exonerated until a
load-matched re-run is tried, or it should be treated as a flake, not a regression, and handled by the
load-flaky-gate discipline (`red-gate-triage.md`). Keep the **majority-rerun** ("fails 2 of 3")
shortcut for short regression lists — roughly 5 specs or fewer; past that, per-PR bisection is cheaper
than reading a noisy majority vote across a long list.

### A behavior change ports its own specs in the same PR — the mover updates every assertion the move breaks

A PR that intentionally relocates behavior a suite asserts against (moving a UI element to a new home,
renaming a route, changing a default) breaks every spec still written against the old location — and
those specs are usually scattered across files the author didn't touch. The PR that causes the move is
the PR that updates them: keep every assertion (don't delete the coverage to make the suite pass), and
treat "my change is right, the specs are stale" as a signal to fix the specs in the same PR, not a
finding against the suite. A merge train discovering broken specs this way after landing several PRs is
discovering a review gap, not a train defect — this belongs in review, before the member enters the
batch.

### Merge-train wrapper hygiene — admit, attribute, report and install without lying to yourself

- **Pre-gate each PR before it is admitted.** Run a fast per-PR check first: merge-conflict check against the
  current base, the count/size ratchets, the type check, and only the browser specs the diff touches (not the
  full suite). A PR with an unresolved conflict or a plain type error that enters a train poisons the union's
  result and costs a slot. Flag an admission step with no individual pre-check, and a pre-check that re-runs
  the full suite.
- **A ratchet counter counts every form of what it counts.** A style-duplication ratchet that scans only the
  class form misses the inline-attribute form (and the reverse), so a member passes its own delta check and
  still blows the limit in the union. Attribute a trip to the member by its own per-PR delta and drop that
  member before the expensive browser suite, never after it.
- **Attribute a regression only after the base alone fails to reproduce it, and compare by test title.** An
  auto-bisect that runs "base plus one PR" per PR without first running the base blames every PR for a
  timing-sensitive spec that also fails on the base, and file-level comparison blames PRs for unrelated failing
  titles in the same file. Run the base once on the regressed spec files, drop every title that fails there,
  and compare the remaining titles per PR. If every regression also fails at the base, treat the union as
  proven.
- **When merging the base into a release branch conflicts on a flaky-test file two PRs fixed differently,
  take the base's version, then run that test file.** The base's fix already landed and passed its own gate;
  re-resolving by hand invents a third variant. Keep the release branch's change only if the base has none
  for that hunk.
- **A train wrapper keeps every verdict line.** `| tail -3` hid the CONFLICT/DEFER lines above the final
  RED/GREEN, so a member vanished with no visible reason. Filter by verdict prefix
  (`^(GREEN|RED|CONFLICT|DEFER|STALE)`), never by position.
- **Chain PRs that regenerate the same generated artifact.** Two members that both rebuild one generated file
  always conflict in a union. Merge the first into the second and rebuild so the second is a descendant, and
  both land in one train in order. Any direct merge to the integration branch mid-train restarts this, so
  announce a short merge freeze while a release is being cut.
- **Install before the gate, never during it.** If the union's lockfile differs from the installed tree, do a
  clean install first. A gate step that reinstalls packages or checks out another ref in a working tree a
  running browser suite is still reading deletes modules under its workers, and the missing-module crash reads
  as a real regression. Use a fresh isolated tree per concurrent suite. Flag any gate script that can mutate
  `node_modules`/vendor dirs in a tree another live process reads.
- **A wait loop built on `pgrep -f <pattern>` can match itself** when its own command text contains the
  pattern, so it waits to its timeout. Anchor to the target's argv0 (`^bash /path/script.sh`) or track PIDs.

### Committed generated docs plus a freshness check don't survive a merge train — generate at build time or serve on demand

A doc generated from source and then committed, guarded by a test asserting it's still fresh, works for
one PR at a time; inside a train, *any other* member's backend change can make the committed doc stale
relative to the union tree even though neither PR touching the doc itself changed. The freshness test
then fails on a union no single member's own CI would have flagged. Generate the doc in the build step,
or serve it on demand instead of committing a snapshot — a train (or any batch merge) is exactly the
condition committed-plus-freshness-test doesn't survive.

### A capability-gated control needs an explicit test double, not an ambient default — a flipped gate turns specs red with no code change

A UI control gated on an environment capability (an API key present, a feature entitlement) renders
disabled whenever that capability is absent in the test environment — which a spec written against the
enabled state doesn't expect, and which flips with the environment, not with the code under test. Specs
must stub the capability explicitly (force it on for the enabled-state assertions) and carry a separate
disabled-state case, rather than relying on whatever the test environment's ambient default happens to
be; a merge train is where an environment-dependent flip is likeliest to surface, because it's the point
several members' changes and the ambient environment are evaluated together.

### Mergeable is a snapshot against a moving base head — re-check before each merge; freeze the sweep while a resolver runs

"Green + mergeable" is a **snapshot against the current base head, not a durable property**. Landing PR A can
flip an overlapping PR B from MERGEABLE back to CONFLICTING — A touched a file B also touches, so B now needs
a rebase — while **B's checks stay green** (they ran against the old base; only its mergeability changed).
This bites at two scales:

- **Snapshot-then-batch (the coordinator *reads* staleness).** A coordinator that snapshots "these five are
  green + mergeable" and merges them one by one finds PRs 2..5 increasingly CONFLICTING as earlier ones land —
  then stalls, or (worse) force-merges onto a base the PR was never tested against. **Re-check mergeability
  immediately before *each* merge, never once at the top of the batch** — mergeable has a shelf life of "until
  the next overlapping merge." **Group the batch by the file sets each PR touches: serial-with-rebase *within*
  a group, parallel only *across* disjoint groups.** Merging two PRs that share a hot file as if independent
  is the bug. (The merge-train union above surfaces these collisions up front and proves the *combination
  builds* — but doesn't make a conflicting member mergeable: the union branch is thrown away and the member
  branches are left unchanged, so each member still resolves against the moving target and the per-merge
  re-check still applies at step 4. Sequence the resolver first, *then* run the train.)

- **Sweep-while-resolving (the coordinator *causes* the staleness).** Running a **merge sweep** (landing green
  PRs into a shared base) **concurrently with** a **resolver lane** (rebasing a conflict-prone set against
  that same base) makes the sweep the very thing re-dirtying the cluster it's trying to land: every merge
  moves the base head and invalidates the resolution the resolver just computed, so the PRs it was making
  mergeable flip back to conflicting — an unbounded treadmill where the broadest, hottest-file PRs never
  converge. **Freeze the *merge* step — not the build step — while a resolver is active against the base:**
  lanes keep taking PRs to green (no stall, no visible slowdown), green PRs **queue** instead of merging, the
  **hardest-to-rebase set lands first** against a now-stable base, then the queue drains back-to-back.
  Freezing the merge rather than pausing all work removes the invalidation without dropping throughput.

**A third state — `UNKNOWN` while the forge recomputes.** Distinct from the MERGEABLE↔CONFLICTING flip above:
**GitHub** computes mergeability **asynchronously** (not independently verified for other forges), so right
after any base-changing merge an overlapping PR's `mergeable` field is briefly **`null` / `UNKNOWN`** while
the recompute runs — that's *not-yet-known*, not CONFLICTING. A batch merger that treats `UNKNOWN` as
CONFLICTING skips a PR that's actually fine (landing only the **first** of a back-to-back set); one that
treats it as MERGEABLE merges blind. **Poll until it settles** to a definite state (a bounded 2–4 tries with
short backoff), retry **only `UNKNOWN`**, and never auto-retry a definite `CONFLICTING` as if transient.

Both value-flip cases above are the **stale-base failure below at the mergeability layer** — a quantity
computed against one base head, consumed against another — except the moving head breaks *mergeability* here,
not a gate's diff. A fleet coordinator applies this whenever it batches merges; `agentic-delivery`'s
`merge-queue-worktrees.md` cross-references here rather than restating it.

**A stale CONFLICTING is a cached-view claim, not ground truth — verify locally before trusting it, and clear
it without a full re-run when nothing actually changed.** A forge can report a PR CONFLICTING against its
target branch off an **older view** of that target, even though a local merge of the exact same two commits
(PR head, target head) is clean — one observed run saw six PRs flip CONFLICTING at once right after their
shared base PR merged, with no textual conflict locally and no custom merge driver involved. The usual fix —
merge the target into the PR branch — creates a **new head commit**, so a merge-train proof already run
against the old union (Merge trains, above) no longer names that commit, tempting
either a full re-run or a trust-the-refresh shortcut. Neither is necessary: prove the refreshed head produces
the **identical tree** to the already-tested union candidate —

```
git merge-tree --write-tree <target-branch> <new-head>   # tree id the refresh would produce
git rev-parse <tested-union-commit>^{tree}                # tree id the gates already tested
```

Equal tree ids mean the refresh changed nothing the gates didn't already see — the earlier proof still holds for
**content-only** gates (tests, lint, build), no re-run needed there. A gate that reads **commit metadata** —
trailers, message lints, signer checks — still runs against the **new head**: the tree comparison says nothing
about the commit object wrapping it. Record the refreshed head's receipt as **both tree ids plus the new head
SHA**, consistent with the pin-the-verdict-to-the-exact-SHA discipline above. Different tree ids mean real
content changed and a new union must be tested. Use the same comparison to decide whether a refresh-only push
(clearing a stale flag, not resolving a real conflict) needs re-verification at all, instead of defaulting to a
full gate re-run.

### A finished check's green can be stale off a prior evaluation — confirm it ran against the current head, and know each gate's trigger model

A green that already **finished** isn't durable either — the reviewed object can change under it, so the check
you see may not have run against what you're about to **merge**. Distinct from the moving-base cases (the
mergeability-snapshot above; the stale-base gate-diff below): here the base need not move at all. Two ways a
finished green goes stale:

- **Trigger coverage — the check never re-ran.** Most gates re-evaluate only on a **subset of events**
  (typically a new push / new head). A mutation **outside** that set — **editing the body or metadata**,
  **retargeting the base**, a bot **amending the description**, or a gate reading a **cached artifact / body**
  captured at an earlier run — never fires the check, so its last verdict certifies the **pre-mutation**
  state.
- **Timing — the check will re-run but has not yet.** A mutation that **does** fire the trigger — a **rebuild
  / rebase** that pushes a new head — has a run **still in flight**, so the green you currently see belongs to
  the **pre-rebuild** head. Merging now lands an **intermediate** state the gate never certified for the final
  head: wait for the fresh run to conclude, and don't merge a change another lane is still rebuilding.

Either way the green is real; it just certifies a state that no longer exists. So before merging, **confirm
the green reflects the current head / inputs**: read the **SHA (or input digest)** the passing check actually
ran against and compare it to what you're about to merge (the pin-the-verdict-to-the-exact-SHA discipline,
`method.md`). And **know each gate's trigger model** — which events re-evaluate it and which don't — so a
mutation the triggers **don't cover**, or a run **still in flight**, reads as **invalidating**, not trusted.
These are the verdict-staleness siblings of the moving-base cases: there the *base* moved under a still-valid
check; here the *reviewed object* changed — via an event the check never saw, or one whose run hasn't
concluded. (Distinct, too, from a required check that never ran at all for this PR — the config-gap blocker
below.)

- **🚩** merging on a green produced **before** a body/metadata edit, a base retarget, or a rebuild the gate's
  triggers ignore; a "these are green" batch snapshot consumed after any such mutation; trusting a check's
  **colour** without reading the head / input digest it actually ran against.

### Red base: discharge the deadlock with a train, never an override

When the target branch itself is red, a merge preflight requiring the base green refuses the very fix PRs that
would green it — a **deadlock**, not a per-PR failure. Agents stall, invent one-off exceptions, or serial-wait
forever. The escape is the merge train above, used deliberately as the *discharge* vehicle:

1. **Discharge (preferred).** Union the individually-green fix members, run the aggregate gate once, and on
   green merge them back-to-back (the merge-train procedure above). The union's green **is** the proof the
   preflight's "base green at head between merges" wait was asking for, so it **discharges** that wait — which
   the red base can't otherwise satisfy.
2. **Serial fallback.** Wait for the base to rebuild between merges only when a true dependency stack can't
   share one union.
3. **What the union green does *not* license.** Not merging a **red** member, not an `--admin` / force-merge
   past the gate, not an undocumented "just merge anyway." A red member is still red; only the
   *base-green-between-merges* wait is discharged, since the union already proved the combined tree.
4. **Keystone exception (pre-ratified, never improvised).** When a cause no open branch introduced (a date- or
   clock-triggered test) reds the base and the fix is one PR, only merging that PR onto red can discharge it.
   With the owner away, the fleet stalls; the tempting workaround, cherry-picking the unmerged fix into every
   sibling so its gates go green, spreads unreviewed code across N diffs, goes stale if the fix changes, and
   unblocks nothing. The owner commits the exception **before** unattended runs, under the standing-grant
   authorship rule (agentic-delivery `SKILL.md` **Standing grant**), naming the fix PR or pre-ratifying one
   keystone of a shape (path globs, max files, expiry at most 30 days out; single-use): it may merge onto red
   when the base fails the check on its own, the PR touches only the fix's files, base + PR is green in a
   union run, and it merges alone, first. Siblings then **rebase** (which drops a duplicate patch), never carry a
   copy. `merge_train.py keystone` checks each condition and parks any sibling carrying a copy (#1142).
   A CI re-run reuses a PR's old merge commit, so after any fix lands, update each PR behind it instead:
   `merge_train.py refresh` by default prints local merge-and-push commands per PR (its own owner runs
   them on their next push, zero extra CI runs); `--use-update-branch` opts into printing (`--apply` runs)
   `gh pr update-branch` instead, which costs one CI run per PR — see agentic-delivery `host-enforcement.md`
   **Cost discipline: no push/CI spend to "see if it passes"**. Either way it skips keystone-copy carriers.
   It does not coordinate with a lane mid-push: run it only when no lane is pushing to the PRs it updates,
   or have lanes rebase afterward, since a lane's later force-push drops the merge commit refresh just made.

Name this the **red-base discharge** and put the vehicle used on record; an oral-only exception ("we
just merged past it that once") is itself the finding. A red base is the release pipeline's blocked state, so
`release-engineering.md` cross-links here — but the discharge *mechanism* is the merge train, so it lives here
and that file never restates it.

### A union / merge-train gate that HANGS or is BROKEN in-env (not fails) silently stalls the pipeline

A train's aggregate gate can **hang** — a wedged runner, a deadlocked build, a lost webhook — rather than
fail, and a coordinator waiting on it stops merging everything queued behind it, with no red status to react
to. **Detect it by liveness, not elapsed time alone.** During the gate **run** the base head is stationary *by
design* (nothing lands until the gate concludes), so the live signal is the **gate job's own output** — no new
log output past ~2× its normal window is a hang (the *long `in_progress` shard* rule below, applied to the
conductor); cancel and root-cause, don't passively wait. During the merge **drain** (members landing
back-to-back), a **base head that stops advancing** past ~2× the per-member cadence is the hang signal there.
Emit progress (members landed / remaining) so a stall is visible instead of reading as healthy idle.

A hung heavy gate is a **can't-check (`UNVERIFIED`), not a pass** — it never authorizes the merge. But don't
block the queue forever: **timebox** it and fall back to the **deterministic runnable subset** (lint / unit /
type-check) as a **proof-of-record** for what *can* be checked, escalating the heavy gate's absence — that
subset is a degraded record, **not** the union's combined-build proof, so it doesn't license merging a member
the union never validated. Keep flaky / heavy browser / visual gates in **per-change pre-merge checks**, not
as a blocking term of the batch union, so one wedged heavy gate can't stall the whole train.

A heavy gate **broken in this environment** — its own harness crashes, a dependency it needs is down — is the
**crash cousin** of the hang above, and likewise a **can't-check, not a red**: "could not check" is not "found
a problem" (the gate discipline in `ux-gates.md`). It must **fail-open for the batch proof** — drop
that one broken term and run the deterministic runnable subset — so batching **continues** rather than
collapsing the whole train to serial merging; one broken tool must not halt all batching. Hang and crash
differ in the **response** and in **what evidence survives**: a hang is **timeboxed then escalated** (validity
genuinely unknown, the gate may still be running) and leaves *no* completed union run; a crash is
**definitively broken here and safe to route around now** and leaves the run's **other** terms genuinely
complete. Both keep the flaky / heavy gate out of the blocking union term, and both hold the **same floor at
the grain each leaves intact**: a hang validated nobody, so nobody merges on the reduced record (the floor
above); a crash validated everyone *except* a member whose essential check **was** the crashed term, so only
those members are held back. Fail-open means the tool's *own crash* is not a red — **never** that an
unvalidated member merges. **Treat a throughput-gating tool as P0:** a broken gate that fails one PR is a
normal bug, but one sitting in the batch-proof path throttles *every* merge — its blast radius is the whole
delivery rate, so it jumps the queue ahead of a gate that only affects one change's correctness.

### A required check must be *satisfiable* — pending forever blocks merge like a red

A branch-protection **required check** gates merges only if some job actually reports a conclusion for *this*
PR. When the required *name* isn't backed by a job that runs and concludes here, the check sits **pending
forever** — indistinguishable from a hang, and merge-blocked exactly as a failure is (its enforcing surface
never saw this PR — `SKILL.md` principle 2). Two ways it happens:

- **A required check with *no status* blocks merge — but distinguish "never ran" from "ran and reported
  skipped."** When `on: pull_request: paths:` filters a whole **workflow** out for an out-of-scope PR (only
  `units/**` changed, so the required `app-browser` workflow never triggers), the check gets **no run at
  all**; the enforcer reads "no status" as not-green and the PR is unmergeable without an override. Fix: give
  the required workflow a **pass-through job** that always triggers and exits 0 on out-of-scope paths (so it
  reports a conclusive Success), or don't name a legitimately-absent workflow in the required list.
  **Contrast** a **job** skipped by a job-level `if:` inside a workflow that *did* run — the forge reports it
  **skipped/Success**, which satisfies the required check and needs no pass-through. The trap is the **missing
  status**, not the skip itself. The pass-through **cuts both ways**: legitimate only when **nothing was in
  scope** (a path filter genuinely excluded this diff); a **false-green hole** when there **is** something to
  check and the *event* — not the paths — routed around the real checker: a required workflow whose real job
  runs on `push` / `synchronize` but whose pass-through also fires on an `edited` (title/body) event reports a
  conclusive **Success** for a PR whose code the checker never re-ran. Make the pass-through reachable
  **only** on the paths/events where the real check is genuinely N/A — never an unconditional `exit 0` that
  green-lights an event the real job ignores. A **locally-added merge preflight** can invert this: when the
  forge itself reports a job **skipped/Success** — a job-level cost-gate `if:` an agent can't flip without an
  owner-only label or a manual dispatch — a preflight that **refuses** that green verdict is *stricter than
  the required check it stands in for* and **deadlocks** anyone without the owner lever (the gate-vs-standard
  rule — a gate must never be stricter than the standard it enforces, `ux-gates.md` /
  `frontend-a11y.md` — applied to CI). Such a preflight must **diagnose why** a check is absent —
  *policy-declined* (cost gate: work exists, a human must grant the run) vs *nothing-to-run* (path filter: no
  in-scope change) — and **name the owner action**, not refuse blindly; conflating the two reports a false
  block and pushes the agent toward the very label it's barred from adding.
- **Trigger-event gap.** A required job whose workflow omits the event that fires the PR never starts *for
  this PR*: a `full-ci` job with no `labeled` trigger, in a label-driven flow, never begins; a
  `workflow_dispatch` run carries its own `run_id` and never attaches to the PR's check rollup, so the
  preflight never sees it. The workflow **existing** isn't the check **running** — verify the required name
  maps to a job whose triggers include how this PR is actually checked.
- **A required check that never runs on a PR — read the `on:` block FIRST, and name the right trigger key.** A
  PR's required check reports on the **PR head**, so the run that satisfies it is a
  **`pull_request`-triggered** run — filtered by **`on.pull_request.branches`, which matches the PR's *base*
  (target) branch**. So when PRs *targeting* a long-lived integration branch show the check as **no-run /
  Pending** (the #262 *no-status* case that blocks merge — not the *skipped/Success* case that satisfies it),
  the load-bearing key is the `pull_request` **base** filter: is the target branch in
  `on.pull_request.branches`? Absent = **structural** (the check can never report on those PRs), not a flake.
  A **distinct** concern in the same `on:` block: `on.push.branches` must list the integration branch to stamp
  *its own HEAD* green via a push run **after merge** — that HEAD-provability point does **not** unblock the
  open PRs. Diagnose in order: (1) target branch in `on.pull_request.branches`? — this unblocks the PRs; (2) a
  job-level cost-gate `if:` (label/dispatch, above); (3) a path filter (diff out of scope — OK); (4) *only
  then* rerun / flake / timeout — and separately, is the branch in `on.push.branches` so its HEAD is provable?
  Reading the `on:` block beats N PR-level reruns chasing the wrong key.
- **Stale-base fails the whole queue at once.** A gate diffing the PR head against **`origin/main`** (not the
  PR *base*) turns one additive commit on `main` — a new row, fixture, or schema entry the integration branch
  hasn't pulled — into a simultaneous failure of **every** PR queued against that branch, with no regression
  in any of them. When N PRs fail the *same* gate at once, check `git log HEAD..origin/main --oneline` for a
  stale base **before** triaging them individually; one `git merge origin/main` on the integration branch
  clears them all. Sync the integration branch on **each** additive `main` merge, not only before the final
  train; a new gate baselined on `origin/main` must **document that assumption** (prefer the PR base for a
  long-lived-branch workflow).
- **A "net-new" ratchet on a merge commit must compare against the merge's own base, not the PR's old merge-base.**
  A lint-warning or count ratchet that diffs against the PR's original merge-base charges the PR for everything
  it just merged in from base, so every PR that merges base forward fails on warnings it did not add. While
  `MERGE_HEAD` exists (or on a merge commit), diff against `MERGE_HEAD` / the base tip. **Check:** merge a clean
  base into a PR that adds nothing; the ratchet must stay green.
- **A change-detection gate's hardcoded base is the scope-selection sibling of stale-base — loud when the
  branch outruns the stale ref, silently skipped when that ref won't resolve.** The bug above corrupts a
  gate's *verdict*; the same mistake in a **change-detection** step — a path filter / "did `app/` change?" /
  "did any migration touch?" check deciding whether a downstream job **runs at all** — corrupts its *scope
  decision* instead. Anti-pattern: a diff pinned to a **hardcoded release-branch constant**
  (`git diff origin/release-v2...HEAD -- app/`) instead of the branch's actual base — its configured upstream
  `@{u}`, the PR's declared target (`github.event.pull_request.base.ref` in CI), or a computed merge-base
  (`git diff "$(git merge-base <base> HEAD)" HEAD`, i.e. `<base>...HEAD`) (the pinned *ref* is the defect;
  merge-base diff semantics are the right choice for a scope check, not the problem). A hardcoded constant
  fails **two** ways. **Loud:** once the branch runs **ahead** of the stale cut, the diff span balloons to the
  branch's whole history since the cut, so the filter reports every gated path touched on **every** push (a
  "changed" verdict that no longer reflects this push — noise and wasted CI, not a correctness bug by itself).
  **Silent (the dangerous one):** a literal ref is a **resolvability** hazard the computed forms mostly avoid
  — in a shallow / partial CI checkout (`fetch-depth: 1`, `origin/release-v2` never fetched)
  `git diff origin/release-v2...HEAD` **errors** (`fatal: bad revision`), and a naive
  `… | grep -q '^db/migrations/'` reads the empty/failed output as **no match**, so the job **skips** a real
  change with nothing turning red. (The positional "branch is *behind* the ref" case does **not** empty the
  diff — three-dot / merge-base semantics correctly report the branch's downstream commits; the silent skip
  comes from the ref failing to *resolve*, not the branch's position.) Fix: derive the base at run time (never
  a literal branch/tag name), **ensure that base ref is actually present in the checkout** (fetch it /
  adequate depth), **fail closed** — a change-detection diff that errors or can't resolve its base must run
  the job (or fail the run), never silently skip — and **have the gate name the base it diffed against** (and
  whether the diff resolved) in its output, so a bare true/false can't hide a wrong-base or unresolved-ref
  result behind a correct-looking "nothing in scope." Distinct from the PR-*targeting* wrong-base rule (below)
  and a pre-push hook's hardcoded range (below — fixed via stdin-derived pushed refs, since a hook has no
  upstream to read); three mechanisms, one root cause: a constant standing in for a computed base.
- **A long `in_progress` shard is diagnosed by its log, not by waiting or re-running.** Past ~2× a shard's
  normal duration, **read that shard's log before acting**: a **hang** (no new output for minutes — a
  deadlocked browser, a port that never opened) is cancelled and root-caused before any rerun; a **timeout**
  (the log shows a test hitting its limit) is left to fail cleanly, then the specific test is triaged. Rerun
  **at most once, only after** diagnosis — a rerun with no known cause is spend with no expected change, and
  parallel reruns (*rerun-storm*) multiply runner cost for zero new signal; treating an hour-long
  `in_progress` as normal (*passive wait*) is the mirror error. Cancel with a note naming the evidence (last
  log line, elapsed time) so the next reader knows it was a hang, not a flake or a stale push.

- **The branch-protection required-check *name* list and the workflow’s job names are two enumerations that
  drift.** Distinct from the trigger-config case above (a check that never fires for a PR): here a job is
  **renamed or retired** in the workflow while branch protection still *requires* the **old** status-check
  name — the old name now has no producer, reports no status forever, and blocks **every** PR (and the mirror:
  a check dropped from the workflow but left required). It reads as "a required check never ran," but the
  cause is a stale hardcoded name, not a trigger gap. Keep the two sets **in sync**: derive the required-check
  list from the workflow definition, or add a test asserting
  `{required-check names} ⊆ {job names the workflow can emit}` so a rename fails CI **loudly** instead of
  silently wedging the queue (the **Lockstep surfaces** discipline, `domain-h.md` — file sets that
  must change together). A retired check name often has **more than one consumer** — branch protection, a
  local merge-preflight script, a merge-queue config — so when a gate moves or is renamed, audit **every**
  consumer, not just the one that surfaced the block.

Read the check's **conclusion**, never the bare colour; a required check with no run for this PR is a **High**
merge-blocker in its own right — name it a config gap (unsatisfiable as wired), not a flake to wait out.

### A new PR-body / artifact gate is a contract with its producers — co-evolve them, or every automated PR silently fails it

Adding a gate that requires a convention in the PR **body** or a committed **artifact** — a `Verify:` line, a
changelog fragment, an evidence image, a commit trailer — silently fails **every producer that doesn't yet
emit it**. Sequencing the gate last in one landing batch (*Merge trains*, above) handles the PRs already *in
flight*; it does nothing for **standing** producers — the PR template, Dependabot / Renovate, a
release-drafter bot, an agent delivery swarm — which keep emitting the old shape on **every future run** until
their **definition** is updated. A human author adapts on their next PR; automation can't, and piles up
green-but-refused PRs until someone notices.

- **Co-evolve the gate and its producers in one change.** Landing a body / artifact gate means updating the PR
  template, the bot/agent prompts, and any PR-generating scaffolding **together** — the gate and every client
  of its contract move as one commit.
- **Grandfather or ramp.** A warn-only period — or a *future* cutover date *T* — buys time while producers
  catch up. A past-dated grandfather exempts only the in-flight backlog: a standing producer's next run is
  always after *T*, so it strands anyway.
- **Make the failure name the exact fix** — the literal line or field to add — so any producer, human or
  agent, can self-correct from the failure text alone.
- **Inventory the producers before adding the gate.** The template, Dependabot / Renovate, release bots, and
  agent swarms are each a **client** of the new convention; the one you don't list is the one that strands.

A gate is a contract with its producers: change the contract without moving them and you break them silently —
and an **automated** producer can't "just adapt" the way a human reviewer does. **In review**, a diff that
adds or tightens a PR-body / commit-trailer / committed-artifact requirement is incomplete unless the same
change updates that artifact's producers (or ramps the gate) — the standing-producer generalization of the
merge-train ordering rule (*Merge trains*, above). The message-payload sibling — a new **required field** breaking old producers
and in-flight messages — is `api-contracts.md`.

### The merge gate verifies WHERE a PR merges, not only that it is green — check the base branch

A PR-open command run without an explicit base falls back to whatever the tool picks — for `gh pr create`, a
per-branch `gh-merge-base` git config if set, otherwise the **repo default branch** (the common case for a
lane that never configured that). When the intended integration branch is *not* the default (work lands on
`development`, but `main` is the protected / owner-gated default), a lane whose brief says "base
`development`" in prose but runs `gh pr create` / the API call **without the base flag** silently opens
against the protected branch — and a merge step verifying checks-green + mergeable but **not the base** then
merges it into the protected branch, a governance breach even when the code is green.

- **Every PR-open passes the base explicitly** (`--base <integration-branch>`); never rely on the command's
  default-to-repo-default behavior.
- **Base-branch identity is a merge-eligibility axis**, next to state / mergeable / checks-green: the gate
  reads the PR's *actual* base and **refuses** anything whose base isn't the expected integration branch — a
  green PR against the wrong branch is not mergeable.
- **Recovery when a PR already merged to the protected branch**: do **not** auto-revert the protected branch
  (itself a gated, owner-level change) — surface it for an owner decision, and separately port the change onto
  the integration branch so the two don't diverge.

**A release PR's *head* is never the shared integration branch — the risk is sharpest when "delete head
branch on merge" is on, but the rule holds either way.** The base-branch check above guards where a PR merges *to*; the symmetric
risk is what it merges *from*. A release PR whose head is the integration branch itself, merged on a host
with auto-delete-head-branch enabled, deletes the integration branch on merge — and the host then retargets
every other open PR based on it to the default branch, silently repointing PRs their authors never touched
at production. Cut releases from a disposable `release/<date>` branch pinned at the release commit; never
use a shared/integration branch as a release PR's head. The merge script or gate refuses any release PR
whose head is the integration branch, and after every release merge, verify the integration branch still
exists before starting the next batch — an automation that merges by PR number with no such check would
merge straight into production the moment the branch it depended on vanished. A contributor-parity file (an
allowlist of public API paths, say) kept as one generated source rather than hand-duplicated in each of
several release PRs avoids the sibling failure mode: two release PRs landing on the integration branch with
that file edited two different ways, disagreeing the moment both are in.

### Self-reported evidence is not a trusted control; a local hook is advisory

A merge decision rests on **trusted** evidence — a run the forge verified on the **exact commit under review**
(a required check must actually report a conclusion for this PR, above; that conclusion names the SHA it
graded, `method.md`). Anything an author can produce or skip locally is **advisory**, never a passing control:

- **Self-report ≠ control.** A local hook (pre-commit / pre-push), a `Tests: N/N` line in a commit or PR body,
  and a checked PR-template box are all self-reported: `git commit` / `git push --no-verify` bypasses the hook
  with no trace in the result, and the text is typed, not executed. "The repo has hooks" or "the PR says tests
  pass" is **never** logged as a green control — record only a forge run pinned to the reviewed SHA (a
  required status that never ran is the merge-blocker above, not "the author ran it locally").
- **A conflict-free `git merge` never invokes `pre-commit` at all — this is not a bypass, it's a missing hook,
  verified against git's own behavior (a clean merge completes despite a `pre-commit` hook set to always
  fail).** Git's internal merge-commit codepath for a **clean** (non-conflicting) merge runs `commit-msg` but
  not `pre-commit`; only a project-installed **`pre-merge-commit`** hook fires there. A repo that wires
  `pre-commit` as its quality gate but never adds `pre-merge-commit` ships every merge-forward,
  sync-from-main, or integration-branch merge **ungated** — no `--no-verify`, no drift, no worktree
  misconfiguration required; the hook the repo relies on was simply never wired to that codepath (distinct
  from both the bypass and the drift bullets above and below — nothing was skipped or stale, the codepath
  never called it). **Compounds** with a custom merge driver that resolves a generated/compiled-file conflict
  by taking one side outright (the merge-driver mechanics are in §6 continued, below, not restated here): a clean
  auto-merge can silently leave that generated file **stale** (missing the other side's regenerated
  contribution), and with no `pre-merge-commit` hook, nothing re-checks freshness before the merge commit
  lands. **Detect:** `git config --get-regexp '^merge\.'` for a take-one-side driver on a generated path, and
  confirm whether `pre-merge-commit` exists alongside `pre-commit` (`.git/hooks/` or the configured
  `core.hooksPath`). **Fix:** add a `pre-merge-commit` hook mirroring `pre-commit` — at minimum the cheap
  regenerate/freshness check for any generated artifact — and a test asserting a zero-conflict merge is
  actually gated; re-generate and diff generated files after any merge even when git reports no conflict.
- **A *drifted local copy* of a CI gate is a false green even when the author ran it in good faith.** The rule
  above covers a local check *skipped or bypassed*; the subtler case is one that **ran and passed and still
  means nothing** — the same gate lives as both a CI job and a local convenience copy (a `pre-push` script, a
  `make verify` / `scripts/check.sh` target, a vendored paste of the CI logic), and the local copy **drifts
  behind** the CI definition. It reports green on a change CI will reject; the author reasonably says "it
  passed locally" and reads the red CI as a flake — grounds for an `--admin` override that then merges what CI
  would have caught. Fix: **single-source the gate logic** — the local entry point **invokes the exact script
  the CI job runs** (one file, two callers), or a version/digest check **refuses to pass locally when the two
  diverge** — so a local pass can never mean *less* than a CI pass. This is the gate-logic case of *audit
  every consumer when a gate moves* above (a local merge-preflight is one such consumer) and of domain H's
  duplicate-source-drift (one source, not two copies that fall out of step); the trusted control stays the
  forge run pinned to the reviewed SHA. (The sibling **design** question — an evidence gate must require a
  source that *renders for the reviewer*, an uploaded attachment, not a raw-content-host link that only
  *looks* like evidence — is `ux-gates.md`'s "gate on visibility, not presence.")
- **The *absence* of a hold marker is not authorization — a mutable-text hold can be edited away.** The mirror
  of the rule above: where a merge is blocked by a "DO NOT MERGE" / hold marker in a **mutable** surface (a
  PR-body line, a checklist box, a label a bot can toggle), its **disappearance** is self-reported too —
  anyone, or an automated body-edit, can clear it with no approving review and no trace. A preflight that
  reads "no hold marker present → clear to merge" is fooled by deletion-by-edit. Back a hold **out of band**
  (a branch-protection rule, a required review, a status check the author can't toggle), never mutable body
  text alone; make body-editing automation **append/insert-only** with a before/after diff; and treat a
  hold-marker *disappearance with no corresponding approving review* as **STILL HELD** (fail closed).
- **Hooks under a worktree gate the wrong thing.** In a linked worktree (the multi-lane setup the red
  flags in `branch-and-merge-hygiene.md` cover), a hook wired for the primary checkout misfires: an **absolute `core.hooksPath`** is shared by
  every worktree, so a hook authored for the primary checkout also fires in every sibling — one resolving
  paths from a hardcoded location rather than the invocation then examines the wrong tree; and a pre-push hook
  diffing a **hardcoded default branch** gates the wrong range. A pre-push hook's real range is the pushed
  refs it receives on **stdin** (`<local-ref> <local-sha> <remote-ref> <remote-sha>`) — derive scope from the
  event, not a constant, and don't bake an absolute hooks path a sibling worktree will inherit. A hook that
  silently gates the wrong files is worse than none: it reports green over unexamined changes — another reason
  the hook tier is advisory and the forge run is the trusted gate.
- **A git-tracked file the build regenerates poisons a clean-tree gate run in the same working tree.** If a
  build step rewrites a **committed, tracked** file (a generated bundle, a `dist/` artifact, a lockfile a
  postinstall touches), any gate asserting a clean working tree — a merge preflight, a pre-commit/pre-push
  hook, `git diff --exit-code` in CI — goes **red on a dirty tree the build itself created**, not a real
  defect, so running the build to satisfy one gate breaks the next. Fix at the source: **don't track a build
  output** (gitignore it, generate at build time), or if it must be tracked, regenerate deterministically and
  commit it as its own step, and scope the clean-tree check to **exclude the generated path**, or run the
  clean-tree check in a **fresh checkout the build never ran in** (the merge-train's throwaway integration
  branch, above, does exactly this) — never "run the build, then assert the tree is clean" in the same working
  tree. (Distinct from the run-twice idempotency check, about an *untracked* generated artifact polluting a
  later step across runs; this is a *git-tracked* artifact whose committed baseline the build invalidates on
  every run.)

### A worktree-relative hook runs its base's copy — land the safe hook everywhere first

Resolving hooks relative to the invoking worktree (the fix above) has a second-order failure: each worktree
then runs the hook **as checked out at its own base**. A worktree cut from an old commit or a long-lived
feature base runs *that base's* hook — not the one the team now intends — so if an older hook is slow, prompts
interactively, or hangs on a step the environment no longer satisfies, every lane off that base inherits the
breakage, misattributes it to "flaky / slow tooling," and bypasses the whole tier (worse than no tier —
everyone still believes it runs).
- **Hook content is fail-safe by default.** The committed hook runs a fast, always-safe core and makes every
  slow, environment-dependent, or interactive step **opt-in** (an env flag or a marker file), so an old copy
  can never hang or block a push on a step the environment can't satisfy. A hook that can hang is a hook that
  will be bypassed.
- **Order matters: land the safe hook on every base people branch from *before* normalizing the path.** Since
  a worktree-relative hook runs the base's copy, the fail-safe hook must already be merged into the default
  branch *and* every long-lived integration / feature base first; normalizing resolution while old bases still
  carry the old hook guarantees stale-hook execution.
- **"Which hook runs here" is base-dependent — verify it.** Confirm the worktree's hook matches the intended
  version; make hook installation idempotently re-assert the current version rather than trusting inheritance.
- **A push-blocking step needs an audited, reason-required escape hatch**, so a genuinely stuck lane is never
  forced into a traceless whole-tier bypass (which disables *every* step, not the one bad step).

### On a stacked PR, attribute a CI failure to the commit that owns it

A PR stacked on another (B's base is A's branch, not the mainline) contains A's commits, so B's own CI runs
them too — and a failure A introduced turns B red without B changing anything. Before diagnosing (or "fixing")
a red on a stacked PR, find which commit the failing step belongs to: `git log <merge-base>..<head>` is the
PR's **own** diff, and a failing step in an **ancestor** commit from the base branch is the **base PR's**
defect, not this one's. (Knowing which *run* the red is even for is the companion rule — a run's conclusion
names the SHA it graded, `method.md`.) Attribute it to the base PR and let it fix there; **never commit the
fix onto the downstream PR** — once the base merges, the same fix lands twice: a double-patch or a conflict. A
stacked PR is only truly green once its base has merged and it's been re-run on the mainline.

### A stop halts new work — a MERGEABLE PR and an unpushed rebase are not "new work"

`STOP` / interrupt means **no new lanes, no new commits, no new scope**. It does **not** pause landing a PR
already green and `MERGEABLE` against its intended base, and doesn't license leaving committed work stranded
off the remote. Two things must be true before a stop is actually complete:

- **The MERGEABLE set is not silently abandoned — but a stop grants no new merge approval.** Enumerate the
  open PRs that are green + `MERGEABLE`; finished work must not vanish because a stop arrived. Merging is a
  shared-state action, so §6's gate still holds: **merge only what already had standing approval** (per its
  preflight — the red-base discharge above governs *how* such a merge lands, not *whether* you may fire it),
  and for everything else the stop-complete step is to **hand it off by URL** to the next owner. A green PR
  left un-merged and handed off is not the loss; an irreversible merge fired *because* a stop arrived —
  approval a stop can't itself grant — is the §6 regression.
- **No unpushed commit is left silent.** An interrupted rebase/amend often leaves the new SHA **local only**;
  a stop taken there can strand it forever (a later push flake then loses it). Push before stopping, or print
  the recovery triple in the stop message — the **absolute worktree path**, the **branch**, and
  `git rev-parse HEAD` — so another lane can retrieve the tree. "Push failed / a flake" is not a completed
  stop: retry the push or hand off the path.

### §6 continued — rails for executing a triage row (delete, close, resolve, absorb, automate)

- **Close the issue a merge was meant to resolve only after the merge is
  confirmed to have landed — never on "the merge command returned success" or
  "the merge was requested."** Automation that merges a PR and closes its
  linked issue in the same step, without waiting for confirmation, can close an
  issue whose merge failed or landed in a dirty state under a transient
  failure — a race with another merge, a conflict surfacing only during the
  real merge operation, a permission hiccup. A closed issue reads to every
  later human and agent as "this is done"; if the change never actually
  landed, the backlog now understates real remaining work and nothing is
  watching it anymore. Gate the close on a **confirmed post-merge state**: the
  target branch's head commit actually contains the merged change, verified by
  commit ancestry (`git merge-base --is-ancestor <merged-sha> <base-branch>`)
  or an equivalent check — not merely that the merge API/command returned
  success. To verify the gate itself works, inject a merge failure (a
  conflicting concurrent change) into a test run and confirm the issue is
  **not** closed when the merge does not actually land, then confirm it **is**
  closed once a real, verified merge completes.
- **A branch can be safely merged-away and still be another PR's base — check before deleting *any* branch,
  even a confirmed-merged one.** If another open PR uses this branch as its **base** (a stacked PR reviewing
  changes on top of an unmerged branch), deleting the base auto-closes the stacked PR on most forges, with no
  reopen/retarget once the base ref is gone — even though the underlying commits may survive a while in
  reflog/backup. Check first: `gh pr list --state open --base <branch>`. If any exist, retarget them
  (`gh pr edit <n> --base <new-base>`) or get explicit confirmation that losing that PR's thread is acceptable
  — every time, not only when a stack is suspected.
- **Once a stacked PR has already auto-closed this way, pushing more commits to its branch does not revive it
  — it recreates a bare orphan branch with no PR attached**, so the work must be re-proposed as a new PR
  (retargeted onto the shared base, or rebased onto the parent's post-merge commits) rather than "fixed" by
  pushing again. Prevent it instead: retarget the child PR onto the shared base **before** merging the parent
  (`gh pr edit <n> --base <shared-base>`), or open the child against the shared base from the start and rebase
  onto the parent's commits rather than branching off the parent's own branch — the check-before-delete
  mechanics are the bullet above. **Corollary for reading PR state during any triage:** a forge's `closed`
  state doesn't distinguish "closed via merge" from "closed unmerged" — this orphan-close and a normal
  squash/merge both read `closed`. Before treating a closed PR as done or its branch as safe to delete, check
  the `merged` field too (`gh pr view --json state,mergedAt`), never `state` alone.
- **Never hand-resolve a merge conflict inside a generated/compiled file.** When two branches both regenerate
  the same derived artifact (a build output, a compiled config, a generated manifest/index) and a merge
  conflicts inside it, take either side, then **re-run the generator** against the merged source inputs —
  never hand-splice the two conflicting versions. A hand-merged generated file can be syntactically valid and
  still contain a combination no run of the generator would ever produce, and the corruption is often silent
  until a much later read (cross-ref domain H: a generated/source pair needs a parity test or a single
  generated source so this doesn't drift over time — same failure, at the moment of a merge conflict rather
  than over time).
- **Two PRs regenerating the same artifact can both be valid with *no* conflict — a silent regression, not a
  merge error.** The rule above fires on a conflict; the worse case fires on none. When two open PRs each
  rebuild a derived artifact (`out/`, a lockfile, a compiled index, `app/data/`) from a shared source tree,
  each writes a valid file from its **own** base, git merges both cleanly, and whichever lands second
  **silently drops the first's regeneration** — nothing marks it. Trigger to watch: this PR regenerates an
  artifact **and another open PR touches the same source** that produces it
  (`gh pr list --state open --limit 500` — the `--limit` matters, §1). Fix: the second PR **rebases onto the
  merged first and rebuilds** from the combined source (a superset fold), never layering its own partial
  build. Flag a generated-artifact PR as **superset-fold-required** while a sibling source PR is open.
- **A PR whose *only* conflict is a generated/compiled artifact re-conflicts on every same-class merge — a
  structural loop, not a normal rebase-able conflict.** When the sole conflicting path is a **derived file
  neither side hand-edited** (a lockfile, a bundled `dist/`, a checksums/manifest file, a generated schema or
  client) and many open PRs regenerate it from a shared source, "rebase and it's clean" is false **by
  construction**: each same-class PR that lands **rewrites that serialization**, so a branch you just rebased
  green re-conflicts before it can merge, and under steady merge volume it re-stales faster than any
  human/agent can rebase — an unwinnable loop that reads as a perpetually "almost-ready" PR while compute
  burns on re-rebasing. Distinct from the silent-drop case above, which fires on *no* conflict (last writer
  wins); this fires on a conflict that **never clears**. Distinct, too, from `merge-operations.md`'s sweep-while-resolving
  treadmill (a *coordinator* re-dirties a cluster with a concurrent merge sweep): this needs no coordinator —
  ambient merge cadence alone drives it. **After the second re-conflict whose only path is a generated
  artifact, stop rebasing** and change strategy: get the PR green + mergeable **once** and land it inside a
  window where no same-class PR merges (`merge-operations.md`'s freeze-the-merge-step / a single merge-seat holding the class's
  other merges for the brief handoff), always **taking trunk's copy and re-running the generator** rather than
  hand-splicing (the regenerate-from-merged-inputs rule above). **Durable fix — stop conflicting at all:**
  regenerate the artifact as a **post-merge / CI step** (or stop committing it and build it in CI), or
  serialize the class and regenerate it **last**, so same-class PRs never block each other on it. A local git
  merge driver looks like the durable fix but only mitigates *your* local merge — see the next bullet. **🚩**
  rising rebase attempts per merged PR whose only conflicting path is a generated file; treating a
  generated-only conflict as resolve-by-rebase.
- **A git merge driver resolves the artifact conflict only on a *local* merge/rebase — the forge's server-side
  merge never runs it, so the PR still shows CONFLICTING.** Registering a custom driver
  (`.gitattributes merge=<driver>` + a resolver script set up per-clone) so conflicts in the artifact
  auto-resolve (take either side + regenerate) fixes only a **local** `git merge`/`rebase` on a clone where
  the driver is registered. A merge driver is a **client-side** feature — registered per-clone in local git
  config, run only by git on a clone that has it — so a host computing mergeability and merging on **its own
  servers** has no reason to run your repo's local resolver and treats the artifact as an ordinary conflict.
  On **GitHub** this is observable: the "Merge" button / merge API / auto-merge / merge queue and its
  mergeability computation **ignore custom `.gitattributes merge=` drivers** (should generalize to other
  forges but is **not independently verified** here, per the async-mergeability note in `merge-operations.md`) — so a PR whose
  only conflict is the driver-handled artifact still displays **CONFLICTING indefinitely**, the host merge
  button stays disabled, and auto-merge never fires, even though the conflict is trivially auto-resolvable on
  any driver-registered clone. Teams then waste effort "rebasing to fix it" through the host UI (which can't),
  conclude the driver is broken (it isn't), or build a second driver (redundant). **Don't read
  host-CONFLICTING on a driver-managed path as a real conflict** — confirm whether the *only* conflicting path
  is the driver-managed artifact. **Land it via a local merge/rebase on a driver-registered clone, then push
  the resolved head:** the local resolution leaves no conflict, so the push flips the host to MERGEABLE and
  the normal host merge then works; **document the mechanic next to the driver** ("resolve/land locally; the
  host won't run this driver"). The rule uniting both bullets: **a merge driver is a client-side convenience
  for your own merge; it never changes the PR's forge-visible state** — the only host-visible fix is a
  **pushed commit that carries no conflict** (regenerate-and-push, or don't commit the artifact and build it
  in CI, previous bullet). **🚩** a PR stuck at host-CONFLICTING whose only conflicting path is a
  driver-managed generated file.
- **A subset absorbed at a stale SHA can revert a later fix — no conflict, last writer wins.** Distinct from
  the superset-fold case above (a *derived* file rebuilt from source): here PR B **absorbed PR A's own source
  content** at an **older** tip, missing A's later commits (say a disabled-submit guard A fixed in
  follow-ups). Merge A, then merge B, and B's stale copy of those files silently overwrites A's fix — git sees
  no conflict, so nothing warns. Before landing: if B's history carries a **subset of A at older SHAs** (same
  files, earlier commits), don't merge B as-is after A — merge the **fuller tip first** and rebase B onto it,
  replaying only B's unique commits, **or** fold A's missing commits into B and merge B once. After landing,
  **grep the live tree for the fixed symbol** (the guard, the hard limit); never trust "B included A."
- **Before closing a PR as duplicate or superseded, diff the two tips — title or branch similarity is not
  patch equality.** Two PRs that look like the same fix can differ in a hunk only one carries (one tip gates a
  `useReducedMotion` check behind a mount guard — `mounted ? … : false` — the other reads it directly);
  closing the "duplicate" drops that hunk silently. Compare the heads first: **two-dot**
  `git diff <tip-A> <tip-B>` when they share a base (the literal difference between the two trees — empty iff
  the tips are identical), or `git range-diff <base>..<tip-A> <base>..<tip-B>` to compare the two **patch
  series** when the PRs forked from different points, which a plain two-dot pollutes with mainline drift. (Not
  three-dot `A...B` — that diffs from the merge-base, the `git log` commit-range idiom, so it can't tell you
  what B has that A lacks.) If B carries hunks A doesn't, **fold them into A** (rebase or cherry-pick) and
  *then* close B with a pointer; close-as-duplicate is safe only when that diff is empty or B ⊆ A with no
  unique lines. Put the **diff result in the close comment** as evidence; "looks the same," a shared branch
  name, or a shared issue number is never sufficient alone.
- **Gate an irreversible command on the verdict string, not just "ran" — and make sure a list-membership guard
  actually checks the list.** Two related failure shapes, both "the guard didn't guard because the shell's
  real semantics differ from the author's mental model":
  - A preflight/safety script's *contract* is often to print a pass/fail verdict while still exiting 0 (so a
    human watching sees the message) — or its exit code is checked but the next command runs unconditionally
    regardless. `./preflight.sh; ./publish.sh` (a bare `;`, or two unconditional steps) fires the irreversible
    command whether or not the gate passed. Before recommending or running a merge/delete/publish/deploy
    command, confirm the preceding gate's **documented pass condition** (an exact string and/or exit code
    checked with `&&`/`if`), not merely that it ran without erroring.
  - A **safety-critical exclusion list** (a held/blocked/do-not-merge set) is commonly checked with
    `for x in $LIST; do [ "$x" = "$item" ] && skip; done` — this silently breaks under any shell where an
    unquoted `$LIST` doesn't word-split (zsh, by default, doesn't; `for x in $LIST` then iterates **once**
    with `x` bound to the whole string, so the comparison almost never matches and the exclusion never fires).
    A script meant to run in "the reviewer's shell" can't assume bash's word-splitting semantics. Use a
    **literal `case`/explicit split** instead — `case "$item" in id1|id2|id3) skip ;; esac`, or a line-based
    exact match (`printf '%s\n' "$LIST" | grep -qxF "$item"`) — for any exclusion check gating an irreversible
    or shared-state action (a held-PR exclusion in a merge script is the canonical instance: a silently-broken
    guard here doesn't fail loud, it just merges the thing supposed to be excluded). Detector: grep scripts/CI
    config for a for-loop iterating an unquoted variable immediately followed by a merge/delete/publish/deploy
    call, and confirm the loop actually iterates more than once against a multi-item fixture in the shells the
    script claims to support.
- **Automated conflict resolution is gated on a marker-grep, not on `git add` exiting 0.** `git add` stages
  whatever is on disk — conflict markers and all — so a resolution step whose
  `git checkout --theirs -- <path>` silently failed can still be staged and committed with `<<<<<<<` /
  `=======` / `>>>>>>>` in the tree (caught, if at all, only by a later parse error). Two mechanical
  backstops, both required for agent/automated resolution where no human eyeballs the diff: **quote/escape
  every path with glob metacharacters** (`git checkout --theirs -- 'app/kpis/[key]/page.tsx'`, or disable
  globbing with the shell's own switch — `set -f` in bash/POSIX sh, but `setopt noglob` / a `noglob`
  precommand in **zsh**, where `set -f` is NO_RCS and leaves globbing on — since a `[param]` / `*` / `?` path
  glob-expands differently per shell, zsh erroring on a no-match while bash may pass the literal, so an
  unquoted resolution silently no-ops); and **grep the staged tree for conflict markers before every commit,
  gating on the result** —
  `git grep --cached -qE '^(<{7}|={7}|>{7})' && { echo 'unresolved markers'; exit 1; }` (exit 0 = a marker was
  found → block), or git's built-in `git diff --cached --check`. A bare `git diff -G` *prints* the hunk but
  **exits 0**, so it doesn't gate — and `add` success is never proof of resolution; the gating marker-grep
  plus a build/parse is.
- **Update a branch another worktree still holds with a detached-HEAD fast-forward, never a force-push.** When
  the branch you must update is already checked out in another (often stalled) worktree,
  `git worktree add <branch>` refuses and force-pushing to escape it **strands** that lane — discards commits
  the lane had already pushed (orphaned on the remote) and leaves its local ref and unpushed work on a
  now-diverged branch. The non-destructive primitive: `git worktree add --detach <dir> origin/<branch>`, do
  the work there (merge the base in, resolve, run gates), then push `HEAD:<branch>` — a **fast-forward** when
  the remote ref is an ancestor of your new HEAD (verify that first; if diverged, it needs a real merge, not a
  push). The "already checked out" collision is usually a symptom of stale worktrees never pruned —
  `git worktree prune` (and removing a merged lane's tree) clears it.


### Browser proof lives in the train and a nightly run, never only at release

A release went red on deploy day with 40 real browser failures after about 260 merges proven by unit tests alone; the browser suite had never run on the integration branch between releases. The rules:
- **Trains run the affected browser specs plus a smoke set on the union before landing** (`BROWSER_CMD` in `train_land.sh`). Skipping is an explicit opt-out (`BROWSER_CMD=skip`) that warns loudly; an unset hook warns too. The full suite is not per PR: cheap gates (type check, ratchets, touched specs) run first.
- **A nightly full browser suite runs on the integration branch's HEAD**, on the least-loaded machine, never the coordinating one (heavy QA there starves the coordinator and turns the signal into noise). A red run is a P0 within the hour and **feature merges pause until it is green**.
- **Cut the release a day before deploy**, with a full QA receipt by end of that day. Deploy day is fixes-only: no branch refresh that restarts QA.
- **Check:** count PRs merged since the last green browser run; a nonzero count with no train or nightly that ran browser specs means the gate was skipped.

### Run the merge preflight from the PR's own worktree and assert HEAD equals the PR head — cheap gates first

A merge preflight (receipt, changelog, clean tree) reads the current working directory. Run from a shared clone, it validates the wrong tree and can pass a PR that should be refused. Run it from the PR's own worktree, and have it assert that the checked-out `HEAD` equals the PR head SHA before reporting anything; refuse on a mismatch. Order the gates cheapest first (changelog, whitespace, file-size ratchets, then the expensive suite) so a trivially refusable PR fails in seconds. **Check:** run the preflight from an unrelated checkout; it must refuse, not pass.

### Merge-train fast path — batch it, prove it once, land each PR pinned to its proven head

Three scripts in agentic-delivery's `scripts/` (paths and refs come only from args or env) package the loop;
`merge_train.py` stays the verifier and the scripts wrap what comes after it. Read each script's header for its env.
- `train_land.sh <tag> <pr> <pr>…` union-verifies via `VERIFY_CMD`, then lands only if the verdict is `GREEN`.
  It refuses a **single-PR train** (one PR takes the normal merge path; a train's cost is amortized only over a batch)
  and a RED union lands nothing.
- `land_train.sh <base-sha> <union-sha>` lands each member **pinned to the head SHA the union proved**
  (`gh pr merge --match-head-commit`). A member whose head moved is skipped, never merged unproven; it waits out
  `mergeable=UNKNOWN` instead of treating it as a conflict; it readies a draft; and a PR with no changelog fragment
  is appended to a **backfill list** (a visible follow-up), not skipped or silently merged without one.
- `reap_own.sh` kills only dev servers owned by the current user whose cwd is under your own tree and idle more
  than 2 hours, so it is safe to run on every tick; never `pkill` by pattern (`dev-env-ownership.md`). Every kill
  is verified (`kill -0`, SIGKILL after 5 seconds). `--report` is the read-only cross-session mode: it lists
  orphans by worktree path and never kills.
- `clean_finished.sh` removes your own worktrees whose PR is merged or closed or whose lane handed back, and
  deletes your own scratch. A dirty one is archived first (`git diff HEAD` plus the untracked list). It skips a
  worktree a process still uses or that has unpushed commits, so cleanup stays reversible.

Everything finished is cleaned automatically, but only what you own or what is provably finished: at train start
(`CLEAN_ROOT` on `train_land.sh` runs both scripts), at lane teardown, and on every coordinator wake. Anything
else is report-only. The hand-back check is `ROOT=<lane worktree> reap_own.sh --report` printing `orphans=0` (no
server or listener left under the worktree). The coordinator-wake check is the same `--report` without `ROOT`:
free RAM plus any `FINDING hot` line (a process at high CPU for more than 2 hours is a finding to act on, not noise).

Operating rules the scripts rely on:
- **Run the train scripts from a detached tools worktree on the base branch**, not from a lane checkout whose
  branch or tree moves under them; the script re-detaches it onto the fresh base before each verify.
- **Find the union by commit, not by name.** When a culprit is dropped and the train reruns, the rerun's worktree
  gets a new name; `land_train.sh` searches `UNION_DIRS` for the one that contains the union SHA.
- **In a shell loop, give every `gh` call `</dev/null`** (it reads the loop's stdin and eats the rest of the
  list), and **`set -o pipefail` before `gate | tail`** (or the pipeline's status is `tail`'s and a red gate
  reads green). Filter verdicts by prefix, not position (above).
- **Freeze merges while a release is cut** (above); browser proof is in the train and nightly run
  (`Browser proof lives in the train…`, above), and per-PR gates run cheap checks first so the expensive suite only
  sees a candidate that already passed them (`Run the merge preflight…`, below).
