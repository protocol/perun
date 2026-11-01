# Software-house roles — hats over the delivery gates

Read this when standing up (or running) the full delivery team on a repo: who
does what, when a hat fires, which gate it owns; when the Conductor drifts into a
lane's work; or when tempted to skip a G4/G5 step (anti-rationalization table).
Each hat's discipline is one the review lens does not carry. Expands the **Operating model** in
`SKILL.md`. Depth only where the delivery role adds something the review side
does not already hold — for the rest it **points** to the `deep-code-review`
skill's `role-coverage.md` (see **Cross-references** below), the review-time lens
for the same role, rather than restating it.

The shape is grounded in how multi-agent software frameworks actually decompose
the work — an **assembly line of specialized roles driving a standard operating
procedure**, so each stage can *verify the previous one's output* instead of
chaining unverified generations (MetaGPT; ChatDev's specialized agents across
design → coding → testing) — and in the agentic-workflow patterns a team like
this is built from:
an **orchestrator** that decomposes and delegates, **parallel** workers, and an
**evaluator** that critiques a generation in a loop (Anthropic, *Building
Effective AI Agents*). All by-name; see the standards index
(`docs/standards-index.md` in the repo, `standards-index.md` in the installed
`deep-code-review` references).

**Cross-references.** Bare file names below — `role-coverage.md`,
`product-ux-quality.md` (and its sub-files `ux-interaction.md`,
`ux-gates.md`), `docs-and-dx.md`, `security-appsec.md` /
`security-ai-agents.md`, `standards-index.md` — are files in the **sibling
`deep-code-review` skill**, reachable at `../../deep-code-review/references/<file>`
from here; the installer always ships that skill alongside this overlay, so the
path resolves whenever this file does. Bare `SKILL.md` means **this** skill's
`SKILL.md`; the review bar's own phases are named "the `deep-code-review`
bar's …".

Two rules override the whole roster:

- **Hats, not headcount.** A hat is a mandate that fires from risk, not a
  standing bot or a profile. One worker wears several compatible hats on a small
  change; do not spin up an identity per role. Start with the fewest hats the
  change's blast radius needs and add one only when a simpler structure has
  provably fallen short (*Building Effective AI Agents*: add complexity only when
  it demonstrably improves the outcome).
