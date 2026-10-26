# Fast agentic delivery — fan-out sizing and host resourcing

Read this when: sizing a fan-out or capping in-flight write lanes, cutting per-lane cycle-time or handback
verbosity (a billed-output cost lever), gating a spawn on free RAM, the swap trend, disk, or CPU, capping a
dev/build server's memory, pacing lanes to a shared API/model quota, rechecking a remembered constraint-state, or
tearing down a worktree and its helper processes. Part of the `fast-agentic-delivery.md` lesson ledger — its index,
sources, and cross-references live there; an "above"/"below" pointer to a section not in this file resolves through
that index.

---

## Environment probe procedure (host sizing before fan-out)

`full-map.md` **Environment probe** states the act-on rule — probe before sizing, and gate on free RAM and the swap
trend. This is the full procedure it points to.

- **Probe:** free RAM and CPU cores (`memory_pressure`/`vm_stat` or `free -h`; `nproc` or `sysctl -n hw.ncpu`),
  disk (`df -h`), and which tools/connectors this session actually has usable auth for. A lane dispatched
  against a connector that needs an auth flow it cannot complete fails at the worst point — after it already
  holds a worktree slot.
- **Decide from the probe, not from habit:** how many HEAVY lanes (a real build, browser test, or compute
  process) this run supports — tighten under memory pressure even where a core-count formula would allow more,
  since a machine can exhaust RAM before it exhausts CPU slots; which model tier a lane needs
  (`model-tiering.md` in the `deep-code-review` sibling) — frontier only where the blast radius already calls
  for decorrelation, not by default; and whether a heavy gate runs locally at all or waits for CI/a shared
  runner when local capacity is short.
- **Shell semantics belong to the probe, not to guesswork mid-script.** Know which shell will actually run a
  script before writing a list-membership or exclusion check in it — `merge-operations.md` has the
  concrete failure mode and the portable fix; this step only says *check*, not what to write.
- A
  **failure that only appears under heavy fan-out concurrency is contention, not a defect, until reproduced at low concurrency**
  (`parallel-audit.md` §0) — probing capacity first is what keeps that distinction from being made after the
  fact, on a report already full of false timeouts.

## Size the fan-out to the decomposition, not to available concurrency

`SKILL.md` states the rule — never more lanes than there are independently-verifiable objectives, and pilot
before full fan-out. The detail: a lead that hands out vague, overlapping instructions gets duplicated work, not
more coverage — subagents given no clear boundary have been observed independently re-investigating the same
ground (Anthropic, multi-agent research system). Default tiers: a single fact/lookup needs one lane; a bounded
comparison needs 2-4; only a genuinely decomposable task graph justifies 10+, and each of those needs its own
objective, output format, and explicit boundary against its siblings — spawning dozens of subagents for a simple
query is a named failure mode, not a hypothetical one. **Pilot before full fan-out:** on a wide, mechanical
batch, run a handful of lanes first, fix what the pilot exposes, then commit the rest of the width — cheaper
than discovering a bad task boundary after the full width is already running.

**Cap fan-out width at the codebase's editable seams, not machine headroom alone.** The probe above sizes width
from RAM/CPU; that ceiling is silent about how many independently-editable regions the *planned work* actually
touches. When most of the plan concentrates on a handful of large, shared files, lanes collide on those files
regardless of headroom — merge conflicts, dedicated conflict-resolution lanes, repeated batch/train
re-verifications of work already checked once. One observed run: a fan-out sized to a double-digit lane count on
available memory, where a large share of those lanes targeted one of a handful of large shared files, producing
repeated conflicts and forcing several full batch re-verifications of the same integration branch before it
landed — cost the memory-only sizing never anticipated. Before sizing a wide fan-out, count the planned work's
distinct files/modules (weighted by how many lanes target each) and cap width at
**min(editable seams, machine headroom)**, not headroom alone. Where the plan needs more lanes than a shared file
can support, **split that file first** with a dedicated pure-move/no-op lane (*Split a shared hand-edited file
before fanning out*, below) and land it ahead of the fan-out, rather than accepting collisions as parallelism's
cost. Worked example: a plan lists a dozen fixes, but seam-counting shows most of them land in the same two
shared files — correct sizing narrows the fan-out to one lane per shared file (serializing the fixes that
target it) instead of one lane per fix, and inserts a split-first lane ahead of the fan-out for the file with
the most collisions.

## Escalate a lane, don't just retry it

