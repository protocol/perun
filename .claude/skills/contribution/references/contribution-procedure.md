# Contribution procedure: depth

Read this when a lesson is borderline (project-specific or general?) or a leak is subtle
(the contribution `SKILL.md` routes here). `SKILL.md` holds the flow and the block; this holds
the worked tests and leak examples.

**Where you work.** Prepare the change in a checkout of the *upstream* repository, where
its gates and contribution rules live. The only thing carried over from the private
context is the generalized change, scrubbed before it is written into any file.

---

## 1. The generality test (worked)

Two questions; both must be yes, or stop. For this repo as the upstream, "the bar" is the skill text; for any other project it is that project's docs and open issues.

- **Does it reproduce off this project?**
  - *No →* a lesson like "our nightly job must run after this project's deploy"
    is project shape, not a principle. Imprint it in the project's own
    `AGENTS.md` via `deep-code-review` Phase 6. Nothing to contribute.
  - *Yes →* a lesson like "regenerate a checksum pin as the **last** pre-commit
    step, or a later edit silently invalidates it" reproduces on any repo with a
    checksum-pin gate. Candidate — continue to the second question.
- **Is it missing from the bar?** Re-read the exact target section in the skill.
  - *Present, or a near-duplicate →* stop. Adding it is slop; prefer the existing
    bar (`idea-critic`'s slop-rec rule).
  - *Genuinely absent →* candidate confirmed.

Example of the second gate catching slop: "distinguish a flaky browser-test
failure from a real regression before reverting" feels valuable, but
`agentic-delivery` principle 3 already carries it. Nothing to contribute.

## 2. Generalize — lesson to principle

Strip: names, stacks, ticket IDs, repository names, timelines, product
specifics. Keep: the defect class, its detection, and the fix shape.

The test for "generalized enough": could a reader on an unrelated stack apply it
**without knowing where it came from**? If they need the origin to understand
it, it is not generalized yet — keep reducing.

## 3. Scrub — mechanical floor, human ceiling

Run the repo's own fail-closed gate on the drafted artifact:

```bash
bash scripts/ci-gates.sh privacy --banlist .banlist.txt .
```

It reports `file:line`, never echoes the match, and fails closed on secret
shapes and banned identifiers. It **cannot** catch:

- **paraphrased facts** — "a client retrains its fraud model nightly" carries no
  name yet leaks a strategy *and* the existence of that client;
- **structural tells** — an example whose shape only makes sense for one
  organization's system;
- **timing / roadmap** — "before the launch next quarter" leaks a plan.

These are the residual-risk cases. The human who knows the source clears them;
the agent's job is to **flag** them, not to decide they are safe.

## 4. The provenance & risk block — filled example

Placeholders are fictional (`Acme Capital`, per this repo's confidentiality
rule); a real block names the real source **internally only**, and that line is
stripped from the public artifact.

```
SOURCE (internal only): a data pipeline at Acme Capital.
GENERALIZED-AWAY: the vendor name, the cron time, the table names; kept only
    "regenerate a checksum pin as the last pre-commit step".
RESIDUAL RISK I COULD NOT RULE OUT: NONE — the principle is a git/CI mechanic
    with no business content; the one source detail (a checksum gate) is a
    public pattern, not proprietary.
MOSAIC CHECK: NONE — a git/CI mechanic reveals nothing about the source even
    combined with prior contributions; if three contributions from one source
    instead rebuilt its stack + release cadence, that aggregation is the flag.
MECHANICAL SCRUB: privacy gate clean at <sha>.
DRAFTED BY: contribution 1.1.0 / <agent model> — recorded in the append-only ledger.
```

A `NONE` with a stated reason like that is acceptable. A bare `NONE` is not — it
is the same empty gesture as an `idea-critic` verdict that "found no issues"
without naming what it attacked.

## 5. Human handoff — via CONTRIBUTING.md

The human, not the agent:

- re-reads the block and **clears residual risk** from knowledge of the source
  the agent does not have;
- opens the PR per `CONTRIBUTING.md` (its gate list, the Definition of Done in
  `CLAUDE.md`, and the one-line "what I verified" note in the PR body).

The agent has prepared; the human decides and pushes. Research on this pattern
found **no safe automated substitute** for that merge gate — so it is imposed,
not optional.

## 6. Protected core (kernel)

A contribution must not weaken what decides what is safe to send: the privacy gate, the
evaluator and its thresholds, CI, the banlist, and the path list itself. Those paths live in
`kernel-paths.txt` beside `SKILL.md`; verify before sending:

```bash
git diff --name-only <base>..HEAD \
  | grep -Ff .claude/skills/contribution/kernel-paths.txt \
  && { echo "KERNEL EDIT: human-authored only, not an agent-drafted send"; exit 1; } \
  || echo "userspace only: ok"
```

A change that alters how the scrub or evaluator *behaves* is also a kernel change, and a
drafted change is graded by the unmodified harness, never by the improved one. An agent that
can edit its own evaluator raises its score by weakening the test, so the evaluator and the
merge gate stay out of reach.

---

Cross-references: origin trigger at `agentic-delivery` G10 + its
`references/retrospective.md`; the privacy gate and Definition of Done in this
repo's `CLAUDE.md`; the "we should contribute this" attack and the anti-gaming
rule in `idea-critic`; the imprint-locally alternative at `deep-code-review`
Phase 6.