- **Independence where it counts.** The hat that *builds* never also *signs off*
  its own build. QA, Security, and the adversary are independent of the
  Implementer — a different context, and for a sensitive diff a decorrelated
  second model (the reviewer runs in its **own context window with its own tool
  access**, the property that makes a subagent a real second opinion rather than
  an echo — Claude Code subagents); a fresh context is also documented to reduce
  self-bias specifically ("a fresh context improves code review since Claude
  won't be biased toward code it just wrote" — Claude Code best practices).

---

## The roster (hat → fires when → owns at the gates → depth)

| Hat | Fires when | Owns at gates | Depth |
|---|---|---|---|
| **Conductor** | Every multi-hat change | Intent, task graph, merge plan, evidence roll-up (G0, G2, G7); never self-approves; once a lane is staffed, never self-executes its work — even under pressure | `SKILL.md` Operating model |
| **Ops / Merge-Guard** | ≥2 live lanes **and** a plumbing event | No gate ownership — serializes pushes, rebases / re-runs / ready-flips green PRs (the G7 owner merges), debugs flaky hooks, stops a retry loop only once its owner confirms; reports only exceptions, keeping the Conductor's context free for G0/G2/G7 | **below** |
| **Product Analyst** | Feedback / a "make it do X" ask / a vague outcome | Turns the ask into a testable spec + a feedback-coverage entry (G0, G1) | **below** |
| **Architect** | New surface, data model, or cross-cutting change | Seams, dependency direction, SPOFs, NFR budgets, drift from the stated design (G3) | role-coverage.md *Architect* |
| **Implementer** | Any code change | The diff, its tests, its rationale, one writer per worktree (G4) | **below** |
| **Evil Twin** | Any plan / approach / agent-originated "we should" | Attacks the claim before the owner sees it (G0/G1); pre-owner gate on every recommendation | **below** + `idea-critic` |
| **QA** | Behaviour, data, or UI changed | Independent functional / regression / a11y / state-coverage verification at the exact SHA (G5, G6) | role-coverage.md *QA* |
| **Security** | Authn/authz/egress/secret/supply-chain surface touched | Independent AppSec / privacy / supply-chain; red on paper + authorized testbed only (G6) | role-coverage.md *Data & AI*, *Backend*; `security-*.md` |
| **UX & Design** | A rendered surface changed | At-home bar, five data states, encoding hygiene, interaction-completeness (G4, G6) | role-coverage.md *UX & UI*; `product-ux-quality.md`, `ux-interaction.md` |
| **Release** | A change is ready to ship, or a feature flag is added | Named-owner sign-off, rollback proven, human approval on the outward action (G8, G9) | role-coverage.md *Release & docs* + **below** |
| **Docs** | Behaviour, API, or nav a reader sees changed | The docs move in the **same change** as their subject; no stale pointer left behind (G4, G10) | role-coverage.md *Release & docs*; `docs-and-dx.md` |

Every hat above is the **delivery** form of a review lens `role-coverage.md`
already defines. The review lens says *how to judge* the code from that role's
seat; the delivery hat adds *when the hat fires in the gate flow and what it must
produce there*. The four with **below** carry delivery discipline the review
lens does not hold; the rest are one-line pointers on purpose — restating
`role-coverage.md` here would be the duplication this framework forbids.

---

## Catch and reverse your own drift (Conductor)

**Catch and reverse your own drift into a lane's work** — the completeness
fix applied to *action*, not only attention. Scope: only while the Conductor
role is active **and** at least one lane is in flight; in single-agent mode
(ceo `full-map.md` **Size effort to the project**) the agent does the work.
The tell: two consecutive Conductor turns that query, build, edit, or mutate
the target instead of dispatching, reading a receipt, or deciding. On the
signal: **stop**, **package** a lane brief (goal, scope, acceptance check,
output contract), **dispatch** it (`full-map.md` *Worktrees and occupancy*), **resume**
status-reading. Exception: a step only the Conductor's session can perform (a
connector, credential, or surface no lane holds), done minimally.

---

## Ops / Merge-Guard — routine plumbing gets a hat, not the Conductor's context

The Conductor's context is the scarcest resource in a multi-lane run — it holds
the map of every lane, the plan for the next wave, and the state needed to
verify delivered work on the real surface. Plumbing — pushes, PR finishing,
flaky hooks, stuck retry loops — needs none of that judgment; left unowned, it
lands on the Conductor anyway, and that context is gone for the run.

- **Fires on an event, not as standing staff.** It fires when ≥2 lanes are
  live **and** a plumbing event lands (a push race, a green PR to finish, a
  flaky hook, a stuck retry loop). A single-agent project has no separable ops
  lane — that agent wears the hat (*Hats, not headcount*, above); staffing it
  for one worker, or before any event, is the "fifth bot" the anti-patterns
  (below) reject.
- **Owns the plumbing, not the plan or the merge.** Serializing pushes so two
  lanes don't race a ref; *finishing* a green PR — merge base, run gates
  locally, one push, flip it ready, nothing more: merging stays with the G7
  integration owner;
  chasing a flaky pre-push/pre-commit hook; stopping a retry loop that stopped
  making progress — only after identifying its owner (lane, session, or job)
  and getting that owner's confirmation. Known-mechanism work, not a judgment
  call the Conductor must make.
- **Reports only exceptions.** A push serialized, a PR finished, a hook fixed,
  a loop stopped — none of that is a status update to the Conductor; only what
  the lane could not resolve on its own is. The Conductor's event budget
  (*Conductor operating rhythm*, `SKILL.md`) stays reserved for a lane blocking
  a gate, a receipt, a budget breach, or a preflight collision — plumbing that
  already has an owner is never one of the four.
- **Route the event, don't absorb it.** The anti-patterns name a Conductor
  that *takes work back* from a staffed lane (below); this is the other side —
  when a plumbing event lands, hand it to the hat at once (a lane with slack
  wears it), so the Conductor is never the only one available. A Conductor
  spending its turns on a push or a hook signals an unrouted event, not work
  small enough to absorb.
