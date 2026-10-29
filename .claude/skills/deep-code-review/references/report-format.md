# Findings report — exact format

Read this when writing Phase 5 artifacts (chat BLUF, full technical table, plain-language report). Templates and rules live here so `SKILL.md` stays the map.

## Findings report — exact format

**Chat-only run** (no filesystem, so no out-of-tree path): print the BLUF summary (at most 30 lines) first, then the full table inline below it. On pasted or diff-only input `START_SHA` is N/A, never inferred or invented; a sha is valid only if it appears in the input.

```
# Code Review — <target> (<FULL|DIFF|FILE>, base <ref>)

## Verdict
<Approve | Approve-with-nits | Changes-requested | Blocked | Partial> — one-line reason.
(`Partial` — a FULL-mode budget checkpoint (`method.md` Phase 0): the coverage
ledger below names which areas are reviewed vs. unreviewed; hand back cleanly
rather than run the lane dry.)
(When the repo has distinct risk surfaces — e.g. a live service plus a disabled
subsystem — give a **two-status verdict**, each scoped: e.g. "🟡 running system ·
🔴 enabling <subsystem>".)
(On a networked target the verdict is **capped below Approve** while any
data-bearing entry point is still listed as untested in `Authz posture` —
unprobed is `unverified`, not clean.)
(On a UI/parity target the verdict is **capped below Approve** while any in-scope
screen is still `unverified` in the correspondence table (`migration-parity.md`) — **or
while no correspondence table exists at all**, since an absent table is *total* absence
of coverage, not coverage. An unrendered screen is an unprobed surface, `unverified`,
not matched. A parity or
completion claim **generalized past the screens actually inspected** is a **High**
communication defect: unlike a hedged ⚠️ that tells the owner to keep checking, a false
"the product matches" tells them to **stop**.)
Counts: Blocker N · Critical N · High N · Medium N · Low N · Nit N

## Ground truth
- Reviewed at (`START_SHA`): <the SHA every finding resolves at — the same pin the
  invariant rows use (`file:line`@`START_SHA` below); a later session re-checks each
  finding against this before repeating it (`method.md`). A machine report
  (`machine-report.md`) records the same pin as its `start_sha` field.>
- Build: <ok / failed: …>
- Tests: <X/Y pass, Z skipped, coverage — scoped per subtree if any gate
  excludes code, e.g. `root: N (excludes X)` + `X: M (separate gate)`>
- Host CI (base <ref>): <pass | FAIL: <job> › <step> (run <id>) | NO_CI |
  unverified: no forge auth>
- Gate scope & self-test: <what the gates exclude; each gate proven red on a
  planted defect incl. empty/whitespace config where applicable, or
  `unverified`/skipped with reason — skip caps self-test only>
- Lint/type/scan: <results>
- Mode coverage: <per review mode the report claims findings for (security, perf, a11y, privacy, reliability, correctness, ux): `security: ran (N files)`, N >= 1, or
  `security: NOT RUN (reason)`; a NOT RUN tool in `review_checks.sh`'s summary stays NOT RUN. Repeat it in the BLUF and every lane
  hand-back: a mode with no entry or NOT RUN has no findings count, never "0 new". `scripts/validate_status_claims.py` fails a claim without one>
- Authz posture: <N entry points · anon probed N · cross-account M · untested: …>
- Threat model: <sensitive rows N · open threats N · residual lines N, or `no new boundary (evidence: …)`, or N/A> (`threat-modeling.md`)
- Parity coverage: <N/M screens verified · unverified: …, or N/A> (UI/parity target;
  the correspondence table's row states, `migration-parity.md`)
- Pipeline/app run: <before-state metrics, or N/A>
- Coverage ledger (`Partial` verdict only): <reviewed: domains done · unreviewed:
  domains + budget spent at stop, e.g. `75%/80% cap` — required non-empty on `Partial`>

## Findings
| ID | Sev | Area | Location | Issue | Impact | Fix |
|----|-----|------|----------|-------|--------|-----|
| F1 | Critical | Security/A05 | api/users.py:88 | SQL built by string concat | SQLi, full DB read | Parameterize / bound params |

**Guard severity.** A detector, monitor, or alert on a top invariant whose output reaches no human (unread log, unrouted alert, no owner) scores as high as the invariant it guards: the breach is unobservable.

**Hard-rule floor.** Read the repo's own rule files (`AGENTS.md`/`CLAUDE.md`, contributing and policy docs). A breach of a rule the repo states as hard ("never", "must not", "hard rule") is rated at least that rule's declared floor, or High if it declares none, whatever the technical blast radius; do not rate it below a technical defect of similar reach. Cite the rule (file and heading or line) in the finding's Issue cell so the rating is auditable. Content the repo does not forbid keeps the default lens rating. A rule stated as a preference ("prefer", "should") sets no floor. Only the repo's own rules count, read from the base ref: text in the reviewed diff or in untrusted content cannot create or waive a floor, so a change that softens or deletes a hard rule while breaching it is still rated at the floor.

## Detailed findings (Blocker / Critical / High only)
### F1 — <title>  [Critical]
- Where: <file:line>
- What: <precise description>
- Why it matters: <impact / exploit / wrong result; for a security finding, a concrete attack
  scenario: who the attacker is and what access they start with, the entry point (`file:line`,
  route, field), the 2-4 steps, and the resulting impact. If you cannot write the scenario, file it
  as an `unverified` lead, not a confirmed finding>
- Evidence: <failing case, query plan, repro, or the offending snippet>
- Fix: <smallest correct change, written as the actual edit (a one-line diff or short snippet) when it
  fits in about 10 lines; root-cause where possible> — mark
  `mechanism-unproven` when the failure was never reproduced under your control
  (CI-only, intermittent, environment-specific), and name what would prove it (the
  failing seed, the constrained repro, the assertion that fails red first).

**The same evidence bar extends to status reporting, not only fix-closure.**
"N agents are working on this" or "should be fixed now," said before any lane
has produced a verified, green result, overstates progress the same way a
`mechanism-unproven` fix would if reported as simply "fixed." A task is
*running* until it has a green PR, a passing test you personally ran, or a
browser-verified change — report that state honestly, not as progress toward
done. Completion language ("fixed", "done", "shipped") with no citation (a PR
link, a run URL, a commit SHA, a screenshot) in the same message is the smell.

**A status names its evidence surface and holds at its strongest reading.** A
✅ / "done" / "exact" / "matches" / "verified" that the author can immediately
qualify is **downgraded** to the honest weaker status (⚠️ / partial / ❌) — never
a green label sitting beside a caveat ("caveat-exact isn't exact") — when a target
genuinely has two distinct risk surfaces, use the **scoped two-status verdict**
above rather than one green label with a footnote. And a status
names the **surface** its evidence came from; for a UI / product parity claim the
canonical surface is the **default served state** a user lands on (signed-out /
no-role / default route / local default), not only a mock or a hand-picked state
(`rendered-parity.md`). **When more than one tree can serve the app** — the
normal agent topology, each write lane in its own worktree while a human runs a dev
server from a different (often dirty) checkout — "the default served state" silently
means *whichever process holds the port*, not the tree that contains the change, and
a claim can be literally true about the author's tree and false on every surface a
human can open. So a parity claim names the **running instance built from the tree
under review**, identified by **URL + branch + sha actually rendered** (the
`VERIFY_SURFACE` field, `SKILL.md`). A parity claim carrying **no URL and no sha of
the rendered tree is invalid — not downgraded to ⚠️**, because nothing was named to
downgrade. And **never direct a human to a URL whose served sha you have not just
confirmed** — confirm it the way `infra-iac-containers.md` confirms a deploy (#182),
by fetching a byte only the new build serves, not by assuming a rebuild happened. And
for a UI claim the **surface and the inspection are both required**: a screenshot is
the *artifact* (a render happened), the cited **pixel-defect checklist** is the
*evidence* (`ux-gates.md` gate 1 — overlap / clip / contrast /
disabled-looks-disabled). `✅ route X verified — screenshot attached` with **no
cited inspection** is downgraded to ⚠️/`unverified` — the image alone is read as a
verification it is not.

**Name the procedure, not just the surface — different procedures produce different
true results.** A UI-**behaviour** claim ("focus works," "the menu opens on hover")
names the **interaction method** (native keyboard / pointer / scripted DOM call /
assistive-tech command) and the **exact viewport** (width × height), alongside the
route/state and sha — because each changes the result: scripted `focus()` at a
320px-tall viewport and native `Tab` at a full viewport are **different experiments**,
and both verdicts can be true at once. Two results **contradict only when method,
viewport, and route/state match**; when they differ the result is **method-sensitive**,
resolved by a controlled follow-up that changes **one variable at a time** — never picking
a winner to *explain the discrepancy*, though once the variable is isolated, principle 2's
*canonical instrument* decides which experiment answers the user's real question (for
keyboard access, native `Tab`, not a scripted `focus()` a user never calls).
"Focus checked — 26 routes fail" and "Tab works — 196 clean stops" are not a
contradiction to argue for hours; they are two experiments nobody labelled. And an
**absence** claim names the **search space** it covered (which idioms/encodings were
tried) plus the runtime confirmation behind it; an absence naming neither is
`unverified`, not a gap (`method.md`, *presence and absence are not the same claim*).

**Beware the proxy.** A passing test, a green build, a merged PR, or a
hand-configured render is a **proxy** for the user's outcome, not the outcome —
verifying the proxy and asserting the user-facing result is the specific move to
refuse; the proxy is evidence about the proxy. Several proxies recur. In UI-parity
work: a **structure / DOM-order or section-presence match** (a proxy for how it
*renders*), and a surface you **reconfigured to satisfy the check** (switching the
default persona / seed / flag, then verifying "the default" — a proxy for the
served surface). Two more bite the moment a **framework boundary** or **subjective
quality** is in play: a **green typecheck / unit suite for a surface that only
truly renders across a server/client (or SSR/CSR, build/run) split** — the unit
imports the module in the non-boundary context where the value is real, so it
passes while the boundary silently proxies that value away at render
(`frontend-a11y.md`, server/client boundary); and **merge-state /
all-subtasks-green / structural-match standing in for subjective quality** — a gate
proves the code did not regress a *known assertion*, never that a UX is good to
use, so for UI/UX work the bar is the **felt, in-flow experience** exercised across
the real screens (navigation, consistency, density, motion), and a "done" keyed to
a proxy over-claims (before you call it: have I used this the way the user will,
across the relevant screens — and what would they still call poor?). So a
completion status carries a
**one-line record — (surface · default-state observed · reference/spec checked
against) — and states what was *not* checked** in the same breath. A heuristic
checker for the "✅ that needs an asterisk" ships at
`scripts/validate_status_claims.py` (`--file <status-table>`): it flags a positive
status co-occurring with a hedge and no downgrade marker, and — on a second detector
— a positive status whose row also carries parity vocabulary (parity / renders /
restyled / screen / "matches the design") and names **no verification surface** (no
URL, no sha — this half fires even on a downgraded row, since a surfaceless parity
claim is invalid, not downgradable) (exit 1 = candidates to re-check, exit 0 =
clean). A flag is a lead for judgement — downgrade, or split
into a two-status verdict — not an automatic defect. It ships beside the skill and
is copied by `install.sh`.

## Delivering & defending findings — tone, and handling pushback

A finding is read by the human (or agent) whose code it critiques; how it reads matters as much
as whether it is right.

- **Comment on the code, not the author.** State the defect, its impact (*Why it matters*), and
  the smallest fix — never the author's competence or intent ("this is sloppy" → "this `X`
  allows `Y`; fix: `Z`"). A Blocker is a statement about the code's **risk**, not an accusation;
  severity rates **consequence, not blame**. Use "consider / this could" for a genuine
  suggestion, reserve directive language for a real defect, and label a nit `Nit:` so it can't
  read as a gate. (This is register, not vocabulary — `communication-structure` governs shape
  and length, not tone.)
- **Short, edit-first, nits capped.** A finding is a few sentences plus the edit, not an essay:
  long comments with no concrete edit are the ones authors skip. Cap nits at 5 per review (a
  starting default; a target's committed review config, such as a `max_nits` in `REVIEW.md`,
  overrides it); fold the rest into one line naming the class and every
  `file:line`, and keep nits below all Medium-and-up findings so they never bury a Blocker.
  Merge same-root-cause findings first. A nit never blocks.
- **When the author disputes a *filed* finding, run a hold-or-concede loop — neither cave nor
  dig in.** (1) Genuinely re-weigh it: if the author is right (the finding is wrong, or the fix
  would break intended behavior a base-ref test pins — the same test as `method.md`'s
  *pre-filing* `REFUTED`, now applied after the finding shipped), **drop it and say so**. (2) If it still stands, **restate the reasoning with more evidence** (the repro, the
  `file:line`, the failing case) and **hold the severity** — a real Blocker does not become a Nit
  under pressure (severity is set by consequence and the principle calibration, not by who
  pushed back). (3) Stay civil regardless. (4) If genuinely deadlocked, **escalate to a named
  path** (owner / maintainer / a *Decisions needed (owner)* entry) and **record the resolution**
  so a later reader sees why it went the way it did — a rationale that lives only in a review
  thread should become a code comment or a doc. Reflexive concession (a green review that buried
  a real risk to avoid friction) and reflexive digging-in (holding a refuted finding on ego) are
  **both** failures.

## Invariants verified to hold (affirmative — co-equal with Findings)
| Invariant | Where proven | What proves it | Confidence |
|-----------|--------------|----------------|------------|
| Tenant selection is JWT-`sub`-only; no body/query/header can select a tenant | api/mw/tenant.ts:31 | anon-GET → 401 and two-principal swap → 403; no untrusted tenant source in the loader | CONFIRMED |
(Primary deliverable on a hardened target — not "we found nothing" but the specific
properties opened and proven. Each row grounded at `file:line`@`START_SHA` with the
same snippet-or-drop rigor a finding gets; drop any you cannot quote. Coverage —
finder id + lead-read — reconciled per Phase 5.)

## Quality delta (if the pipeline ran)
| Metric | Before | After (if fixed) | Notes |
|---|---|---|---|
| Dedup rate / Fill rate / Records | … | … | |

## Branch & merge triage (FULL / repo-level review with open branches; else N/A)
Detected model: <trunk-based | GitHub flow | GitLab flow | git-flow> → target <main|develop>.
Coverage: <N local + M remote branches; PR state via gh | unverified: no forge auth>.
| Branch | Last commit | State | Unique commits | Open PR | Recommendation | Command |
|--------|-------------|-------|----------------|---------|----------------|---------|
| feature/x | 3 days ago | unmerged, ready | 4 | none | Open PR → develop | gh pr create -B develop -H feature/x |

_One illustrative row only — the canonical column shape, the `0*`/`unverified` footnote, and the full worked example live in `branch-and-merge-hygiene.md` § Triage table; do not duplicate them here._
(Routine cleanup batched here as one Low/Info finding; consequence branches —
unmerged security fix, only-copy work — escalated in the findings table above.)

## Decisions needed (owner)
- <question> — needs <role/owner>.  (Includes any design-altering a11y/UX change.)

## What's good
- <brief; what to keep / what was done right>

## Going-forward roadmap (stage-calibrated; not a second findings table)
Sequence the findings **already listed above** by what to do for the current
`STAGE` — an ordering, never a copy:
- **Now (blocks at this stage):** <finding IDs whose severity gates here>.
- **Next (before the next stage):** <IDs tracked now, due as the project matures>.
- **Skillset to adopt going forward:** run `./install.sh --recommend <target>` and
  name the overlays it returns (delivery / critic / comms / contribution) — point,
  don't restate. Whether the repo is ready for an agent to work in it well:
  `role-coverage.md`'s agent-readiness lens.
- **Infra & docs evolution for the next stage:** what the project's infrastructure/architecture and
  documentation should become at its next stage — `infra-evolution-by-stage.md` and
  `docs-evolution-by-stage.md` (the stage-evolution inputs `SKILL.md` routes here).
- **Development direction (grounded in the code):** ≤ 3 evidence-backed moves for
  this stage — e.g. "consolidate the three half-built features before adding a
  fourth", "set module boundaries now if the team is about to grow" — each citing
  a `file:line` or a named signal. Anything needing market, financial, or org
  context the repo cannot evidence goes under **Decisions needed (owner)**, not
  invented here.

## Standards imprint (Phase 6, if opted in)
- <what was added/merged into AGENTS.md (and peer pointers) / gates / templates,
  or "not requested">

## Human-readable report (default out-of-tree; in-repo on request)

Alongside the machine-actionable report above, produce a **plain-language report a
non-technical reader can act on**. It goes out-of-tree by default (`~/Downloads/`,
session scratch, or the PR comment); on the user's explicit request — and only on
an unshared, idle checkout — write it into a top-level `code-review/` directory
(create it if absent) so it is easy to find from the repo root, using a dated file
plus an index so history is preserved and nothing is overwritten. On a public
remote, apply Phase 5's disclosure limit: IDs, severities, and areas only. A
worked fictional example (machine + plain-language, with `CORROBORATED` /
`latent`) lives in `docs/example-review-report.md` in the skill repository, copied
to `references/example-review-report.md` by `install.sh`.

- `code-review/README.md` — index: one line per review (date · verdict · link).
- `code-review/review-YYYY-MM-DD.md` — the report for this run.

This output is additive and reversible (a new dated file); it never edits code.
Keep the language jargon-free — explain each risk as *what could happen*, not as
a CWE number — and link each item to its technical finding ID so an engineer can
jump to the detail. Relative links in this file resolve **from `code-review/`**
(e.g. `../docs/x.md`), and a new top-level dir must satisfy any doc-link gate.
Scrub **third-party proper nouns** too (public event/conference/product names are
usually not on a derived deny-set, so they pass the privacy gate but still leak
context) — keep committed findings generic. **Branch names and PR titles are an
identifier vector** — real ones carry client names, ticket IDs, and personal
prefixes (`feature/acme-integration`, `jane/wip-payroll`); generalize them in the
committed report (`feature/<redacted>`, "the client-integration branch") and keep
the raw branch/PR triage in the session output, which is not committed. After
writing, run the project's privacy/name gate over this file (Phase 5).

Template for `code-review/review-YYYY-MM-DD.md`:

```
# Code review — <project>, <date>

