# Branches, merges & open-work triage

Read this on a **FULL / repo-level review** of a git repo with more than one branch, or whenever the request
names branch cleanup or open work — "clean up the branches", "what's still open", "should this merge to main
or develop?", "does this need a PR?", "which branches are stale / already merged / safe to delete?". **N/A by
scope on a narrow `DIFF`/`FILE`** (a PR/branch reviewed against a base stays a compact packet) unless branch
cleanup was explicitly asked. Expands section **S** of `SKILL.md`: detection commands, per-branch decision
tree, merge-strategy trade-offs, and safety rails for acting on the recommendation. The deliverable is a
**triage of all open work**: one recommendation per branch, plus the exact command to carry it out.

Standards this file tracks (trunk-based, GitHub/GitLab flow, git-flow, merge methods): `docs/standards-index.md`.

**Boundary with `docs-and-dx.md` (section O) — no overlap.** O owns *is branch protection configured*
(required PR / reviews / status checks, no force-push, CODEOWNERS) as a repo-posture check. **This file owns
*what open work exists and what should happen to each piece of it*.** The one seam — "must this merge go
through a PR?" — is resolved by *reading* O's posture and cross-referencing it, never restating the protection
checklist. Where review fixes land (a branch + PR, security split off) is `SKILL.md` Phase 5; this file
triages branches that already exist.

---

## 1 — Ground the branch set before judging it (fail closed, never "clean")

Every command below reads **local refs**, only as current as the last fetch — an un-refreshed or shallow clone
makes a repo with a dozen open branches *look* empty, the exact "empty output is not a pass" trap the skill
condemns (`full-map.md` principle 2). Before any triage:

- **Refresh and prune first:** `git fetch --all --prune`. A shallow clone
  (`git rev-parse --is-shallow-repository` → `true`) can't see full history, so its merged/unmerged answers
  are unreliable — say so and `git fetch --unshallow` or re-clone before trusting the result.
- **Open-PR / merged-PR state is forge state, not git state.** Whether a branch has an open PR, or was already
  **squash/rebase-merged via a PR**, lives on GitHub/GitLab/etc., not local refs. Read it with
  `gh pr list --state all` (or the forge API). Absent that auth/tooling, the PR column is **`unverified`** —
  name it as the resolving artifact (`full-map.md` principle 3); do **not** infer "no PR" from its absence.
- **Forge-only branches you never fetched are invisible to git entirely.** State the coverage honestly:
  "triaged N local + M fetched remote branches; forge PR state <read via gh | unverified: no forge auth>." A
  triage that silently omits un-fetched branches is a false all-clear.
- **A truncated listing is not a complete count — the same trap at a different threshold.** `gh issue list` /
  `gh pr list` (and most forge list APIs) default to a page of **30**; counting or triaging with no `--limit`
  (or no pagination loop) silently truncates there and under-reports everything past it — a real backlog of
  over a hundred can read as thirty. Before stating any count from a forge list, pass a limit that comfortably
  exceeds the expected total (`--limit 500`, or paginate on a returned cursor) and say what limit was used.
  "Empty output is not a pass" above and "truncated output is not the total" are the same failure: trusting a
  list's *shape* without checking whether it's actually complete.

Fail closed: if refs can't be refreshed or PR state read, the triage is `unverified` with the missing artifact
named — never a confident "nothing to clean up."

## 2 — Detect the branching model → this sets each branch's merge target

The user's "merge to develop **or** main" is answered here: **which** long-lived branch feature work
integrates into depends on the model the repo actually uses. Detect it from refs and docs, don't assume:

| Model | Long-lived branches | Feature work targets | Branch lifetime | Signals to detect it |
|---|---|---|---|---|
| **Trunk-Based Development** | one trunk (`main`) | **`main`** (trunk) directly, or a short-lived branch merged back fast | hours–2 days | single long-lived branch; short branch list; CI to main |
| **GitHub flow** | one (`main`), the default branch | **`main`** via PR, then delete the branch | short | PR-per-change; `main` default; branches deleted on merge |
| **git-flow (Driessen)** | **`main` + `develop`** | **`develop`** for features; `release/*` and `hotfix/*` off/onto `main` | mixed; some long-lived | a `develop` branch exists; `release/*`, `hotfix/*`, `feature/*` prefixes |
| **GitLab flow** | `main` + environment or `release/*` branches | **`main`** first ("upstream first"), then promoted downstream | short feature, long env | `production`/`staging`/`pre-prod` or `release/*` env branches |