- **Mechanism, not narrative.** Use the shipped tools, never a
  re-implementation: `scripts/serial_gate.py run` serializes a command across lanes with a
  flock-based lock (the push-serialization case), `scripts/lane_guard.py
  handback` verifies a lane's exact-SHA handback before it is treated as
  finished (the PR-finishing case), and `scripts/surface_check.py checks`
  reads each named check's latest run at a SHA (the flaky-hook-diagnosis
  case). The lane's own judgment is in reading those outputs and deciding
  when to escalate — the exceptions it reports.

---

## Product Analyst — feedback becomes scoped, verified work

The review side has a *product-planning lens* (problem→acceptance, smallest
slice, success metric — role-coverage.md). The delivery role is the front of the
assembly line: it converts a real signal into a spec a later stage can verify,
which is exactly the "requirements as the first SOP stage" that keeps a
multi-agent build from hallucinating a plausible-but-wrong feature (MetaGPT).

- **Feedback → scoped work.** Every unit of work traces to a real signal (a user
  report, a support theme, an analytics gap, an owner goal) or it is speculative
  build — flag it as cost, not progress. Restate the signal as the problem, the
  non-goals, and **acceptance criteria that each map to a test or eval**. An
  acceptance criterion with no test is `unverified`, never "done."
- **Interaction-completeness (the ask is not done until the loop closes).** A
  feature that lets a user *add* something is unfinished until they can **see,
  reach, and edit** what they added, in the same surface — a write-only input is
  a defect, not a slice. Trace every state change the ask implies through to its
  read-back. Depth and the greppable red flags: the `deep-code-review` skill's
  `product-ux-quality.md` and `ux-interaction.md`.
- **Benchmark against comparable products, by name.** Before speccing a solved
  element (a feed, a composer, an empty state, a delta, a filter), name how two
  or three comparable products solve it and match the muscle memory users already
  have; a novel design for a solved problem is a cost. "Looks nicer" is not a
  reason — name the precedent (the same by-name discipline the review bar's
  `product-ux-quality.md` uses). A deviation is surfaced to the owner as a
  decision, never shipped silently.
- **Maintain a feedback-coverage map.** A living list: each reported item →
  `scoped` (issue/spec) → `verified` (the shipped fix was checked against the
  original signal) or `deferred: <reason>`. It is the product analogue of the
  review's coverage ledger — an item that is silently dropped is the failure this
  map exists to make visible. "We shipped something" is not "we closed the
  signal"; only a verified entry closes it. **A `deferred` label is a reported
  decision, not an internal one** — labeling an ask `deferred` in the map without
  naming it to the owner, with a reason, in the same cycle it was deferred, is a
  silent drop wearing the coverage map's own vocabulary: from the owner's side
  nothing happened and nothing was said. One observed run: a sizeable share of an
  owner's asks were internally marked `deferred` over several sessions, and when
  the owner asked for a status of everything they had requested, most of that
  deferred set had never been mentioned to them, and several had no plan to be
  revisited at all. Surface every newly-`deferred` row to the owner in the cycle
  it changes state, with the reason and, when possible, an expected revisit
  point; a standing, owner-visible list of everything currently `deferred` is
  part of the routine status report, not a separate audit the owner has to
  request. *Worked example:* "deferring the export-format ask — waiting on the
  billing-schema decision, will revisit after that lands" is surfaced in-cycle,
  the opposite of a `deferred` row that only ever exists in the map file.
- **Owner-collected feedback and current shipped functionality outrank an
  abstract design spec — precedence is stable brief to merge.** When a
  design-spec review flags that a shipped feature (built from a real owner
  signal) deviates from the spec, the spec loses the tie: status quo (what
  currently ships) and owner feedback both outrank a new design ask. A lane
  proposing to revert a shipped, feedback-backed feature "for design parity" is
  exactly the deviation the bullet above requires surfacing to the owner as a
  decision — never executed silently — and needs the owner's **explicit
  confirmation** before the revert lands, not just a design-review sign-off.
  Write the ranking into the brief and read it back during review before
  landing, so a pivot-then-restore cycle (implement per feedback → revert for
  parity → re-request the same feedback) never repeats. `scripts/feedback_ledger.py`
  (landing in a parallel lane) is the mechanism meant to make each feedback
  item's shipped status auditable, so a proposed revert can be checked against
  it before it happens.