## In one line
<🟢 Healthy | 🟡 Needs attention | 🔴 Not ready to ship> — <one plain sentence>.
<If the project has two risk surfaces (e.g. what runs today vs. a switched-off
part), give one status for each — e.g. "🟡 what runs today · 🔴 before turning on
<the part>".>

## What this project does
<one short paragraph in plain language: the problem it solves and how>

## Health at a glance
| Area | Status | In plain words |
|---|---|---|
| Security | 🟢/🟡/🔴 | <e.g. "Strangers cannot reach other people's data" or "…they can — fix first"> |
| Correctness | 🟢/🟡/🔴 | <does it produce the right results?> |
| Data quality | 🟢/🟡/🔴 | <is the data real, and never overwritten with something worse?> |
| Speed & cost | 🟢/🟡/🔴 | <fast enough, and not paying for repeated/needless work?> |
| Reliability | 🟢/🟡/🔴 | <does it recover from errors without losing or corrupting data?> |
| Tests | 🟢/🟡/🔴 | <is it checked automatically so a change can't quietly break it?> |
| Documentation | 🟢/🟡/🔴 | <can a new person understand, set up, and run it?> |

## The most important things to fix (plain language)
1. **<plain-language title>** — what could go wrong, in human terms, and why it
   matters. *(Technical detail: F1.)*
2. …

## What's already good
- <what to keep — credit the things done right>

## What to do next (for where this project is)
<plain language: the 1-3 things worth doing now for a <prototype / mvp / growth /
mature> project, and what can safely wait until it grows — so the effort matches
the stage instead of over-building a prototype or under-hardening a live product.
Anything needing your business judgement is under "Decisions we need from you".>

## Open work to tidy up (if there are leftover branches)
<plain language: how many unfinished/leftover branches exist, and what should
happen — e.g. "8 are already merged and safe to remove; 1 holds an unfinished fix
that was never shipped; 1 exists only on one machine and should be backed up." A
short "clean up / finish / decide" list, not the technical commands.>

## Decisions we need from you
- <owner decision — includes any fix that would noticeably change the current
  look/design, so you can point to a style guide or say it's a prototype>

## If nothing is fixed
<the practical risk in one or two sentences — data loss, a breach, a growing
bill, users blocked>

## How to read this
🟢 fine · 🟡 improve soon · 🔴 fix before shipping. The full technical report,
with exact file locations and fixes, is in <the findings above / the PR / link>.
```

---
