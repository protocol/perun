# Fast agentic delivery: concurrency, scheduling & merge cadence

Read this when: sizing a heavy-lane fan-out on a shared machine (the full environment-probe procedure and the
fan-out tiers live here), choosing between a merge cascade and a merge train for a queue of already-green PRs,
diagnosing a fleet-wide red that no single diff caused, or reviewing (domain K/S in the sibling
`deep-code-review` skill) whether a target project's own fleet-scale CI/merge behavior holds up under N-agent
load. `SKILL.md` holds the act-on predicate (free RAM + swap trend), the Conductor's event-driven rhythm and
drift rule, gate-epistemology principles 3 and 6, and the worktree/occupancy rules; this file holds the
procedure, mechanism, and worked examples behind them, each section opening with a one-line anchor to the rule
it expands.

---

## Index — seven themed files (load only the trigger's)

- Fan-out sizing, the WIP cap, cycle-time, handback verbosity as a cost lever, the RAM/swap/disk/CPU probe, a
  dev-server memory cap, a shared quota ceiling, a remembered constraint-state, worktree lifecycle and teardown →
  `fanout-host-sizing.md`
- Queue sweeps, head-of-line starvation, auto-merge scoping, permission asymmetries, cascade and single seat,
  ready-flips, train landers, review gate, CI-offload, draft-gated checks → `merge-queue-worktrees.md`
- Red unions, fleet-wide advisories, flaky/contended/absent checks, landed flaky-fix propagation → `red-gate-triage.md`
- Stale refs, stash, scratch, assignment paths, worktree sprawl → `worktree-isolation.md`
- Delegating by measured number, foreground verification, finalize and done-contracts, stranded PRs, hard-to-write
  tests, liveness and duplicate dispatch, plugin forks, self-polling lanes, timeboxed briefs, release verification,
  `Verify:` lines, fan-out joins, relaying findings, soft prohibitions, context-inheriting forks → `verification-handback.md`
- Dev-server dependency copies, serve-vs-commit trees, hard-reset sync loops, generator re-stamps, absolute-count
  ratchets, live-feedback bursts, requirement queues, ownership maps, contention probes, the local-stack procedure →
  `dev-env-ownership.md`
- Tracker auto-close and issue closing, PR-body markers, fan-out ETAs, the unattended work loop, go-faster signals,
  monitors, the add-only loop set, degradation workarounds, research vs delivery, terminus, surface enumeration →
  `unattended-trackers.md`

Sections keep their original order; the sources below back all seven files.

---

## Sources

Fetched fresh for this file (entries 1–5 verified 2026-09-09; entry 6, 2026-09-18):

1. Kanban University, *Kanban Guide*. A WIP limit's purpose, verbatim: "balance utilization and still ensure the
   flow of work"; "limiting the work that is allowed to enter the system is an important key to reducing delay
   and context switching"; a WIP limit as "an enabling constraint."
   https://kanban.university/kanban-guide/
2. Google Engineering Practices, *Small CLs*. "100 lines is usually a reasonable size for a CL, and 1000 lines
   is usually too large"; small changes are reviewed more quickly and thoroughly, introduce fewer bugs, and
   simplify rollback.
   https://google.github.io/eng-practices/review/developer/small-cls.html
3. Wikipedia, *Blast radius* (computing sense). "The impact that a security breach of one single component of an
   application could have on the overall composite application"; a sibling technical-debt sense naming
   lockstep-edit surfaces directly.
   https://en.wikipedia.org/wiki/Blast_radius
4. GitLab Docs, *Merge trains*. "Two merge requests can each pass their own pipeline, but their combined changes
   can still conflict"; each queued pipeline runs combined with the target branch **and** every earlier queued
   change.
   https://docs.gitlab.com/ci/pipelines/merge_trains/
5. Brendan Gregg, *Linux Load Averages: Solving the Mystery*. "Adding the uninterruptible state means that Linux
   load averages can increase due to a disk (or NFS) I/O workload, not just CPU demand"; worked example, "a
   heavily disk-bound system might be extremely sluggish but only have a TASK_RUNNING average of 0.1" — the
   basis for "don't gate on `load1` alone" in `fanout-host-sizing.md`.
   https://www.brendangregg.com/blog/2017-08-08/linux-load-averages.html
6. GitHub Docs, *Linking a pull request to an issue*. Auto-close is default-branch-scoped: "When you merge a
   linked pull request into the **default branch** of a repository, its linked issue is automatically closed";
   the `Closes` / `Fixes` / `Resolves #N` keywords are "interpreted only when the pull request targets the
   repository's default branch."
   https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue

## Cross-references

- `SKILL.md` **Environment probe** — states the act-on predicate (free RAM + swap trend); this file holds the
  full probe procedure and the load-average mechanism.
- `SKILL.md` **Conductor operating rhythm** — the event-driven attention model this file's queue-sweep and
  fan-out-sizing sections extend.
- `SKILL.md` **Gate epistemology**, principles 3 and 6 — the two existing cases this file adds a third case to,
  and the union-proof rule the cascade section stays subordinate to.
- `SKILL.md` **Worktrees and occupancy** / **Local environment (own it)** — where the worktree-provisioning
  gotcha's two fixes belong in practice.
- `deep-code-review`'s `release-engineering.md` — the review-time audit of a *target's* release pipeline
  (feature flags, canary, DORA); this file is the authoring-time counterpart for the project's own fleet, not a
  target's.
- `deep-code-review`'s `branch-and-merge-hygiene.md` — the grep-the-tree-not-the-claim check ("B included A")
  that the verify-first-before-laning section reuses pre-laning, and the evidence-before-a-destructive-close
  discipline.
- `deep-code-review`'s `merge-operations.md` — the mergeable-is-a-snapshot /
  freeze-the-merge-sweep-while-a-resolver-runs rule a fleet coordinator applies when batching merges; and the
  self-reported-evidence-is-not-a-trusted-control rule plus the co-evolve-a-body-gate-with-its-producers rule
  that this file's `Verify:`-line section reuses.
- `docs/standards-index.md` — fetch dates and full citations for the six sources above.