The Product Analyst **recommends**; scope and priority are owner decisions
(role-coverage.md: product ideas never carry Blocker/Critical gate language).
Its output feeds G0 (brief) and G1 (spec); the Evil Twin attacks the approach
before it reaches the owner.

---

## Evil Twin — the adversary as a standing hat

The mechanism, hats, and verdict schema live in the `idea-critic` skill; install
it with `--with-critic` / `--full`. This section is only its place **in
delivery**: it is the **evaluator** in an evaluator-optimizer loop (*Building
Effective AI Agents*) — a critique pass that runs *before* an approach becomes
work, not after.

- **Fires before substantive work, not after.** Attack the plan at G0/G1 (the
  approach choice) and before any agent-originated "we should" reaches the owner
  — writing, editing, and committing are substantive; orientation is not. A
  critique that arrives after the build is sunk cost, not a gate.
- **Default to dissent.** Agreement is earned by surviving the attack, not given
  by default; the failure mode this hat exists to kill is reflexive assent that
  ships a weak idea. See `idea-critic` for the three hats and the trigger.
- **Verify its own objection — the adversary is a lead, not an oracle.** A
  pushback is itself a claim and must survive the skeptic hat: check the premise
  against **current, verified state** (run the query, read the file at the pinned
  ref) before letting an objection stand. An adversary that blocks good work with
  a stale or assumed fact is a false negative dressed as rigor. Its findings are
  leads the parent re-verifies at source — never acted on as truth.
- **Decorrelated for high blast, and surface conflicts.** Low-blast/same-turn:
  the parent runs the hats inline. High-blast, unsolicited, or an owner decision:
  a genuinely different context or model (same-brain "independent" is a lie —
  idea-critic). When the adversary and the parent's own evidence disagree, keep
  **both** in front of the owner (a short dissent ledger); do not silently
  collapse to one.

---

## Implementer — the build discipline behind "one writer per worktree"

`SKILL.md` gives the Implementer one line (implements in a dedicated worktree;
never wears independent QA/security/release). This is the bar that line assumes —
the discipline that makes a diff reviewable and keeps the build from degrading
what already works. It is a generic engineering standard; a project's own
`CLAUDE.md`/`AGENTS.md` overrides it on conflict.

- **Documented + rationale.** Every exported function carries a docstring (one-line
  purpose, edge-case behaviour, side-effects: `Pure` vs `writes X`). A non-obvious
  branch says *does X because Y, trade-off Z* — pre-empt the reviewer's "why not W?"
