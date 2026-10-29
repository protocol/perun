# Gate epistemology — the twelve public principles, with full statements of 3, 9, 11, 12

Read this when: adding a gate (4); a publish boundary (1, 2); a check flips, can't run, or lacks input (3, 5); a merge train or revert (6, 10); tests (7); public artifacts (8); closing shared state (9); done (11); invariant forks (12). In detail: a gate flips, a count jumps, or a check could not run and you must call it defect, flake, or `UNVERIFIED` (3); before closing, deduplicating, or deleting shared state (9); before reporting a change as visible or done (11); before shaping a choice as an owner gate when a ratified invariant may already decide it (12). `full-map.md` **Gate epistemology** routes here; the numbering is shared, so "principle N" resolves in either file.

---

## The twelve principles

Copied as principles, not as anyone's private playbook:

1. **Publish boundary is the gate.** Private data may exist in a private
   checkout; the failure is *escape* into a public artifact, PR title,
   changelog, compiled bundle, or example. Scan those surfaces, not only
   file bodies.
2. **Banlist split.** Committed `.banlist.txt` = generic secret shapes.
   Gitignored local file = real identifiers. Fail closed if the committed
   list is missing or malformed. Report `file:line`, never echo the match.
   Scope a history scan to what the PR adds: `origin/main..HEAD` commits plus
   `git diff origin/main...HEAD`, never `old_tip..HEAD` (once main is merged in it
   re-scans main's history: false hits). Scan and push are separate steps.
3. **A gate can be wrong about why.** Real defect fails closed; a check that could not run is `UNVERIFIED`, and a required one still blocks even when authorization exists (evidence and permission are separate decisions); on a red pipeline find the failing step, rerun a known-flaky check; revert only once the failure reproduces and is tied to the change; re-fetch state when a result surprises you.
4. **Prove the gate can fail.** Plant, watch red, revert. Required for
   every new gate this project adds.
5. **Skip loudly over absent input.** Missing fixture ≠ pass.
6. **Union proof only on overlap.** G7.
7. **Test the failure, not only the feature.** Schema reject, authz deny,
   monotonic-quality overwrite.
8. **Definitions, not live values**, in any public or compiled artifact.
9. **Closing or deleting shared state needs evidence, not presumption** — a reproducible reason, unique context migrated first.
10. **A fleet-wide external advisory is a third case for principle 3, and an
    independent-queue merge cascade is a cadence choice subordinate to
    principle 6** — see `references/red-gate-triage.md`, `merge-queue-worktrees.md`
11. **"Visible/done" is measured on the owner's own surface, never a proxy** — wired ≠ rendered ≠ has a real value.
12. **A fork a ratified invariant already decides is not an owner gate**; a change that would reverse one is queued to the owner, never applied silently.

---

## Principle 3 — a gate can be wrong about why

3. **A gate can be wrong about why.** Real defect → fail closed. Check could
   not run → `UNVERIFIED` — neither a defect nor a pass; a *required* missing
   check still blocks its gated action even when authorization exists (evidence
   and permission are separate decisions). Applied to a red pipeline: identify
   the failing job **and step** before blaming the newest merge, and if the
   shape matches a known-flaky browser/probe/hydration check, rerun and recheck
   **before** reverting — a revert is warranted only once the failure
   reproduces and is causally tied to the change, not merely adjacent in time. And **a
   conclusion that surprises you** — a gate that flips, a count that jumps — **is the signal
   to re-fetch the specific state at decision time**, not to act on a snapshot remembered from
   earlier in the run (principles 9 and 11 apply the same discipline to a close and to the
   owner's rendered surface).

## Principle 3, a stale-runner case — a receipt names the script that produced it

A gate receipt records the blob of the runner it ran (`lkg.py record` stores `scripts/run-ci-tests.sh` at the commit) and is refused when the working-tree copy differs from HEAD's; `lkg.py check` rejects a receipt with no or a different runner. A lane that ran an old worktree copy proved nothing about HEAD's gate.

## Principle 3, an empty-baseline case — a gate with nothing to check is not the same as a gate that checked and passed

A gate that compares a run against a **baseline** (a ratchet, a pin count, a regression set) and finds the
baseline **empty** — zero pins, zero prior entries — can read as green by the same code path a real pass takes,
because "0 violations found" and "nothing was there to check" produce the identical exit code. That is principle
3's *check could not run → `UNVERIFIED`* case wearing a passing gate's clothes: an empty baseline has not
confirmed the thing it exists to confirm, it has confirmed there was nothing to confirm against. One observed
run: only a design ratchet among a set of similar gates turned out to have zero pins, and it silently passed
throughout. Treat a **never-populated** baseline as `UNVERIFIED`, not a pass: a gate whose baseline has never
had entries must fail closed or flag itself explicitly, the same skip-loudly bar principle 5 already sets for a
missing fixture, applied here to a baseline with nothing in it rather than a fixture that is absent. A baseline
that was populated and has since been **drained to zero** is different — that is the ratchet's goal state
(every pin fixed, every regression closed), and it is provable, not merely claimed: the history shows entries
that reached zero over time rather than a baseline that was always empty. Distinguish the two before scoring a
zero count: `UNVERIFIED` for never-populated, pass for drained-with-history.

## Principle 3, a stale-allowlist-entry case — the PR that fixes an allowlisted violation removes its own row

A ratchet or allowlist file records a **currently-known** violation so a gate can go green while a backlog is
worked down over time. Fixing the violation (deleting the offending file, renaming it, patching the code) without
removing its row leaves the gate expecting a violation that no longer exists. That row is now `UNVERIFIED` wearing
an exemption's clothes — principle 3's *check could not run* case, except here the row itself is the thing that
can no longer be confirmed. Nothing breaks **today**: the un-exempted check still passes. It breaks the moment
anything re-triggers strict counting on the same gate (a stricter mode, an unrelated later cleanup) — the count
now mismatches reality, and the PR that gets blamed is whichever one tripped the recount, not the one that left
the stale row. **Rule: a PR that fixes an allowlisted item removes that item's row in the same change; a gate
that supports it also fails (or warns) when a row names a violation that can no longer be found**, so a missed
removal is caught at the fixing PR, not at some unrelated later one. Shipped instance:
`deep-code-review`'s `scripts/binaries_gate.py` treats a `binaries-allowlist.tsv` row for a file that is no
longer tracked, or no longer at a banned extension, as a `STALE ALLOWLIST ENTRY` failure, not a silent exemption.

## Principle 3, an unmeetable-locally case — a check no local environment can run is an explicit logged skip, not a silent pass or an infinite block

Some checks a gate would like to run are genuinely **not runnable in the environment doing the verifying** — "a
green local verify equals a working container build" is unmeetable without a local container daemon, no matter
how thorough the rest of G5 is. Forcing that check anyway (fail the gate forever, or fabricate a pass) is worse
than naming the gap: one observed run explicitly logged the skip and named the deploy step as the **first
environment that actually checks it** — the gate that follows still runs it for real, and nothing downstream
mistakes the local green for coverage it never had. **Rule: when a check is unmeetable in the current
environment, log the skip with probe evidence (the failing check command and its actual output, not just an
assertion it "can't run here"), keep the verdict `UNVERIFIED`, and name the first environment downstream that
will actually run it** — never fold the gap into the local verdict as a silent pass, and the named downstream
gate (deploy, here) must block release until that check actually runs there and passes. This is
principle 3's *check could not run → `UNVERIFIED`* applied where "could not run" is a property of the
environment, not a transient flake.

## Principle 9 — closing or deleting shared state

9. **Closing or deleting shared state needs evidence, not presumption** — the
   "skip rather than guess" bar (principle 5) applied to removal. A ticket
   closed as duplicate/invalid needs a reproducible reason (not "looks like the
   others"), and any unique context it carried migrates to the canonical item
   **before** it closes. A batch of presumed-junk items is a batch of
   `UNVERIFIED` closures until each is checked — a plausible pattern across many
   is not evidence for any one.

## Principle 11 — visible/done is measured on the owner's surface

11. **"Visible/done" is measured on the owner's own surface, never a proxy.**
    Integrated to the mainline (G7), a green branch build, a passing test, an
    insert/row count, a grep count are engineering states — real, but none is
    "the owner can see it." Before reporting a change as *visible*, fetch the
    specific rendered thing from the surface the owner actually uses (a running
    app, the deployed page — which may lag a pinned or cached serve *behind*
    the integrated code), confirm it, and report only what you observed. Keep
    the states distinct in words: **wired / defined / rendered ≠ has a real
    value**; "queryable" ≠ "query written"; "the code path exists" ≠ "it was
    proven to run" (principle 3's `UNVERIFIED`, stated for the liveness case;
    it is what G9 verifies against a deployed SHA).

## Principle 12 — a fork a ratified invariant already decides

12. **A fork a ratified invariant already decides is not an owner gate.** Before shaping a
    choice as a human gate, check whether a ratified invariant — no-data-loss, a security or
    accessibility floor, a monotonic-quality rule — already mandates the answer; if it does,
    applying it is a lane's **mechanical** job, and escalating spends an owner decision on a
    settled question while the lane stalls. Gate only the genuine forks the invariants leave open.
    Conversely, a change that would **reverse** a ratified invariant or decision is not a lane's
    mechanical call either — stop and queue it to the owner rather than silently applying it (the
    code-level instance — never loosening a ratified assert-absent test to ship a conflicting
    feature — is `deep-code-review`'s `testing-situational.md`).


**Handles are identifiers too.** A brief that names a person by handle can get that handle copied into a code string. Names and handles belong only in PR bodies and comments, never in code, and the privacy gate's pattern list should also scan for handles.

- **A faster checker may run fail-fast before the authoritative gate only after error parity is proven.** The wrapper that runs both checkers on a commit appends the outcome at gate time (`scripts/pregate_parity.py record <ledger> <sha> <gate_failed 0|1> <fast_failed 0|1>`); `pregate_parity.py check <ledger>` allows the pregate only with at least 5 distinct failing commits and no row anywhere where the gate failed and the fast checker passed. This reorders the run only: a fast red may stop early, a fast green never skips the gate, and the authoritative gate remains the only thing that can pass a merge. This repo has no fast-checker caller; a project that adds one wires the wrapper.
