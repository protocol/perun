# Fast agentic delivery — worktree isolation

Read this when: isolating a lane's worktree: stale refs, `git stash`, out-of-tree scratch, an assignment path, a worktree's own gate firing on a file it does not own, worktree sprawl or cleanup, or sparse-excluding committed evidence.
Part of the `fast-agentic-delivery.md` ledger (index and sources there); an "above"/"below" pointer to a missing section is in `merge-queue-worktrees.md` or `red-gate-triage.md`.

---

## A worktree's own gate can fire on a file it does not own

A definitions- or content-only change can rebuild a generated artifact that is *mirrored* into a directory owned
by a different toolchain (for example, a compiled data file synced into an application directory whose own
pre-commit gate fires on any staged path under it). In a **fresh** isolated worktree — before that toolchain's
own install step has run — the mirrored file alone can trip that gate and fail closed, even though the change
never touched that toolchain's code. Two portable fixes, either sufficient: (a) provision the *whole* worktree's
toolchain (run every subtree's own install step) before the first commit, even when the change looks confined to
one subtree; or (b) scope a definitions/content-only lane to skip staging the generated mirror at all, letting a
downstream build step regenerate it. This is a **provisioning gap, not a defect in either gate** — each gate
does exactly what it is supposed to; the worktree was simply not fully set up for the one it tripped.

## An isolation worktree inherits the parent clone's stale refs — verify freshness, or query the server

A worktree branched off the local clone's **remote-tracking ref** runs whatever version of the build / CI /
merge scripts that ref points at. If the clone has not fetched recently, the worktree silently runs **stale**
scripts and produces **false** results — a merge-preflight that still requires a CI job the current workflow has
since **removed** will refuse every PR with "required job never ran," while the fixed script on the true remote
HEAD passes. It looks like a live gate bug; it is a stale checkout, and it can flip a diagnosis back and forth.
Two fixes: (1) **fetch the base ref immediately before creating the worktree** (or hard-reset / rebase the
worktree onto the freshly-fetched remote ref before running any script); (2) for any check that must reflect
**current** remote / CI state — merge gates, required-check verification —
**query the forge/server API for the actual check-runs** — immune to local staleness — rather than trusting a
local script copy (the same "trusted evidence is a forge run pinned to the reviewed SHA" discipline in
`deep-code-review`'s `merge-operations.md`). The narrowest case of this is a merge-train daemon racing **itself**:
right after its own merge, poll the remote target until it observably contains the SHA it just merged (bounded
retries with backoff, hard-stop-and-retry-next-tick on a fetch failure) before collecting the next union, rather
than trusting a local/cached ref that has not yet observed its own write (#1128). **🚩** an agent that infers
"the gate is broken" from a worktree without confirming its base ref is current; a merge or CI decision made
from a local script in a worktree of unknown freshness.

## Worktree sprawl outruns manual cleanup — one prune tool, sized to open PRs plus live lanes

The GC and orphaned-process sweeps in `fanout-host-sizing.md` (*The orchestrator owns garbage collection*, *The
orchestrator also owns reaping orphaned heavy processes* — both **advisory and approval-gated**, never an
autonomous destructive sweep) are the right shape; this is what trips when nothing runs them regularly. Each new
worktree pays a **full dependency install** (never a symlinked shared tree — `dev-env-ownership.md`'s
*Boot-the-dev-server lanes need a copy, not a symlink*) plus its own build artifacts, so an unattended fan-out
that creates worktrees per lane and never sweeps the finished ones accumulates disk fast. One observed run: 174
worktrees against 33 open PRs — roughly 94% orphaned — consuming roughly 400GB with the host at 80% disk.

- **One worktree tool, not ad hoc `git worktree add`/`rm` per lane** (`scripts/lane_worktree.sh`, below): sparse-checkout the artifact directories a
  lane doesn't need in full, and copy-on-write the dependency tree when the target's lockfile already matches a
  sibling's (cheaper than a fresh install, still a real copy — never the symlink the dev-env rule above forbids).
- **Prune through the existing approval-gated reap path** — merged branch, clean or allowlisted untracked state,
  idle past a threshold, and **not a live process's cwd** (the process-level liveness check
  `fanout-host-sizing.md`'s *work-product liveness signals go silent in the post-push window* already requires
  before a delete) — propose-with-the-exact-command, execute-only-on-approval, the same bar that section already
  sets; this section adds no new authority to delete.
- **Size the pass, then measure it:** **total worktrees** should sit at or below **open PRs + live lanes** — a
  standing ratio, not a one-time cleanup, since sprawl reaccumulates at the same rate a fan-out creates
  worktrees. **Orphaned** worktrees (present, matching none of the above) are a separate count and target
  **≈ 0 after each merge train** — any nonzero orphan count past that point means the prune pass didn't run or
  missed something, not a tolerable steady state.

## Keep lane worktrees outside the watched repo tree, and reap them at stop

Lane worktrees created inside the repo dir get scanned by every file watcher on the host: one host with 129 lane
worktrees (49GB) under the repo kept fseventsd at 158% CPU, because "reap at hand-back" in a brief is only a request.
Default root: `${XDG_CACHE_HOME:-~/.cache}/perun-wt/<repo>` (override `PERUN_WT_ROOT`). Create lanes with
`scripts/lane_worktree.sh <name> [base]` (branch `lane/<name>`, one path segment: no `/` or `..`; prints the path; writes a
marker `<git-dir>/perun-lane` with branch, repo, path and optional `PERUN_AGENT_ID`). The SubagentStop hook
`handback_cap.py` then runs `git worktree remove` (never `--force`) and `branch -d` for the stopping lane, but only if
the marker matches the tree and repo (and the agent, when the marker names one), the tree is strictly under the lane root
(a root of `/`, `$HOME` or an ancestor of the repo is refused), HEAD is the `lane/` branch and equals its own upstream, the
tree is clean **including ignored files** (`.env`, local DBs, `node_modules`), and no test or build runs from it. Unmarked
trees (a parent's, a sibling's, `.claude/worktrees`, hand-made) are never touched; a marked tree it cannot reap, or a stop
released after repeated blocks, is reported on stderr and left for the approval-gated sweep above (`PERUN_REAP_WORKTREE=0`
turns the reaper off). Limit: a marker without an agent id proves a lane tree, not which agent owns it; export
`PERUN_AGENT_ID` when creating it to bind the owner. `perun_doctor.py` has "lane worktrees in repo" and "lane worktrees out of tree" rows (count and size, `du` capped at 30s):
WARN above 20 trees or 20GB (`PERUN_WT_MAX`, `PERUN_WT_MAX_GB`).

## Committed UX evidence bloats every checkout — sparse-exclude it, and prune it out of HEAD

Screenshot/recording evidence attached to a PR review is easy to commit straight into the tree it documents;
at scale (thousands of PNGs, low single-digit GB) every worktree and lane then checks that folder out on
creation — slow worktree creation, disk churn, and, observed once, a file watcher pegged at 100% CPU
walking it. Give every worktree a sparse checkout that excludes the evidence folder by default (a lane that
genuinely needs to look at the evidence adds it back explicitly), and prune evidence older than roughly a
week out of **HEAD** — git history still has it; nothing needs it live in every checkout going forward.

**A harness-isolated worktree doesn't inherit the repo's own sparse-checkout script — it needs the same
discipline applied explicitly, or it grows past the ordinary worktree-sprawl numbers above.** A per-subagent
"isolated worktree" mode that clones fresh rather than reusing the fleet's worktree tooling skipped the
sparse-checkout step above in one observed run and grew to roughly 220GB. Brief every isolated-worktree lane
to run the project's own sparse-checkout script on creation, not a bare clone, and remove the worktree at
hand-back rather than leaving it for the periodic prune pass to find — or, short of that, add the same
cleanup sweep this section already prescribes (remove if clean and its `HEAD` is reachable from a remote) to
the isolation harness's own lifecycle, not only to the fleet's worktrees.

## Out-of-tree shared scratch crosses commit metadata — worktree-per-lane doesn't cover it

Concurrent write-lanes that each generate per-lane content — a commit-message file, a plan/notes file, a
screenshots / evidence dir — and write it to the **same hardcoded path in a shared temp/scratch directory**
collide: lane B overwrites lane A's file before lane A consumes it, so lane A commits with **B's message**
(`git commit -F <shared-path>`) or attaches the wrong note. Each branch's **code diff is correct**; only the
**metadata** is crossed — and metadata crossing is **invisible to a diff-scoped review**, which reads the tree,
not the message the tree ships under. The usual mitigations miss it: a git **worktree per lane** isolates the
branch, index, and deps, but a scratch path in a shared temp dir is **not part of any worktree**, and the
collision travels through `git commit -F <path>`, so "stage explicit paths, never `git add -A`" doesn't reach it
either.

- **Give every lane a unique scratch path** (suffix by lane id / worktree / PID), or keep per-lane content
  **inside the lane's own worktree**.
- **Verify metadata ownership, not just the diff** — before finalizing a lane, confirm the committed
  message/note belongs to *that* lane.
- **🚩 grep:** `git commit -F <path>` / `--file=<path>` where `<path>` is **fixed across lanes** (no lane-unique
  component), or multiple lanes referencing one hardcoded scratch/temp path for per-lane content.

Same root cause as `deep-code-review`'s `concurrency-shared-state.md` (two writers, one path) but where its
mitigations don't reach: **out-of-tree** scratch, and the corrupted thing is **commit metadata** a diff review
never sees.

## A worktree does not isolate repo-global refs — never bare `git stash` across lanes

A `git worktree` per lane isolates HEAD, the index, the working tree, and (with a copied deps dir)
`node_modules` — but **not** repo-global plumbing that lives in the one shared `.git`. `refs/stash` is the sharp
case: **`git stash` is a single repo-wide stack, not per-worktree**, so lane B's `stash push` and later `pop`
can consume or reorder an entry lane A pushed — silent cross-lane WIP loss, and the popped changes may not even
apply cleanly onto B's tree. (Other repo-global state — branches under `refs/`, config — shares the hazard; the
stash is just the one lanes reach for reflexively.) Never run a bare `stash push` / `stash pop` in a lane that
runs concurrently with siblings off the same repo: **commit-then-reset** onto the lane's own branch, use a
**second worktree** for throwaway state, or — if you must stash — use `git stash create` (it returns a
**dangling commit SHA** and never touches the shared `refs/stash` stack), record that SHA in a lane-private
file, and reapply with `git stash apply <sha>`. Avoid bare `stash push`/`pop` and `stash@{N}` **by index**
entirely: the index is positional on the shared stack, so a sibling's push between your lookup and your pop
shifts it and you pop the wrong entry — the same race, one level down. Complements the foreign-WIP rule below
(*don't stash another lane's uncommitted work*) with the deeper reason: the stash **stack itself** is shared, so
even your own push/pop is unsafe under concurrency.

## A worktree assignment is a path, not an adjective — an integrator on a shared branch detaches

Brief N lanes with *"work in an isolated worktree off `<branch>`"* and the phrase splits two ways: one lane
creates a fresh worktree, another reads it as *the* worktree where `<branch>` is already checked out and writes
straight into that tree. They never collide on a file — their file sets are disjoint — they collide on the
**tree**. The occupied tree then carries a second lane's *uncommitted* work, and the first lane's own gate trips
on it: a fully verified merge is blocked by a foreign half-written test file it must not touch. A git-diff
review sees nothing — the foreign edits are unstaged, so the committing lane's own diff is clean; the failure
surfaces only as a confusing unrelated test failure. And "just make your own worktree" fails for exactly the
lane that most needs one: `git worktree add <path> <branch>` **refuses a branch already checked out elsewhere**
(`fatal: '<branch>' is already used by worktree at …`), which is precisely the integrator's situation.

The topology is fixed: N lanes plus one integrator all want a checkout of the *same* integration branch — N+1
agents, one branch. State it explicitly, one line per brief:

- **Name the exact path; "isolated" is not an instruction.** The brief gives the path the lane creates
  (`<scratch>/wt-<lane>`), and the lane writes **only** under it. "An isolated worktree off X" is a hope; a path
  is an assignment.
- **The integrator folds in on a *detached* worktree.** `git worktree add --detach <path> <branch>` — detach at
  the **local** `<branch>` tip, not `origin/<branch>`: detaching does not occupy the ref, so it succeeds even
  though the branch is checked out elsewhere, and it lands on the verified local tip; `origin/<branch>` bases
  off the **stale** remote tip (dropping the merge you just verified) and does not exist at all for a local-only
  integration branch. Then merge the finished lane, verify, publish, and remove the worktree. A detached
  checkout is immune to the same-branch refusal above and cannot be squatted by a lane that believes it owns
  `<branch>`'s tree. How the result is *published* is a separate choice — a direct
  `git push origin HEAD:<branch>` from the detached tree, or a PR from the merged result — under whatever
  publish gate the project already applies (a push to a shared branch is itself an owner-approved action); the
  detach is what makes the *integration step* itself collision-proof either way.
- **Verify tree ownership before the first write.** `git status --short` in the target tree: if it shows changes
  the lane did not make, the tree is **occupied** — stop and report, do not write into it. Foreign dirt is an
  occupancy signal, not noise.
- **A gate failing on a file the lane never touched is the environment, not the code.** This is the collision
  twin of *a worktree's own gate can fire on a file it does not own* above: there the unowned file is a mirrored
  artifact, here it is another lane's uncommitted WIP — either way, re-run the gate in a clean or detached tree
  to tell an environment fault from a code fault before chasing a bug that does not exist.
- **Never resolve it by stashing.** `git stash` on another lane's uncommitted work removes it from that lane's
  tree silently and is unrecoverable from the lane's point of view — a data-loss fix for a coordination bug.
  Reassign the path instead.
- **A `git worktree add` failure is fail-loud, never a silent degrade to the shared tree.** Whatever the cause —
  the branch-in-use refusal above, disk, permissions, an unsupported git version — a write-lane that catches the
  error and keeps going by writing straight into the shared/main checkout trades an unannounced collision with the
  owner's or a sibling lane's tree for the honest option: report **BLOCKED: worktree creation failed — `<error>`**
  and stop; never retry into the shared tree as a fallback. If a step genuinely cannot avoid the shared tree, `git
  status --short` it first (as above): foreign lane WIP is still never stashed (the rule just above); the **owner's
  own** uncommitted work is preserved first with `git stash create` (the dangling-SHA, shared-stack-safe mechanic
  above), never a bare `stash push`, rather than left to be silently overwritten.