- **Test the failure, not only the feature.** Fixing a bug lands a **regression
  test first** — red on current code, green after the fix. Weight-pin the
  coefficients of a scoring/heuristic function; snapshot a stable identity (an id,
  a dedup/join key). A change that would break a passing test is a signal the
  behaviour is intended, not a defect (cross-ref the review's REFUTED rule).
  An owner-reported fix is done only when a spec pins the exact geometry or
  behaviour; a later change edits that spec only with a quoted owner decision.
- **Errors handled per item.** External calls handle failure explicitly; a loop
  body catches per-item, logs, and continues — one bad item never halts the run.
  Never silently swallow.
- **No scope creep.** No premature abstraction, no helper for one call site, no
  speculative future-proofing, no half-finished code left in the diff. Three
  similar lines beat a wrong abstraction. **Multi-repo case, classify before dispatch:**
  a shared **provider** repo (source/raw fields, the platform every consumer reads) is a
  different scope than a **consumer** repo (a workflow, a derived/computed view built for
  one use). Building consumer-specific logic inside the shared provider is scope creep
  the diff-level checks above never catch, because the provider diff still looks clean in
  isolation. One observed run: 2 lanes built consumer-specific features into the shared
  provider (~45 agent-minutes; one lane killed, one discarded) before this was caught.
  Classify each planned feature provider-or-consumer at G2, before lanes are cut; route
  consumer-shaped work to the consumer repo. **Check:** the plan carries a
  provider/consumer column per item, not just a file/owner column.
- **No magic values.** Named constants/config; a status string or threshold lives
  in one shared place, not inline.
- **Unreleased UI ships flagged in the real app, not as a separate prototype.**
  New UI for a feature not yet ready to ship starts life as a flagged
  route/component inside the product itself, built with the app's own
  design-system primitives — never a standalone mockup or prototyping-tool
  export a later step must port. Design review happens by visiting the
  flagged route in the real app; the flag flip at release time is a
  visibility change, not a rewrite. This removes the fidelity-loss hand-off
  instead of building tooling to catch it after the fact (cross-ref
  `deep-code-review`'s `rendered-parity.md`, which names a standalone
  prototype needing a port as a finding in its own right).
- **Applied operations are idempotent** — safe to run twice, last-write-wins by a
  stable key — and **skip rather than guess**: an empty field beats a fabricated
  one; surface uncertainty.
- **Owns the running stack, not only the diff** — see `SKILL.md` *Local
  environment*. G5 is not green until the change was verified against the running
  process.

The Implementer hands QA and Security the **final reviewed SHA**, never its own
narrative, and never reviews its own build.

### Anti-rationalization (G4 / G5)

| Excuse | Rebuttal |
|---|---|
| "I'll add tests later." | Later is the load-bearing word. Tests before or with the change (G4). |
| "Too simple to spec." | Five lines of acceptance is a spec. Zero is not. |
| "Unit tests cover the UI." | Domain P needs headed-browser evidence on the route that renders. |
| "Green locally is green in CI." | Different OS, browser, secrets. Exact SHA in CI is the receipt. |
| "The stack didn't start; tests still passed." | G5 is `UNVERIFIED`, not pass. |

---

## Release — the discipline behind a shippable change

`role-coverage.md`'s Release & docs lens judges a release **at review time**
(sign-off checklist, rollback tested, branch triage). This is the **authoring**
counterpart: what the Release hat does *while a change is being built*, so the
review side has something real to check rather than a claim to take on faith.
Depth and the review-side checklist: the `deep-code-review` skill's
`release-engineering.md`.

- **Tag a feature flag's category the moment it is added**, not only when a
  later review finds it stale. Fowler's four categories: release (short-lived —
  a week or two, then remove), experiment (A/B/cohort — lifetime tracks the
  experiment), ops (operator kill-switch — meant to be long-lived), permissioning
  (feature-by-segment — long-lived, treat as an authz surface). A release-category
  flag ships with a removal date or a tracking issue **in the same change**, not
  as a follow-up nobody files.
- **A canary or blue-green claim ships with the config that makes it true**: a
  named traffic-split/router mechanism and a named halt metric (not error-rate
  alone — a business-metric regression is also a rollback trigger), not only a
  runbook sentence. "We'll do a canary rollout" in a PR description with no
  matching config is a plan, not a release.
- **Rollback is exercised, not only documented.** A tested rollback (a drill, a
  game-day, a prior incident that actually used it) is what G8 means by "rollback
  proven" — a runbook path that has never been run is `unverified`, the same as
  any other undemonstrated claim.
- **DORA-or-`UNMEASURED` before G8 is called done.** Compute deployment
  frequency, change lead time, change fail rate, deployment rework rate, and
  failed-deployment recovery time where the pipeline has the raw signal (deploy
  timestamps, incident/rollback records); report `UNMEASURED` where it doesn't —
  never a fabricated number, never a silent "fine."

---

## Gates a software-house repo runs (the SOP, made enforceable)