Detect the repo's default branch with `git symbolic-ref refs/remotes/origin/HEAD` — **often unset**
(`fatal: … is not a symbolic ref`); run `git remote set-head origin -a` first, or read
`gh repo view --json defaultBranchRef`. Then: **if a `develop` branch exists and carries commits `main`
doesn't, treat features as targeting `develop`** and `release/*`/`hotfix/*` as targeting `main`; otherwise the
target is the default branch (`main`). State the detected model in one line before recommending targets — if
ambiguous (e.g. a lone `develop` with no supporting-branch convention), that's an owner decision, not a guess.

**Check the base of work *in flight*, not only the target of finished branches.** Once the model names the
integration target, enumerate in-flight work against it: open PRs
(`gh pr list --state open --limit 500 --json number,baseRefName,headRefName,changedFiles` — pass a limit
exceeding the expected total and say which, per §1; the default 30 silently truncates) **and** pushed branches
with no PR yet (§3's `for-each-ref` enumeration — where retargeting is still cheapest). Verify each one's
**base** against that target with the §3 divergence count
(`git rev-list --left-right --count <integration-target>...<branch>`). A large change branched off the
**wrong** base — e.g. off `main` while features integrate into `develop`, which carries commits `main` lacks —
is written against a product state that no longer exists on the integration line; merging it later conflicts
with or reverts those commits, and every lane built on that base inherits the problem. A PR's own green checks
say nothing about whether its **base** is right; that's a §7 severity call, below.

## 3 — Enumerate & classify every branch (validated commands)

Run these against refreshed refs. Each row is a classification signal, not a verdict — the verdict comes from
the §4 tree. (All commands below were validated against a scratch repo covering normal-merge, single- and
multi-commit squash-merge, rebase-merge, stale-unmerged, diverged, and deleted-remote cases.)

| Question | Command | Reading |
|---|---|---|
| Already merged (tip is an ancestor)? | `git branch --merged <target>` / `git branch -r --merged origin/<target>` | listed → tip is reachable from target; a normal or fast-forward/rebase merge |
| Not merged by tip? | `git branch --no-merged <target>` | listed → tip not an ancestor — but this **also lists squash-merged branches** whose content already landed (§ trap) |
| Content already applied (squash/rebase/cherry-pick)? | `git cherry -v <target> <branch>` | `-` = that commit is already upstream; `+` = not; **no output = fully applied** |
| Unique commits to bring in | `git log --oneline <target>..<branch>` / `git rev-list --count <target>..<branch>` | the work a merge/PR would actually add |
| Ahead **and** behind (diverged)? | `git rev-list --left-right --count <target>...<branch>` | `A⇥B` → A commits only on target, B only on branch; both > 0 = diverged, needs rebase/merge before it lands cleanly |
| Staleness + tracking, sorted oldest-first | `git for-each-ref --sort=committerdate --format='%(refname:short) %(committerdate:relative) %(upstream:track)' refs/heads` | last-commit age per branch; drives the stale bucket |
| Remote branch deleted, local ref lingering | same `for-each-ref` → `%(upstream:track)` is `[gone]` (or `git branch -vv` shows `: gone]`) | merged-and-cleaned-up-remotely — safe to prune the local ref |
| Never pushed (the **only** copy) | `%(upstream:short)` empty in `for-each-ref` | work exists **nowhere but this disk** — deletion is data loss (§6) |

**The squash-merge trap (verified, and the most common false positive).** `git branch --merged` reports a
squash- or rebase-merged branch as **un**merged, since its tip never became an ancestor of the target.
`git cherry` recovers the **single-commit** squash and any rebase/cherry-pick (patch-ids match), **but a
multi-commit branch squashed into one commit defeats patch-id matching** — cherry still shows `+` for every
commit though the content is fully in `main`. So the **forge's merged-PR list is the authoritative
corroborator** for "already merged": before recommending "open a PR / N commits to merge," cross-check
`gh pr list --state merged --head <branch>`. Recommending a merge for already-merged work manufactures a
conflict-laden PR — a fabricated finding.

## 4 — The decision tree (one recommendation per branch, target from §2)

Walk top-down; the first match wins. Every "merge/PR" resolves its **target** from the detected model (§2) —
`develop` under git-flow, else the default branch.

1. **Content already in the target** (normal-merged, or squash/rebase-merged confirmed by cherry *or* the
   forge merged-PR list) → **delete the branch** (local `git branch -d`; remote
   `git push origin --delete <b>`; local `[gone]` ref → `git fetch --prune` already flagged it). `-d` refuses
   if git thinks it's unmerged — for a confirmed squash-merge use `-D` **only after** the forge confirms the
   merge. **Before any delete, check for a stacked PR first** (§6 → `merge-operations.md`) — a branch can be safely merged-away by
   every check above and still be the *base* of another open PR.
2. **Never pushed and holds unique commits (only copy)** → **push first** (`git push -u origin <b>`) so it's
   recoverable, *then* apply the rest of the tree. Never delete an unpushed unique branch (§6).
3. **Unmerged, coherent, ready, target is protected / needs review** → **open a PR** to the resolved target.
   If the branch is behind, rebase/refresh it first (step 6). Read O's protection posture to know whether a PR
   is *required* vs a direct merge is allowed.
4. **Unmerged, coherent, ready, trunk-based repo with no PR requirement** → **merge to trunk** (fast-forward
   or per the repo's merge strategy, §5) — or still prefer a PR if any status check or reviewer gate applies.
5. **Unmerged but mixes unrelated work, or bundles a security/permission change with routine edits** →
   **split**: the security-relevant part rides its own small PR (this *is* `SKILL.md` Phase 5's
   split-by-risk-surface rule); or **cherry-pick the one good commit** out of an otherwise-stale branch and
   drop the rest.
6. **Diverged (ahead + behind) or behind the target** → **rebase or merge the target in** to land cleanly,
   then re-triage (usually → step 3). Rebase only unshared/personal branches; a **shared** branch is merged,
   not rebased (§6). For a **long-open** branch this is necessary but not sufficient — rebasing and re-running
   CI doesn't prove the merge won't revert work the target landed since the branch forked; verify its effect
   against current HEAD first (§6, long-open-PR bullet).
7. **Stale + WIP + no clear owner intent** → **escalate to the owner** (a "Decisions needed" item) with the
   age, unique-commit count, and last author; don't guess whether abandoned work should ship.
8. **Open PR that should not be merged** (superseded, wrong approach) → **close as superseded** (don't merge,
   don't silently delete the discussion) — or **convert to draft** if it should stay visible and CI'd but not
   mergeable.
9. **Worth keeping but not now** → **tag-then-delete**: `git tag archive/<b> <b>` (or an `archive/*` ref) then
   delete the branch — reversible, clears the branch list without losing the work (§6).

## 5 — Merge strategy & "PR or direct merge?"

Match the repo's existing convention first (read merged history: `git log --merges --oneline -20` — many merge
commits ⇒ merge-commit repo; near-linear ⇒ squash/rebase). The three GitHub methods and their trade-offs:

- **Merge commit** (default, `--no-ff`): preserves every commit and records a merge commit — full history,
  non-linear graph. Best when individual commits are meaningful and an explicit integration point is wanted.
- **Squash and merge**: collapses the branch to a **single** commit on the target — clean, linear history, one
  revert unit; loses intra-branch granularity (and creates the §3 cherry trap for future triage).
- **Rebase and merge**: replays each commit onto the target with **no** merge commit — linear history that
  keeps individual commits. Rewrites the commits' identity, so it's for branches never depended on downstream.

**PR vs direct merge** is decided by O's protection posture, not preference: if the target requires a PR +
review + passing checks (a protected branch), the recommendation is **always a PR** regardless of model. A
merge queue, where present, automates merges into a busy protected branch and tests each change against the
latest base so the branch is never broken by incompatible changes — recommend it instead of racing merges.
Never recommend a direct push to a protected default branch (`SKILL.md` Phase 5).

**The rest of §5 — landing and merge-pipeline mechanics** (merge trains, the mergeable snapshot, stale greens, red bases, hung or unsatisfiable required checks, PR-body gates, the merge base, self-reported evidence, worktree hooks, stacked-PR CI attribution, stop semantics) **lives in `merge-operations.md`.** Load it when landing or sequencing PRs, or when a merge gate or required check is stuck, stale, red, or in question.

## 6 — Safety rails (acting on the triage is destructive / shared-state)

Triage is **advice**; carrying it out mutates shared state. Under `full-map.md` principle 7 and the global
"confirm before destructive/irreversible/shared-state" rule, produce the recommendation + the exact command,
and **execute only on explicit approval** — the same opt-in bar as the Phase 6 imprint. The rails
for **recommending or executing** a close / delete / merge row — a stacked-PR base, generated-artifact conflicts, a subset absorbed at a stale SHA,
closing a duplicate, gating an irreversible or automated step, updating a branch another worktree holds —
continue in `merge-operations.md` (§6 continued); load it before recommending or acting on any such row.

- **Never delete unique unmerged work.** Deleting a branch whose commits exist nowhere else is irreversible
  data loss. Gate every delete on "content is in the target (§3 confirmed) **or** it's tagged/pushed
  elsewhere." Prefer **tag-then-delete** so any delete is reversible.
- **A long-open PR is reviewed against its own fork point, so its diff cannot reveal a revert of work the base
  shipped after it branched.** Distinct from the subset-absorb case (`merge-operations.md`; two open PRs, B holding a stale
  subset of A): here **one** PR sat open while the integration branch raced hundreds of commits ahead, and the
  trap is that the **review surface itself is merge-base-relative**. A PR's "Files changed" view is
  **typically** merge-base-relative — as is `git diff <base>...<branch>`, which `git-diff(1)` defines as
  `git diff $(git merge-base <base> <branch>) <branch>` — showing only what the branch changed *since it
  forked*. That looks correct (it **is** the intended change from the old fork point) but is **blind by
  construction** to everything the base landed on those same files afterward. So green + mergeable + a clean
  Files-changed is a **false all-clear**: where the branch edited a file the base has since advanced (a landed
  fix, a hardening), merging can drop that newer work. A plain three-way merge would at least **conflict
  loudly** where both sides edited the same lines — but the silent paths don't: a **squash-merge** lands the
  branch's tree for the files it changed (the base's newer content in them goes with it — the §5 squash
  trade-off / §3 cherry trap), an automated resolution **toward the branch** (`--theirs`, the §6 hazard in `merge-operations.md`)
  takes the stale side outright, and even a **textually clean** merge can defeat the fix **semantically** when
  the branch edited a different region (a caller) than the base hardened (the callee). The branch's own green
  proves nothing either — it ran against its fork-point view of the world. **Two-dot
  `git diff <base>..<branch>` is the mirror trap:** it *over*-reports, flagging every file the base advanced
  but the branch never touched as a **phantom reversion** the real three-way merge would not produce — a lead
  to triage, never the verdict. Take the verdict against **current HEAD**: list the paths the PR touches
  (`git diff --name-only $(git merge-base <base> <branch>) <branch>`), ask whether the base landed commits on
  any of them since the fork (`git log $(git merge-base <base> <branch>)..<base> -- <those paths>` — non-empty
  means the PR's tree predates real work there), and prove the actual effect by **trial-merging onto current
  HEAD** — the throwaway integration branch of `merge-operations.md`'s merge trains, cut off HEAD — and diffing that result against HEAD.
  **Notation follows the question:** merge-base-relative (three-dot) is right for *what did this branch write*
  and correctly suppresses the two-dot phantom reversions (the duplicate-close bullet in `merge-operations.md` picks notation the
  same way), but it **cannot** answer *would merging undo shipped work* — that needs the base's post-fork
  side, which three-dot excludes. **"Rebase and re-run CI" is necessary, not sufficient:** a rebase can
  silently keep the stale side of exactly those files. If the PR's intent already landed on the base (its
  linked issues closed elsewhere), it's **verify-then-close**, not merge; closing someone else's PR is an
  owner call (§6 opening) — surface the touched-path-vs-HEAD evidence, don't act unilaterally.
- **"Is X shipped / live / already fixed?" is a *containment* question against the ref that governs "shipped"
  — a commit-grep on whatever checkout you have out, or a "the PR is merged" status, answers a different
  one.** A `git log --grep` / `-S` hit, a green "Files changed", or a merged-PR record only proves the change
  exists on **some** ref — the branch currently checked out, or the integration branch a PR merged **into**.
  Where a long-lived integration / `development` branch runs far ahead of the line that actually governs
  "shipped" (the release branch, the ref deploy promotes from — often **not** the integration tip, and never a
  **stale local checkout** drifted behind its own remote), a large amount of merged, grep-visible work is
  integration-only and **not live**; the naive check then invites a wrong action — dispatching a
  doc-correction PR to match a "shipped" model, telling a stakeholder a feature is live, closing a
  deploy-readiness item. So **name which ref governs "shipped"** first (where deploy promotes from, not where
  the newest work lands), then test **containment against that ref** with the §3 toolkit pointed at it, not at
  your current branch: `git merge-base --is-ancestor <landed-sha> origin/<governing-ref>` proves containment
  **only while the SHA is preserved** (a normal / fast-forward merge). Under a **squash / rebase /
  cherry-pick** the original SHA is not an ancestor though the content shipped — the §3 squash-merge
  false-negative, the mirror trap — so corroborate the way §3 does but **against the governing ref**: grep
  **its tree** for the landed symbol (`git grep <symbol> origin/<governing-ref>`,
  `git show origin/<governing-ref>:<path>`), `git cherry`, or the forge record of the PR that merged **into
  that ref**. "Merged" with no target named is the ambiguity: **merged-to-integration** (done,
  integration-first) and **promoted-to-release** (shipped) are different milestones — scope every status claim
  to the one you verified. Distinct from the stale-base silent-revert above (*would merging undo shipped work*
  — needs the base's post-fork side); this is *did the work reach the governing line* — needs containment
  against that ref. The same branch-blindness defeats the "is this finding already fixed?" reproduce check in
  `method.md` (its `git log -S` run on the wrong checkout clears a defect still live on the deploy line), and
  it's the verification the "a merged PR is a **proxy**, not the outcome" rule (`report-format.md`) leaves
  unspecified. Treat a governing branch thousands of commits behind its integration branch, with a conflicting
  / stale reconcile PR, as a **release-readiness blocker in its own right**: surface it early — when the
  frontier is genuinely exhausted the honest state is "gated on the promotion / owner," not more
  integration-only work that widens the gap.
- **Never rewrite shared history.** Rebase/force-push only branches that are personal and undepended-on. When
  a force is genuinely needed, it's **`git push --force-with-lease`** (refuses if the remote moved under you),
  never `--force`. A rebase of a shared branch is a merge instead: **merge the base into the branch** (an
  ordinary merge commit), which stays append-only and safe for anyone else's checkout — never rebase-then-force
  a branch you don't know is exclusively yours. Detect "shared" before either operation: `git log --format='%ae'
  <branch> ^<target> | sort -u | wc -l` > 1 means more than one contributor's commits are on it; `git worktree
  list` shows every other checkout on this machine, and a forge's compare/PR view shows commits pushed from
  elsewhere. Either signal means treat the branch as shared — merge the base in, don't rebase and force.
- **Deleting a branch does not scrub its objects.** A branch that ever carried a **secret or PII** isn't
  remediated by deleting it — the objects remain reachable on the remote until GC/forge cleanup, and clones
  already have them. The remediation is **credential rotation** (and history purge / forge support), not
  `git push --delete`. Flag this as its own line, never "delete fixes it."
- **Remote deletes and history rewrites are confirmed, explicit, one at a time** — no batch `--delete` of a
  list the user hasn't seen and approved.

## 7 — Severity discipline (don't turn cleanup into noise)

Branch hygiene has the same noise failure mode as dependency currency (`dependency-currency-and-upgrades.md`
§3): forty stale branches become forty Lows that bury a real Critical. **Batch routine cleanup as ONE finding
carrying the triage table**; escalate a branch to its own finding only on consequence:

- **An unmerged security/bug fix sitting on a stale branch** (the fix exists but was never shipped) → **High**
  — the vulnerability is live *and* the fix is already written but unreleased.
- **A branch that is the only copy of real work** (never pushed) → **High** as a data-loss risk until it's
  pushed/tagged.
- **A large or long-lived change built on the *wrong* integration target** — not the one §2 detected (a case
  arising only where two long-lived branches exist, so there *is* an alternative target) → **High**, distinct
  from and **above** the Medium merge-debt row below: the cost compounds with every commit added on the wrong
  base, and unwinding it later is a forced retarget/rebase of work already built. Intrinsic severity stays
  High at every stage (guardrail 3, `SKILL.md`); stage calibrates only the **urgency** — block-now on a
  `growth`/`mature` line vs tracked on a `prototype` — never the severity. State the left⇥right commit counts
  measured and name the **retarget/rebase-before-more-work-lands** command in the finding.
- **A long-lived `develop`/`release/*` badly diverged from `main`** → Medium merge-debt (Fowler: integration
  frequency; the longer branches live apart, the worse the eventual merge).
- **A branch carrying committed secrets/PII** → severity per the exposure boundary (`security-appsec.md`);
  remediation is rotation, not deletion (§6).
- **Everything else** — merged-and-undeleted, stale WIP, gone-upstream local refs, behind-but-clean → **one
  batched Low/Info** with the triage table and a recommendation to enable "auto-delete branch on merge" so it
  stops recurring.

Never let the volume of routine branch cleanup outrank a real defect.

## 8 — Spike / prototype branches (a naming convention, not a new gate)

A deliberately fidelity-capped, disposable-by-construction exploration (Shape Up's
breadboard/fat-marker-sketch idea, applied to code instead of design) is cheap to discard *if marked as one
before it's built*. This rides the branch-pattern logic this domain already owns — not a new file, not a new
gate:

- **Gate:** a branch matching a spike/prototype naming convention (`spike/*`, `prototype/*`, or the project's
  own documented equivalent) declares its timebox and throwaway status (in the branch's first commit message
  or a linked issue), and never merges to the target **as-is** — it's rewritten to production quality or
  explicitly "graduated" (renamed/re-based onto a normal feature branch) first. **Trigger:** branch-name
  pattern match only, at merge time — never fires on an ordinary feature branch. **Owning hat:** Release &
  docs (this domain already owns branch triage).
- **Planted-defect test:** a `spike/foo` branch merged directly to the target with no rewrite and no
  graduation marker → the gate flags it.

## Triage table (the deliverable — emitted in the report)

```
| Branch | Last commit | State | Unique commits | Open PR | Recommendation | Command |
|--------|-------------|-------|----------------|---------|----------------|---------|
| feature/x | 3 days ago | unmerged, ready | 4 | none | Open PR → develop | gh pr create -B develop -H feature/x |
| bugfix/y | 6 months ago | squash-merged (PR #42) | 0* | merged | Delete | git push origin --delete bugfix/y |
| spike/z  | 1 year ago  | stale WIP, only copy | 12 | none | Escalate to owner; push to preserve | git push -u origin spike/z |
```
`0*` = cherry shows commits but the forge confirms the PR merged (multi-commit squash). Mark any PR column
`unverified` when forge auth was absent (§1).

## 🚩 Red flags

- A `develop` branch unmerged to `main` for months (git-flow gone stale).
- Dozens of merged-but-undeleted branches and **no** "auto-delete on merge".
- Long-lived `feature/*` branches many commits behind the target (merge debt).
- An in-flight branch/PR whose **base is not the detected integration target** (e.g. based on `main` while
  features integrate into `develop`) — for a large or long-lived change, a **High** wrong-base defect (§7),
  not Medium merge-debt.
- A branch with an unmerged security fix — the patch exists but never shipped.
- A branch that only exists on one machine (no upstream) — one disk failure from lost work.
- Recommending "merge / open a PR" for a branch the forge already merged via squash (the §3 trap) — a
  fabricated, conflict-generating finding.
- `git push --force` (not `--force-with-lease`) anywhere near a shared branch.
- "Just delete the branch" offered as the fix for a leaked secret.
- A branch deleted with no check for a stacked PR using it as base.
- A generated/compiled-file merge conflict resolved by hand-splicing instead of regenerating from the merged
  source inputs.
- A runbook/script chaining a preflight and an irreversible command with a bare `;` (or two unconditional
  steps) instead of the preflight's documented pass condition.
- A safety-critical exclusion/allowlist check built on an unquoted `for x in $VAR` loop with no verification
  it actually iterates per-item in the shells the script claims to support.
- A `spike/*`/`prototype/*` branch merged to the target as-is, with no rewrite and no graduation marker.
- A merge-train batch landing a gate-adding PR before the PRs it would force to retrofit that gate.
- A new PR-body / commit-trailer / committed-artifact gate landed with **no update to its standing producers**
  (PR template, Dependabot/Renovate, release/agent bots) — every automated PR is refused (green on its real
  work, red on the new gate) until noticed (`merge-operations.md`'s merge trains cover only in-batch ordering).
- A union/integration branch merged or squashed in place of its member PRs, or already-green members held
  waiting on the union's aggregate CI.
- An `--admin`/force-merge used to escape a red base, instead of discharging it with a verified merge train.
- A `STOP` that leaves a green + `MERGEABLE` PR neither merged under standing approval nor handed off by URL,
  or an unpushed rebase abandoned off the remote.
- A PR merged after another that absorbed its files at an older SHA — a stale subset silently reverting the
  later fix, with no conflict to warn.
- A **long-open PR** approved on its "Files changed" / own-base diff (fork-point-relative, so blind to what
  the target shipped on those files since it branched) — or waved through on "rebase + re-run CI" — with no
  check of the target's post-branch commits on the paths it touches; a squash, a toward-the-branch resolution,
  or a semantically-coupled clean merge then drops that newer work with no conflict to catch it.
- An "X is shipped / live" or "already fixed" claim resting on a commit-grep, a "Files changed" diff, or a
  merged-PR status on the **current / integration branch**, with no containment check against the ref that
  governs deploy — on a repo where integration runs far ahead of the release line, much grep-visible / merged
  work is not live.
- A batch merged off one up-front green + `MERGEABLE` snapshot with **no per-merge re-check**, or a **merge
  sweep run concurrently with a conflict-resolution lane** against the same base — the moving base head flips
  later members back to `CONFLICTING` while their checks stay green.
- A merge on a **finished green that no longer matches the merge target** — a body/metadata edit, base
  retarget, or description amend the gate's trigger ignored, or a **rebuild whose fresh run is still in
  flight** — trusting the check's colour without reading the head / input digest it ran against.
- A PR closed as duplicate/superseded on title or branch similarity with no tip-diff evidence in the close
  comment.
- A local hook, a `Tests: N/N` line, or a checked box logged as a passing control (self-reported,
  `--no-verify`-bypassable, no committed record) instead of a forge run pinned to the SHA.
- Under a worktree: an inherited absolute `core.hooksPath`, or a pre-push hook whose range is a hardcoded
  default branch instead of the pushed refs on stdin — gates run against the wrong tree or the wrong range.
- A programmatic conflict resolution that stages with a quoted `git add` **without** grepping the staged tree
  for `<<<<<<<` / `=======` / `>>>>>>>`, or an unescaped `[param]` / glob-metachar path in a `git checkout` /
  `add` (a no-match glob silently no-ops the resolution).
- A **force-push** used to update a branch checked out in another worktree (strands that lane's unpushed work
  on a diverged branch + discards its pushed commits) instead of a detached-HEAD fast-forward.