**Escalate a lane, don't just retry it.** After two equivalent failures on the
same lane, change approach — not the same fix again (`SKILL.md` *Failure*). In order
of cost: reframe the task boundary, decorrelate (fresh context or a different
model), or move to a stronger model tier (`model-tiering.md`) — start at the
stronger tier only when blast radius already calls for decorrelation
(`idea-critic`'s high-blast rule), not by default; a cheaper tier that clears the
gate is preferred.

## Cap in-flight write lanes by landed artifacts, not lane count or headroom

The decomposition rule above sizes the *total* lanes against objectives; this caps the *in-flight* write lanes
against what has actually **landed**. Its failure is **hours of real spend with the integration head unchanged**
— many concurrent write lanes spawned and re-prompted, yet only a fraction ever reach the remote. "N lanes
running" is the orchestrator's own activity, not delivery, and it worsens with concurrency: each write lane pays
env-setup + install + boot + (for UI) a browser gate largely **serial on the machine**, so past a point a new
lane delays every lane; and routing/dedup/reconcile of N lanes consumes the coordinator — the only actor that
integrates.

- **Lane progress is a durable artifact** — a pushed branch, an opened PR, a committed diff on the integration
  branch — **never a running transcript** (the transcript-is-not-liveness rule below, applied to delivery rather
  than health). A lane with no artifact has produced nothing, however busy it looks.
- **Report the artifact, not the activity** — the status is "**M landed, K in flight, head at `<sha>`**", never
  "N lanes running."
- **Admission is earned by completion** — hold write lanes to a small WIP limit (default low; a WIP limit is an
  *enabling* constraint, Sources) and don't spawn lane N+1 while N are in flight with zero artifacts. Check the
  delivery ratio (landed ÷ spawned) each interval; near-zero for a full interval means
  **stop spawning and drain** (finish or kill what's in flight and integrate what exists), never add lanes.
- **An adaptive throttle must never shrink the pipeline's known bottleneck stage's own capacity — throttle the
  feeders instead** (#1154). A push queue (or any other identified constraint) that a load-triggered throttle
  cuts down to fewer slots is not protected, it is starved harder at the exact moment load is highest and
  throughput matters most; the WIP-admission cap above is that correct direction already — it slows the rate new
  work *enters* the pipeline, never the constrained stage's own concurrency. If the bottleneck's own capacity must
  move under load at all, growing it is the only direction that helps.

## Once lanes are saturated, cut per-lane cycle-time before adding lanes — throughput = WIP / cycle-time

On a capacity-bound machine (a fixed number of concurrent heavy lanes), delivery throughput is
**WIP / cycle-time** (Little's Law). Once lanes are saturated, the highest-leverage move is
**cutting per-lane cycle-time, not raising lane count** — more lanes past the CPU/RAM cap thrash (everything
crawls), *lowering* throughput. Distinct from the WIP-cap section just above (which throttles lane *admission*
by landed artifacts): this throttles *time-in-lane* once admission is already capped — the positive dual of the
fan-out-sizing rule. Ranked levers:
- **Faster gates per lane** — run only **diff-affected** tests (test-impact analysis) and
  **cache dependency installs** so they are not re-paid in every isolated worktree; the
  **full suite still gates the batch / merge-union**, so per-lane speed does not trade away correctness (this
  extends the *CI-offload the heavy gate* section below from a RAM rationale to a cycle-time one, adding dynamic
  diff-affected selection and dependency-install caching).
- **Amortize the fixed gate cost** — batch several atomic, low-collision changes into one PR rather than paying
  a full gate per tiny PR.
- **Merge trains** — verify the union once, merge members back-to-back, avoiding a per-PR base-CI wait
  (mechanism in `deep-code-review`'s `merge-operations.md`).
- **Break the machine ceiling** — move lanes to remote / cloud runners once the local cap is the bind.
- **Eliminate rework** — verify-first + decorrelated pre-merge review + auto-merge-on-green, so a lane rarely
  does a wasted second pass.
- **Shrink the shared collision surface** — when saturated lanes still stall with the hardware idle, the
  cycle-time they pay is often a *queue* on one shared **generated** artifact every lane must rewrite (a
  lockfile, a compiled bundle, an aggregated registry/index), which serializes them however disjoint their
  source edits are. Cut it by making that surface **smaller** (slice the work so fewer lanes touch it, or
  generate per-slice and aggregate once) and giving the chokepoint a **single owner** or a
  **read-through cache** — not by adding lanes (a longer queue). (Invisible-ceiling cousin of the shared-quota
  section below.)
- **Split a shared hand-edited file before fanning out** — when 2+ planned lanes would write one source file
  (one lane per section of a big page), don't serialize them: dispatch one **pure-move** lane first (a module
  per section, a shared module for helpers 2+ sections use, the old path kept as a transitional re-export
  whose importers move to direct paths — `deep-code-review`'s `web-render.md` barrel rule). No logic,
  markup, or style change; gate it on type check, lint, an **unchanged test count**, and a smoke render.
  Merge it, then fan out one lane per module.

**🚩** an orchestrator raising lane concurrency past the probed CPU/RAM cap to "go faster" while per-lane
cycle-time (setup + gate) is untouched — that lowers throughput, not raises it.

## A lane's own handback is billed output — verbosity is a cost lever distinct from what it reports

`SKILL.md`'s Output contract states what a worker returns; nothing there bounds how much prose carries it. In a
fan-out or an unattended multi-round loop that gap compounds: every lane's progress narration and closing report
is tokens the lane is billed to generate and, wherever a handback reaches an orchestrator's own context, tokens
the reader re-pays to process — cost scales roughly as **lane count × output length per lane × rounds**,
invisible in one lane and dominant across N lanes and M rounds of an overnight run.

- **Terse the prose, never the required fields.** Cut narration, a restated brief, an unrequested worked
  example, step-by-step "now I'll" chatter — never a required Output-contract field (role, exact SHA, artifacts,
  acceptance covered, commands actually run with exit status, findings with severity + location + evidence,
  remaining risk, cost/`UNPRICED`). A shorter report missing a field is not terse, it is `UNVERIFIED` by
  omission (gate epistemology principle 3), not a cost win.
- **Size the closing handback to the next decision, not to the transcript that produced it** — a gate verdict,
  the finding's `file:line`, the branch/SHA pushed, and each required check's pass/fail is what the next action
  consumes; the turn-by-turn narrative is not, and mid-lane progress chatter pays the identical per-lane,
  per-round multiplication as a bloated final report.

Distinct from *report the artifact, not the activity* (above): that rule is about a status being **truthful**
(artifact vs transcript), not about how many words carry an otherwise-truthful report. Distinct too from baking
a terse register into the agent definition (`multi-session-coordination.md`): that is the
**enforcement mechanism** that makes a compressed register durable across every spawned subagent; this is what
the register should be terse **about**.

**🚩 tell:** per-lane token spend that tracks the words in each handback rather than the work it describes — two
lanes doing the identical task costing differently for no difference in delivered artifact.

## Gate on free RAM and the swap trend — `load1` is not a reliable signal alone

`scripts/host_probe.py` is this section's own mechanized form, computed by one script instead of
re-derived from prose each session — swap-trend and free-RAM-as-veto below, the paired
load+CPU-idle brake, free disk against a measured per-lane footprint, the live-lane cap, and a
**gate-latency canary**: time a fixed cheap gate (e.g. the lint-only pre-commit tier on a clean
tree) and compare it with its recorded idle baseline (`--canary CMD --baseline-file F`); above
roughly 2x baseline, hold new heavy lanes regardless of what memory says — a machine can thrash on
contention the memory counters read straight through (the sharpening below, 84% free RAM while
nothing landed for hours). It prints one line, `SPAWN`, `HOLD <reason,...>`, or
`COULD_NOT_CHECK <what>`; a could-not-check never authorizes a spawn, same as a hold. `--selftest`
exercises every branch with injected readings, no real sleeping or OS calls.

The predicate with its probe commands, as `full-map.md` **Environment probe** routes it here:

- **Free RAM and the swap *trend* are the primary gate — `load1` is not a
  reliable term.** Spawn another heavy lane only while free RAM >15% AND swap
  is not actively climbing (`sysctl vm.swapusage` on macOS — read it twice, a
  beat apart, for the trend, not only the level). CPU idle >25% (`top -l 1 -n
  0` on macOS, `mpstat`/`top` elsewhere) is a useful **secondary**
  confirmation. `load1` (`sysctl -n vm.loadavg`/`uptime` vs. `nproc`/`sysctl -n
  hw.ncpu`) is at most a **weak corroborating signal, never the deciding
  term** — it counts disk-I/O-wait, not only CPU. Throttle the instant free RAM
  or the swap trend trips; the numbers are a rule of thumb to recalibrate on
  the host in front of you. Why `load1` misleads, the worked example, and the
  swap-blowout case: the paragraphs below.

`SKILL.md`'s environment probe states the act-on predicate — free RAM and the swap trend primary, CPU idle
secondary, `load1` a weak corroborating signal at most. This section is the mechanism and the worked example
behind it. Linux/macOS load averages count threads in uninterruptible I/O-wait, not only CPU-runnable ones —
"adding the uninterruptible state means that Linux load averages can increase due to a disk (or NFS) I/O
workload, not just CPU demand," with a worked example where "a heavily disk-bound system might be extremely
sluggish but only have a TASK_RUNNING [CPU-runnable] average of 0.1" (Gregg; source below). Observed directly on
a 14-core host: `load1` sat at 7 (comfortably under an 18-ish `cores × 1.3` ceiling) while CPU idle read 81% —
the elevated `load1` was disk I/O from several concurrent dependency installs, not CPU contention, so it neither
flagged the real problem nor stayed a trustworthy "all clear." The actual failure was memory: swap grew from
roughly 4 GB to 12 GB, driven by the many headless-browser processes a full local browser-suite lane boots
(CI-offload, below), and lanes died on their own timeout once swap pressure hit — independent of what `load1`
read at the time, and despite the host reporting a comfortable 86% free RAM shortly before.
**Corrected signal hierarchy:** free RAM and the **swap trend** (is it climbing, not just its current level) are
primary — spawn while free RAM stays above a working buffer (~15%) and swap is not actively growing; back off
the instant swap starts ballooning, before free RAM alone would look low. CPU idle is a useful secondary
confirmation of real headroom. **Do not gate on `load1` alone** — at most a weak corroborating signal, never the
deciding term, because it cannot distinguish CPU contention from disk I/O — but the asymmetry cuts the safe way:
a **sustained** elevated `load1` during a heavy-setup fan-out (many concurrent dependency installs or dev-server
boots saturating disk I/O) may **corroborate a back-off** even when RAM and swap read healthy — never a
*licence* to spawn, but a legitimate independent **cap on concurrent I/O-heavy setup**, since the RAM/swap gate
alone won't catch an I/O-bound crawl. The mirror failure is a **CPU-bound** lane type — parallel test suites,
compilation/builds, typecheck — that backs up the run queue rather than the disk: several at once drive `load1`
to a multiple of core count while free RAM sits well above its buffer and swap stays flat, so the memory gate
reads green throughout and the orchestrator keeps spawning into a box where every lane's wall-time is already
ballooning (observed: `load1` near 5× core count on a 14-core host while free RAM held above 50% and swap never
grew). Here the reading the header distrusts becomes reliable once **paired** — a `load1` sustained past core
count *together with CPU idle collapsing toward zero* is a CPU-contention signature disk-I/O-wait cannot fake,
so for a *known* CPU-heavy lane it is a legitimate spawn brake this gate would otherwise miss. Keep it
brake-only and lane-typed: back off a new CPU-heavy lane on that paired signal (high CPU idle stays confirmation
only, never a *licence* — RAM and the swap trend remain primary), and budget CPU-heavy concurrency
**separately** from RAM, since cheap read-only lanes (grep, an API call) tax neither. This is the
*size to the binding one* shape of the shared-quota ceiling below applied among the local resources — effective
heavy-lane concurrency is the **minimum** of RAM-headroom and CPU-headroom, not memory alone (the reverse of the
probe's *a machine can exhaust RAM before it exhausts CPU slots*: the bind runs both ways). Whatever the exact
predicate, **spawn one heavy lane at a time, re-sample after a settle window, then decide on the next** — never
compute a ceiling and dispatch straight up to it, and **leave a burst reserve even when the predicate says go**
— a later spiky lane (a browser gate, a dependency install, a test runner) must still fit without paging the box
into thrash.

**Sharpenings from a later thrash — 84% free RAM while swap sat ~76% consumed and nothing landed for hours.**
The ~15%-free-RAM floor above is a **veto, not a licence**: free RAM may *corroborate a stop* but must
**never authorize a spawn** — it is a post-mitigation number (paging, cache eviction, and compression have
already run), so under this kind of thrash, where dying lanes release RAM as the machine fails, it can read
healthiest exactly as delivery collapses. The swap trend (sampled twice for direction, as above) stays the
primary gate. Add to the probed predicate **free disk, worktree count, and live-lane count** — a fan-out sized
against memory alone dies of disk (worktree lifecycle, below). Size the disk term with real arithmetic, not a
guess: a per-heavy-lane disk footprint is roughly **build output + installed deps** (a fresh
`node_modules`-equivalent per worktree — the per-worktree install the dev-server-lane section below requires,
never a shared symlink), so the concurrent **build**-lane ceiling is roughly `disk_free ÷ per_lane_footprint`,
the same shape as the RAM/swap ceiling above applied to disk. Read an **ENOSPC** death on a heavy lane as what
it is — **a sizing bug, the spawn gate omitted disk** — never retry it blind as a flaky lane (the same asymmetry
as *a subagent's own crash report overrides a healthy probe*, below), and the same
*contention, not a defect, until reproduced at low concurrency* shape as the probe procedure above: a
fan-out-only ENOSPC is the resource cap, not the code.

- **Budget a per-commit gate's transient peak, not only resident disk.** A pre-commit hook that snapshots the
  tracked tree (`checkout-index`, a `cp -R` freshness rebuild) pays one full-tree copy **per run**, on top of the
  resident footprint above: `disk_free > N_concurrent_commits × hook_peak + reserve`, `hook_peak` **measured**
  from one real run, never guessed — 15 lanes committing at once against an unmeasured peak swung free disk from
  21 GiB to <500 MiB in minutes (#1126). Bound the peak at the source: clone instead of copy (`cp -c` on APFS,
  `--reflink=auto` on btrfs/xfs); exclude bytes no gate reads (e.g. committed binary evidence) from the snapshot
  — but **prove that first** (grep the gates and tests for the excluded pattern, then run them) or the exclusion
  silently blinds a gate that does read those bytes, a false green worse than the disk it saved. Cap the heavy
  commit tier itself at `disk_free ÷ hook_peak` **measured** concurrent commits with `serial_gate.py run --slots
  N` (below) rather than admitting every lane's commit at once.

And treat a collapse in observable **work rate** — lanes
not completing, tool calls timing out, nothing landing — as itself the resource signal, outranking any green
metric (distinct from the delivery-ratio drain above: that asks whether lanes convert to artifacts, this asks
whether the machine can still run them; a nothing-landing stretch trips both).

**A subagent's own crash / low-memory / OOM report is a first-class back-off trigger, even when the orchestrator's own probe reads fine.**
The probe above samples the orchestrator's outside view of the machine at an interval — necessarily steady-state
— and can straddle the exact moment several concurrent heavy lanes peak simultaneously (a build, a browser boot,
and a test run spiking RAM in the same window between two samples). A subagent that reports its own process was
OOM-killed, crashed on a low-memory / allocation-failure error, or self-observed swap thrash is not a flaky lane
to retry blind — it **is** the peak reading the periodic probe missed, filed from inside the spike instead of
around it. This is the same asymmetry as *free RAM is a veto, not a licence* above, one level out: a healthy
outside-view reading could not there authorize a spawn, and it cannot here overrule a worker's own inside-view
crash — back off concurrency immediately on the worker's report (the same swap-trend response above), and
re-probe before the next heavy lane, rather than waving off a real crash because the orchestrator's own check
said there was headroom.

## Cap the dev/build server's memory in the one shared start script, not only in CI

The gate above *detects* a memory blowout and backs off; this is the standing fix that keeps it from firing in
the first place — prevention, not detection, so keep both. A memory ceiling on a dev or build server
(`NODE_OPTIONS=--max-old-space-size`, a `ulimit -v`, a container/cgroup memory limit) is load-bearing only if
**every** invocation inherits it. The recurring failure is a ceiling pinned
**only in the CI job's environment**: CI's runner launches the server with the cap, stays under budget, and
reads green even on a runner with less RAM than the dev box — while the plain start command a lane actually
runs, the `dev`/`build` script in `package.json` and the "how to run this" docs, carries no ceiling at all. A
hand-run or agent-run lane invokes the documented `npm run dev` / `npm run build` uncapped, allocates without
bound, and under concurrency several such servers page the box and drive the swap trend straight into the
back-off gate above — the cap meant to prevent exactly that never touched the invocation that needed it, because
it lived in CI's env and not in the command the lane ran.

Fix: put the ceiling on the **one script every caller goes through** — bake it into the shared start/build
entrypoint itself (the `package.json` script body, or a committed wrapper both CI and humans call), never the CI
job's env block — and **size it to the intended per-machine concurrency** (per-lane budget ≈ usable RAM ÷ max
concurrent heavy lanes, with a burst reserve) so N lanes fit without paging. CI, a hand-run, and an agent lane
then inherit the *same* ceiling because they run the *same* script, and lowering concurrency stops being the
only lever, since each lane is now bounded on its own. Distinct from *CI-offload the heavy gate* (below), which
changes **where** the heavy suite runs to cut the local box's peak memory — a different lever, not a
per-invocation cap — and from *dev-server lanes need a copy, not a symlink* of the dependencies dir (below),
which is about install integrity, not a memory ceiling.

## A shared API/model quota is a fan-out ceiling no local probe can see — size to the binding one, not the machine

Everything above sizes fan-out to what one machine can *execute* — free RAM and the swap trend, disk, CPU. A
separate ceiling governs what the provider will *serve*: a shared **API or model quota** (requests and tokens
per rolling window, per account), and once fan-out is wide it is usually the **lower** of the two. It is
invisible to every probe above — the box can read abundantly healthy (high free RAM, flat swap, idle cores,
every gate green) while a growing fraction of lanes simultaneously fail to start or die seconds in on the
account's rate limit, because the quota is summed across every agent, sub-agent, and lane on the account and a
wide fan-out bursts past it. The effective parallelism ceiling is the **minimum** of local-resource headroom and
shared-quota headroom; **size to the binding one.** When the quota binds, extra lanes add no throughput — they
rate-limit-error and stall, wasting the tokens their partial work already spent (#830). This is the ceiling the
*token budget* in the fan-out-ETA section below already assumes exists.

- **A lane's retry on a shared-resource exhaustion (disk, a shared gate) must back off exponentially with
  jitter and give up after a bounded count — an un-backed-off retry loop is a load generator, not a fix.** ~20
  lanes each retrying a failed commit the instant space looked free consumed it before any single one finished,
  climbing to 25-30 concurrent hook processes on 0% idle CPU (#1127, following #1126's disk peak). A lane hands
  back `blocked on <resource>` after its bounded retries exhaust, never loops silently. Cap the heavy tier itself
  with `serial_gate.py run --slots N` (an N-slot semaphore over N kernel `flock`s — no stale-lock takeover,
  nothing to age out, the same primitive the module's 1-slot mutex already uses) rather than a home-grown
  stale-lock-reclaim scheme, sizing `N` to the **measured** ceiling above, not a fixed guess (too low
  under-utilizes a healthy machine, trading an ENOSPC storm for idle capacity). Pair it with `--retry K --backoff
  S --retry-on REGEX`: retries only a matching failure, bounded to `K+1` attempts, backing off exponentially with
  jitter — never a blanket retry-on-any-failure, which would retry a lane's genuine, unrelated test failure into
  the same storm. **The orchestrator's first move in the storm is to pause new retries/admissions, not reclaim
  caches** — caches are rarely the cause, and reclaiming them first burns time the pause would have used to let
  the transient peak drain.
- **A rate-limit error on a lane is a distinct signal from local overload — do not answer it with the RAM/swap back-off above.**
  The gates above catch the machine crawling; a lane erroring or failing to start on the provider's rate limit
  is the *shared* ceiling reporting itself from outside the box, and the local probe keeps reading healthy
  straight through it. It is the same asymmetry as *a subagent's own crash report overrides a healthy probe*
  directly above, one axis out — a real signal the orchestrator's own view cannot see — so read it as its own
  back-off trigger: **narrow** the fan-out or pace it, never retry the same width into the same wall, and never
  widen further just because RAM still looks free.
- **The quota sums across machines, so budget it globally.** This is the *peer caps sum on a shared host*
  failure (`multi-session-coordination.md`'s aggregate reservation) one level out: RAM sums across peers on one
  host, but the quota sums across every machine on the **account**, so two machines each "within local limits"
  still add onto one ceiling — budget it against a shared, account-wide counter or coordination channel, never
  each machine's own headroom alone.
- **When the shared tier is capped, switch lanes or pace — don't spawn lanes that will error.** Move work to a
  **non-capped model tier** (model tier is already a per-lane cost-and-concurrency lever in this file; here it
  is also a quota lever), pace new lanes to the quota's refill rather than assuming a remembered reset window
  that may no longer hold, or keep a **no-quota fallback lane** productive on local, API-free work —
  version-control merges, branch/worktree hygiene, deterministic gates — all of which keep delivering while the
  token budget is exhausted. Prefer **fewer, higher-yield lanes** over many thin ones, and
  **checkpoint partial work to a durable artifact** (a pushed branch, a saved file) before a lane can die, so a
  rate-limit stop is resumable rather than tokens spent for zero delivery.
- **Respawn by priority, not wholesale — and never move the fleet onto the orchestrator's own tier.** A quota
  death (#1132) takes every lane on the exhausted model down within minutes, mid-commit and mid-PR; respawning
  all of them onto the next tier up can exhaust *that* one too, especially when the orchestrator itself already
  depends on it — the same single-point-of-failure shape, one tier up. Respawn in priority order instead: P0 /
  user-facing lanes go to the next capable tier; mechanical finishing (a PR-body fix, a changelog fragment, a
  rerun) goes to the cheapest tier; everything else waits for the reset. Brief a respawned lane from its
  worktree (`git status`, the unpushed log) plus its queue entry in the orchestrator's own state file, never only
  from the dead lane's context — the durable-artifact checkpoint above is what makes that briefing possible.

- **A first limit error is SUSPECTED, not CONFIRMED — one delayed probe before any teardown (#1166).** An
  orchestrator that sees several lanes fail on a rate limit and immediately declares a multi-day quota stop,
  deletes its recurring schedules, writes resume ledgers, and tells a peer session to stop dispatching has
  acted on a snapshot (the *remembered constraint-state* error below, at its most destructive): a short-lived
  throttle and a multi-day cap look identical at the moment of the first error, and only one of them justifies
  the teardown. Before any of it — deleting a schedule, stopping a lane, broadcasting a stop to peers — check
  two cheap signals: (1) is any lane still completing tool calls (`lane_liveness.py`'s ALIVE/QUIET, never its
  own kill verdict, applied to whether the *fleet*, not one lane, is still producing); (2) does one minimal
  probe agent answer, about **10 minutes** after the first error (a documented default, not a hard floor —
  tune it to the provider's own observed reset granularity). Declare the long stop only when **both** fail:
  no lane progress **and** the probe itself errors. Probe **once**, not on a loop — a minimal probe agent
  still loads the full agent context (on the order of tens of thousands of tokens), so polling it repeatedly
  spends the same tokens the stop was meant to conserve. Write the resume ledgers either way; they are cheap
  and reversible, unlike the teardown. Never delete a schedule or tell a peer to stop on a suspicion alone —
  that is the destructive, shared-state action principle 9 already gates, and the *is this lane dead* recheck
  below draws the identical distinction one level down (a lane) that this draws one level up (the fleet).

**🚩 tell:** an orchestrator widening lane count because the local probe reads healthy — free RAM, idle cores,
flat swap — while a rising fraction of lanes fail to start or die seconds in; the fan-out was sized to the
machine when the binding ceiling was the shared quota all along. Track the rate-limit-error rate per N lanes
dispatched — nonzero under healthy local resources is the proof that fan-out is gated on the wrong ceiling.
A second tell, same family: schedules deleted and peers told to stop within minutes of a first rate-limit
error, with no record of the two-signal check above — the accompanying **metric** is wall-clock and token
cost spent rebuilding schedules and restarting lanes that were still completing when the stop fired.

## A remembered constraint-state is a guess, not a current signal — recheck it before you keep acting on it

The quota section immediately above ends on pacing new lanes "to the quota's refill rather than assuming a
remembered reset window that may no longer hold." This is the mechanism behind that clause, generalized: once
any shared constraint has **tripped** — a model/API quota returning a rate-limit error with a stated reset, a
saturated pool — the state you recorded at the moment it tripped is a **snapshot, not a live reading**, and
continuing to act on the snapshot is acting on a guess. Two shapes of that error, one of them destructive.

- **Don't hold longer than the constraint actually binds.** A rate-limit error's "resets at HH:MM" is an
  **upper bound, not a step function**: a rolling/partial window restores throughput continuously and commonly
  *before* the advertised time, and a different model tier may not be capped at all. An orchestrator that
  records the stated reset and idles every affected lane until that clock sits self-throttled on capacity that
  has already returned — indistinguishable from the outside from a slow or stuck run, wasting the exact resource
  it is waiting on. The reset time is not observable; the limit's current state **is**. Back off with a schedule
  that **retries a real check**, not one that sleeps until a remembered clock: at intervals issue
  **one cheap real unit of the throttled work** (a single small request, one lane) and let its success or
  failure — ground truth — decide, resuming the instant a check passes. On recovery **ramp, don't re-burst** —
  the thing that tripped the limit was concurrency, so resume at a fraction and climb while watching for
  re-throttle rather than relaunching the full fleet into the same wall (the
  *narrow, never retry the same width into the same wall* response and the *spawn one, re-sample, then decide*
  discipline of the sections above, applied to a quota's recovery, not restated). Keep the
  **no-quota fallback lane** the quota section already requires productive throughout, so a stale hold never
  means zero delivery. Same shape as the *cooldown / skip-set with periodic re-evaluation* of the
  head-of-line-starvation section below — a block is re-evaluated because it may have cleared, never treated as
  permanent — at the capacity-ceiling grain rather than the queue-item one.

- **Distinguish "I am blocked" from "I remember being blocked."** A status of "paused until <time>" that cannot
  say when the limit was **last verified** is reporting the snapshot as if it were current. Carry a
  **last-checked timestamp** on any held state so a supervisor can tell a real, freshly-observed block from a
  stale assumption — the *report the artifact, not the activity* discipline above applied to a hold, whose
  artifact is a recent check result, not a remembered clock.

- **Don't conclude a lane is dead from an indirect signal either — that is the destructive twin.** "No commit
  yet" / "gone quiet for a while" is the *absence* of a durable artifact, and absence is not evidence: the lane
  may be mid-work with results uncommitted, and killing it discards that uncommitted work irreversibly (a
  destructive, shared-state action — principle 9). The recheck-before-you-conclude discipline is identical to
  the hold above, and its *how* is already stated: judge liveness by a **positive** actual-product signal (a
  live process, an owned port/PID, a ping it answers), never an indirect one, and treat transcript-only
  observability as **`UNVERIFIED`, not dead** (the *transcript is not a liveness signal* rule below; and a stop
  of a lane's turn is not teardown, a "cleaned up" claim unverified until checked, #777 — neither restated
  here). The one thing those rules don't say: **artifact-absence cuts two ways and only one is a licence.** The
  WIP-cap rule above reads "no landed artifact" as *produced nothing yet* — grounds to
  **stop admitting new lanes** and to **refuse to count the work delivered**; it is **never** grounds to
  **terminate** the lane that lacks one. Draining admission on an empty delivery ratio and killing a
  live-but-quiet lane are opposite actions on the same signal — the first reversible and correct, the second
  destructive and gated on a positive liveness signal first.

The unifying error under both: confusing a **remembered** constraint-state with a **current** one. A held quota
and a quiet lane are each cheap to conclude and easy to leave concluded; the fix in each is one real check — a
probe unit of work, a positive liveness signal — before continuing to act on the memory.

**🚩 tell:** an orchestrator reporting "paused until <reset>" across a full window with no record of having
rechecked capacity since it tripped; or one that kills a lane it labeled "stuck" on no-commit / gone-quiet
alone, no positive liveness signal, discarding uncommitted work. **Metric:** the gap between when capacity
actually returned and when the run resumed (a persistently large gap means it is honoring remembered resets
instead of rechecking), and re-throttle events on resume (nonzero means it re-burst instead of ramping).

## A worktree is a resource with a lifecycle — creation without teardown leaks it

Worktree-per-lane is the right isolation, but a worktree is a **resource with a lifecycle**, and nothing in the
fan-out pattern ends it. The failure is
**disk exhaustion that halts every lane at once — including the integration lane that would have landed the work**
— arriving without warning after a per-lane-creates, nobody-destroys run accumulates hundreds of worktrees and
tens of GB. Checkout and status degrade as the registry grows; stale worktrees masquerade as in-flight work (an
entry in `worktree list` proves only that something *once* ran — cross-check a real liveness signal, the
transcript-is-not-liveness rule below); and worktree-held branches escape the usual merged-branch cleanup.

- **Teardown is part of the lane contract, stated at spawn** — on success, after the artifact is pushed, the
  lane removes its worktree; on failure/abandonment it removes the worktree only after
  **capturing any uncommitted work** (the non-destructive rule below — committed work survives on the branch
  ref, but truly-uncommitted work is lost to `git worktree remove`). A lane that cannot guarantee teardown runs
  under a supervisor that does.
- **Stopping a lane's turn is not teardown — and a "cleaned up" claim is unverified until checked.** Ending a
  lane's *turn* (a harness stop/kill — e.g. `TaskStop` — or the lane simply returning) frees the *unit*, not its
  **worktree**: the checkout survives on disk with its branch still attached. So **redispatching** the same
  issue is two required sub-steps — stop the old lane **and** teardown-or-adopt its worktree — never one; skip
  the second and each redispatch generation strands another orphan (the leak this section opens with). And a
  lane (or the orchestrator) reporting "cleaned up / worktree reclaimed" is a **claim, not a fact** — verify it
  against actual state (`git worktree list`, the directory's existence) before trusting it: the
  *report the artifact, not the activity* rule (above) applied to teardown, since a narrated reap that never ran
  leaks silently. When the redispatch is the orchestrator's **own** successive generations of one issue (not a
  peer's stalled lane), the *ownership map blocks a dual write, not dual work* rule below still governs each
  generation — **adopt-and-re-verify** the prior generation's worktree/branch, don't spawn a fresh one beside it
  (and never trust its state blind). **🚩 tell:** a redispatch cadence where `git worktree list` grows by one
  each cycle while the transcript says "cleaned up."
- **The orchestrator owns garbage collection**, because lanes die in ways that skip their own cleanup — but GC
  is **advisory and approval-gated, never an autonomous destructive sweep** (the same
  confirm-before-shared-state bar as any delete). At an interval it **proposes** removals with the exact command
  — registry entries whose directory is gone; worktrees whose branch is merged, whose PR is closed, or idle past
  a threshold **and** holding no uncommitted changes — and executes only on explicit approval.
- **The orchestrator also owns reaping orphaned heavy processes, held to the same bar.** A lane that dies
  mid-step — killed, crashed, or simply abandoned — can skip its own cleanup, so its child processes (a dev
  server, a browser, a build) outlive it as orphans. *Kill a lane-owned helper the moment its step ends* (below)
  is what a **live** lane does for itself; this is the **backstop** for when that didn't fire. Sweeping these
  orphans is **advisory and approval-gated**, never an autonomous kill — the identical
  propose-with-the-exact-command, execute-only-on-approval bar the worktree GC above already sets, not a
  separate, looser one for processes. Termination mechanics (own a process group, terminate by pgid) stay in
  `deep-code-review`'s `concurrency-shared-state.md`; this bullet is only about **whose job the sweep is** and
  **what bar it clears**, not how a kill is executed.
- **Fully pushed is its own reclaim signal, independent of merge state** — once a lane has reported done *and*
  local `HEAD` equals `origin/<branch>` with a clean tree, the worktree is redundant whether or not its PR has
  merged (the branch lives durably on the remote; re-checkout later if needed). Add it to the candidate set
  **unconditioned on idle-time** — the case a human/permission-gated merge queue needs — but pair it with a
  positive liveness check (the transcript-is-not-liveness rule below): pushed+clean alone is not proof a lane
  has stopped writing, since a lane that pushes mid-work and keeps going looks identical.
- **The work-product liveness signals go silent in the post-push window, so their absence is not proof the lane has exited.**
  The positive liveness check the rule above requires normally reads a lane's *product* — a fresh work-tree diff
  or a new commit (the transcript-is-not-liveness rule below). Both are **structurally dead** the moment a lane
  is done pushing: a git-final lane emits no further commit and its tree is clean by definition. A reaper
  applying both rules faithfully then hits a **false negative** — it sees no new git activity, reads the lane as
  stopped, and deletes the checkout — while the lane is in fact still live doing **post-push work**: composing
  its hand-back, waiting on its own CI to go green before it reports, tearing down helpers, or waiting on a
  review. "No new work-product" equals "process gone" everywhere *except* this window — the exact state this
  reclaim rule governs. So here the check must be **process-level**, not artifact-level: a lane-held lockfile
  still in the worktree, the lane still in the live-task registry, an owned PID, or a ping it answers. A
  positive signal the **process** has ended — never the silence of a signal this window is guaranteed to kill —
  is the precondition that lets a pushed worktree even become a removal candidate; the advisory, approval-gated
  sweep above still executes the delete. Delete it on the pushed signal alone and the shell dies mid-step: the
  hand-back never arrives, yet the objective logs as done-and-reclaimed while the slot spins on a dead sandbox.
  **The lane's own half:** a lane that finds its checkout gone treats it as **terminal** — the work is already
  safe on the remote — and hands back at once naming the pushed PR, never retrying shell access on a dead
  sandbox (the inverse of the *stopping a lane's turn is not teardown* rule above — there the checkout outlives
  a stopped lane; here it dies under a live one). **🚩 tell:** a reaper that deletes a worktree the instant its
  branch reads complete on the remote, with no process-level check.
- **GC is non-destructive toward uncommitted work** — a candidate holding uncommitted changes is refused (or its
  diff archived and reported first). Reclaiming space must never become the mechanism that loses a lane's only
  copy of its work.
- **Scratch is a probed resource** — free disk and worktree count are ceilings the spawn probe enforces (the
  swap-trend section above); this section keeps that term from going red, it does not re-specify how to read it.
  The per-lane disk arithmetic and the ENOSPC-is-a-sizing-bug reading live in that section, not here.

---

## Host-priority classes: train > pregate > lane — lanes yield cores while a train's test stage runs

On one capacity-bound host three kinds of work compete for the same cores, and they are not equal. Rank them by how many
other PRs a minute of their wall-clock holds up:

1. **train** — the merge-train verify of one union (`merge_train.py verify`). One red or slow run blocks every member, so it
   is the top class.
2. **pregate** — a single PR's pre-push or pre-merge gate. It blocks one PR.
3. **lane** — an agent lane's own builds and test runs. It blocks only itself, and it can be re-run.

Rule: **while a train's test stage runs, lanes yield cores.** Do not start a new lane's heavy build or test run (pregate may
continue, `nice`d), and `nice -n 19` the heavy children of lanes already running. A starved train test stage times out or
flakes, and that red costs a bisect over the whole batch, which is far more than the seconds a lane waited. Lanes resume when
the train's test stage ends. This is the CPU half of the cycle-time rule above; the RAM and swap gates above still apply to all
three classes.

A red train is first re-run **alone and at low load** (`merge_train.py verify --rerun-cmd`: only the failing checks or specs,
`nice -n 19`, `PERUN_LOW_LOAD=1`). A pass there is a load flake: the batch lands and the flake is logged. Only a red that
reproduces is bisected. Measure it with `landing_watchdog.py check`: a low yield (PRs per landed train) or merges per hour below
target (policy `train_yield_floor`, `merges_per_hour_target`) says trains are being lost to reds or starved.