The roster is only doctrine until each mandate has a gate that enforces it — a
standard with no gate is advisory, and "documented but unenforced" is itself a
review finding (the `deep-code-review` bar's Phase 6). Two tiers: a fast
**commit-time** tier the
Implementer runs on every commit, and a slower **CI / pre-merge** tier the
independent hats own. Wire only what the target lacks; defer to gates it already
has.

| Gate | Tier | Owning hat | Enforces |
|---|---|---|---|
| Privacy / identifier scan | commit | Implementer + Security | No secret or third-party identifier on a committed surface (`ci-gates.sh privacy` is the pattern) |
| Format check | commit | Implementer | Zero diffs |
| Lint | commit | Implementer | Zero warnings |
| Type check | commit | Implementer | Clean |
| Unit tests (quick tier) + count in the message | commit | Implementer + QA | Green; `Tests: X/X` copied from a suite run on the staged tree, so a future drop is visible. Suites that run later (a merge train, CI) leave `Tests: none (<where they run>)`, the parenthetical naming where they run with no count or pass word: a count no run printed on this tree is an over-claim |
| Build + integration/E2E at the exact SHA | CI | QA | Green on the reviewed revision, local stack actually started (G5) |
| Verify-visible-UX | CI | UX & QA | Real controls exercised in the running app; a disabled control **looks** disabled; unit-logic passing ≠ a working UI |
| UX-evidence (screens-changed) | CI | UX | A page-changing diff shows the screens at a narrow + wide width, or an explicit `No UX change: <reason>` |
| Dependency / supply-chain | CI | Security | No known-vulnerable or EOL dependency introduced |

**Each blocking check runs once, at the latest gate that still blocks merge.** The
commit tier holds seconds-long checks; a suite that takes over a minute runs at the
merge gate (CI, merge queue or train) and not earlier. The same suite at two tiers
is a duplicate to remove, not extra safety: `references/pipeline-optimizer.md`
maps and prices them (`scripts/pipeline_profile.py map`).

Every gate obeys the same epistemology (`SKILL.md` *Gate epistemology*;
`ux-gates.md` for the three UX gates): it **tells "could not check"
from "found a problem," reports `UNVERIFIED` on the former — never a pass, and a
*required* check left `UNVERIFIED` still blocks its gated action (evidence and
permission are separate decisions) — is proven
**red on a planted defect** before it is trusted, and is **never stricter than
the standard it implements** (an over-strict gate produces a fix that regresses
another axis). A gate that reaches an external service retries a transient error
a bounded number of times and fails open on a persistent outage — a
can't-check is not a finding.

**Empirical check:** Cemri et al. (2025), 1600+ multi-agent traces: failures
cluster into system design (→ G0/G1), inter-agent misalignment (→ G2, worktree
preflight), and task verification (→ G5/G6) — already covered, not an
eleventh gate.

---

## Anti-patterns (these fail the roster)

- **A standing bot or profile per role.** The roster is hats; an identity per
  role is the "fifth bot" the critic HOLDs (idea-critic). Fewer hats than the
  blast radius needs, never more (*Building Effective AI Agents*).
- **The builder reviewing the builder.** Any hat signing off its own work
  removes the independence the gate exists to provide.
- **The Conductor self-executes under pressure.** The same failure class as
  never self-approving: when a dedicated lane reports difficulty or delay on an
  urgent fix, the Conductor takes the work back and implements it directly
  instead of keeping the lane staffed and handing back only at a true
  decision-gate or hard blocker. Reviews back up, other lanes go unstaffed, and
  the fix still lands late — the context-switch cost drops delivery below
  single-lane throughput, the opposite of what taking it over was meant to buy.
  One-writer binds the Conductor too: once a file is delegated to a lane, route
  every change to it — a safety fix included — through the owning lane, and run
  `scripts/claim_probe.py` before editing any path, like any lane; a direct
  edit can race the lane's write-then-rename and vanish with no conflict.
- **Collapsing a gate because "it's small."** Low-blast reversible work may
  collapse *adjacent* gates; it may never remove independent verification or a
  human approval that actually applies (`SKILL.md` Gates). Moving a blocking
  check to one later blocking gate is neither collapsing nor weakening it;
  removing it or making it non-blocking is both.
- **Reporting a running lane as a finished one.** A spawned hat/worker is *work
  in progress*, not delivered value — report what is running, and report the
  outcome only once it is verified (see `full-map.md` *Worktrees and occupancy* and
  *Failure*).
- **A second delivery OS.** This overlay composes with the review bar; do not run
  it next to another standing delivery pack on the same repo.
