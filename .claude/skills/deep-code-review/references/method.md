# Review method — phases 0–6

Read this when executing a review: after stating `SCOPE` / `START_SHA` / `COVERAGE_LEDGER`, work the phases in order. This file holds the full phase procedures. `SKILL.md` keeps the map, principles, and gates.

## The review method

Work the phases in order. Skip a phase only when it provably does not apply, and
say so.

**Phase 0 — Map the target.**
- **Pin the review surface first.** On a git checkout: `START_SHA=$(git
  rev-parse HEAD)`; state it in the first-response line. Prefer reading via
  `git show $START_SHA:path` (or a dedicated worktree at that SHA). For `FULL`,
  default to a **dedicated `git worktree` or throwaway clone** so a concurrent
  agent cannot change what you are reading mid-review. **Detect a
  shared/mutating checkout:** run `git status --porcelain` twice a few seconds
  apart; note `git rev-parse --show-toplevel` vs any other agent working trees
  you can see. If the tree is dirty with unrelated in-flight work, or status
  changes between checks, treat it as occupied — use the worktree/clone and do
  not plant probes or write deliverables into the live tree.
- **Establish real history depth — never trust a prose claim.** Run
  `git rev-list --count HEAD` and `git log --oneline -5` (and
  `git rev-parse --is-shallow-repository`). A README that says "single commit /
  no history" while the count is large is a docs finding; more importantly it
  changes remediation (a tree scrub does **not** clean prior commits — secrets/
  PII in history need rotation + history remediation as an **owner decision**,
  not a silent filter rewrite). Cross-ref domain S / Q and principle 2.
- Entry points, pipeline stages, request/data flow (sources → processing →
  sinks), external dependencies, and trust boundaries (where untrusted input
  enters). Inventory every `TODO`/`FIXME`/`HACK`/`XXX`/"pending"/"temporary"
  marker in code **and** docs. **On a FULL / repo-level review (or when the
  request names branches or cleanup), also inventory the open branches and their
  merge state** — refresh first (`git fetch --all --prune`; an un-refreshed clone
  hides open work), then list branches with their last-commit age, ahead/behind,
  and any open PR — the raw material for the branch triage (domain S;
  `references/branch-and-merge-hygiene.md`). Skip this for a narrow `DIFF`/
  `FILE`, which stays a compact packet.
- Detect language(s), frameworks, build system, package manager, test runner, CI.
  State in one paragraph: what problem this code solves and how. For anything
  with a network or untrusted-input surface, sketch a **trust-boundary table** —
  `untrusted input → who can set it → what validates/authorizes it → what it can
  reach`; rows that reach money, writes, or secrets with an empty validation
  column are the adversarial pass's starting list. **Three enforcement rows are
  mandatory** (do not collapse them): (1) what the **host platform** claims to
  enforce (docs, portal, edge product); (2) what **this app's code** actually
  enforces; (3) what **preflight/CI** asserts (anonymous `200` on a
  data-bearing route is a **finding**, not a green check — it encodes the hole as
  health). Platform docs that call something "personalization" or "member
  context" (or similar) are **not** authorization unless the app proves it. For
  embedded / iframe / portal-hosted apps, also complete the **Identity Arrival Map**
  in `references/appsec-edge.md` (document vs XHR vs bare curl) **before**
  proposing any gate.
- **Abuse row (optional, high-yield).** For trust-boundary rows that reach
  **money, writes, or secrets** — and only those — add six cells naming who could
  **Spoof / Tamper / Repudiate / Leak / Flood / Elevate** through that row, one
  short phrase each or `—`. Six cells on three rows beats a full threat model
  nobody finishes; the empty cells are the questions Phase 3 answers. Depth on
  the design-level version (the full STRIDE walk, residual risk) lives in
  `references/threat-modeling.md`.
- **Banned remedies from recent reverts.** Scan recent history for auth /
  middleware / gate outages that were rolled back, e.g.
  `git log --oneline --grep='Revert' -i -20` and subject matches for
  `auth`/`middleware`/`gate`/`access`. **Also hunt gates that were deleted rather
  than reverted:**
  `git log --diff-filter=D --oneline -- '*middleware*' '*auth*' '*guard*' '*authz*'`
  — a gate path that once existed and no longer does is itself a **banned
  remedy**: do not propose re-adding it until the removal's root cause is
  named and addressed (the deletion is evidence the shape failed here). Treat
  reverted approaches the same way unless the revert message's root cause is
  explicitly addressed in the new proposal. **Cite the output in
  `REVERTS_CHECKED`** (commits, or `NONE`) and record the concrete rejected
  approaches in **`BANNED_REMEDIES`** (or `NONE`) — a reviewer who only reads `HEAD`
  (no middleware file) otherwise re-recommends the exact fix that already caused
  an outage. **Read the revert *body*, don't just count the revert** — one authored
  by whoever shipped the failure often states the root cause and the **invariant it
  establishes**; carry both forward as design constraints, since a new remedy that
  contradicts the invariant is the banned one in different clothing
  (`references/parallel-audit.md` carries it into fan-out as `REVERT_INVARIANTS`).
- **Triage-first (cheap, before fan-out).** Run the project's own
  `doctor`/preflight and any documented invariant checks; grep/scan the
  invariants the project itself claims; note obvious exposure (world-readable
  static dirs, unauthenticated health that leaks config). For networked apps,
  run the **anonymous GET sweep** early (`references/security-appsec.md`) —
  highest-yield catch for world-readable data routes. Report what these
  surface immediately — they often yield a large share of final value and scope
  the expensive Phase-2 fan-out. Then order the remaining audit by blast radius
  (Review mechanics).
- **Emit the coverage ledger** (the `COVERAGE_LEDGER` promised in the first
  response) before any domain work: the resolved archetype; which of domains
  **A–W** apply and which are N/A with the one-line reason; the `references/*.md`
  files this target **must** load; and whether an **anonymous GET sweep** and a
  **two-principal object-swap** are planned (`Y/N` each, with the reason for any
  `N`). **When the audit fans out, the ledger also tracks, per unit, who covers it
  — finder id *and* lead-read `Y/N`** — so a stall is visible (`references/parallel-audit.md`
  unit manifest). **Phase 5 reconciles the report against this ledger** — a domain
  the ledger called applicable but the report never rules on, or a fan-out unit
  whose finder never completed, is `unverified`, not a silent omission.
- **FULL on a large target: rank, append, checkpoint.** Before reading a line,
  rank the coverage ledger's domains by **blast radius**: money/billing, then
  auth/authz, then data-loss (deletes, migrations, unbacked writes), then
  secrets/config, then the rest. State a **per-run budget** in the
  first-response block (`BUDGET: <tool-calls|tokens> cap N`). **Append each
  area's findings to the out-of-tree report file as it finishes**
  (`report-format.md`) — never hold to Phase 5. **At 80% of budget**, stop new
  domains, write the partial report's reviewed/unreviewed ledger, and hand
  back cleanly.

**Phase 1 — Establish ground truth.** Install/build with the documented steps;
record every deviation (a broken "one-command setup" is a finding). **Run the
project's own one-command aggregate gate by name** (`make check` / `npm run
verify` / …), not a hand-picked subset — and **never record a gate as clean
without confirming its exit code**; empty output is not a pass. **A pipe reports
the last stage's status, not the gate's** — capture then read `$?`, or the gate is
`unverified` (`gate | tail`, SIGPIPE `141`, `grep -q` inversion:
`references/language-stack-redflags.md`). **Never `2>/dev/null` a fact-establishing
step** — it turns "does not exist" into "clean" — and a gate that would "look
passed" if absent is itself a finding. Run the full test
suite (pass/fail, coverage, skipped/flaky), linters, type-checkers, formatters,
and any wired security/dependency scanners. Then, before trusting "green":
- **Enumerate what the gates exclude, and audit it separately.** Read the
  lint/type/test/CI config for `exclude`/`ignore`/path-filter entries and any
  nested project with its own manifest; run each excluded subtree's own gate or
  state it has none. Report coverage **per subtree** (`root: N pass (excludes
  X)` + `X: M pass (separate gate)`) — never an unqualified "tests pass" when any
  code is gate-excluded. "Green root gate + excluded privileged subtree" is a
  finding in its own right: coverage gaps concentrate where risk does.
- **Prove each gate can fail.** Confirm the gate actually runs in CI, then —
  **by default in a dedicated throwaway worktree/copy at `START_SHA`** (never
  plant into a working tree another process can commit from; a verified-clean
  live tree is allowed only when you have confirmed the checkout is unshared and
  idle) — plant a minimal defect it should catch (a throw, an undefined
  identifier, a banned string, a format break), confirm it goes **red and the
  reported count/exit changes**, then revert and **confirm the revert**. (This
  transient, self-reverting probe is one of the dedicated-worktree probes the
  read-only default permits — principle 7.) A gate that stays green on a planted defect is a
  **Blocker/Critical reported before any code finding** — it invalidates the
  ground truth everything else builds on. **Planted-defect matrix (config
  gates):** exercise at least (a) **missing** config, (b) **empty /
  whitespace-only** config, (c) **wrong** config (wrong pattern / stale path),
  and (d) config that **excludes the path under test**. "Missing file fail-closed"
  does **not** prove empty-file fail-closed — empty banlists and blank allow-lists
  are a common silent green. Trace which test files the gate actually invokes;
  tests present but unwired are "decorative" (procedures:
  `references/testing-and-evals.md`).
- **A gate reports only on the scopes that actually ran — a skipped scope is
  `unverified`, not clean.** A pass is evidence only where the enforcing surface
  could **see** the artifact it checks (`full-map.md` principle 2). A multi-scope gate
  that **skips** a scope whose input is absent — a privacy gate whose *identifier*
  scan needs a pattern list (`.banlist.local.txt`, a `PRIVACY_BANLIST_EXTRA`) and,
  when it is missing, runs only the *secret* scan yet still exits 0 — has not
  cleared the skipped surface. Read **which scopes ran**, not the bare exit code; if
  the gate prints only a pass, missing per-scope reporting is itself the gap. A
  green privacy exit with the identifier scope skipped is **not** "boundary clean":
  a status claiming it is over-claims a **trust-critical** surface — rate the
  *claim* **Critical**, not the gate. Same shape as the empty-banlist silent green
  above — the check ran, but not over the thing you needed cleared.
- **A green gate clears only the surface it enumerated — not one it never
  visited.** A gate that ran and passed proves something about the routes,
  states, and inputs its coverage set actually reached; a surface it never
  enumerated (a route the sweep never requested, a state no fixture constructed,
  a branch no test input exercises) is `unverified` under that green, not clean.
  (A gate the config *declares* excluded is a different gap — enumerate those per
  the gate-exclusion bullet above; this is the surface nothing pointed at.) Read
  the gate's coverage set and confirm it **includes** the surface in question
  before reading its pass as a clearance — full-map.md principle 2 (*an absence is
  evidence only after a positive control fires*) at gate-coverage scope. This is
  the **unvisited** surface: distinct from a gate that cannot fail (above) and
  from a probe that observed the wrong thing (detector fidelity, `method-situational.md`) — here
  the gate fails correctly, it was simply never pointed here.
- **Read the host CI, not only your own shell.** Fetch the base branch's latest
  pipeline conclusion (`gh run list --branch <base> --limit 5`, or the forge
  equivalent); "green locally" is not "green in CI" (different OS image, browser
  binaries, gate set). A red, unexplained base is `unverified` ground truth — say
  whether it is a flake, pre-existing and unrelated, or caused by this work — and
  you cannot show a change "regresses no axis" against a baseline already failing.
- **A green names the commit it graded.** Before citing any green or CI status, confirm its SHA is the reviewed head; a re-run re-dispatches the original payload SHA, so a green on another commit is `unverified` for the head.
- **Guarantee claims need pins.** List the guarantee-bearing comments, docstrings and UI strings in the diff; name each one's pinning test; an unpinned guarantee is a finding. Depth: `method-situational.md` claim-vs-code lens.
- **Before trusting a gate, or fixing code to satisfy one:** check the gate against its cited standard, and run it twice (idempotence). Depth for both: `method-situational.md`.
- **Situational Phase 1 checks — `method-situational.md`.** Load it on every `DIFF` and when a firing gate may be stricter than its standard, a gate-aimed fix or a production-build finding must be reproduced, a no-regressions gate keys on labels or positions, a verify gate writes artifacts a later step reads, local and CI disagree or a failure appears only in a reduced worker config, the target is containerized or serverless, the task builds against an exported reference, or the target has native C/C++ or `unsafe` Rust. Also load when a lint/SAST green is cited as clearing a defect class, the diff edits an enforcement artifact (gate, CI, hook, checksum script), any green, CI status, re-run, or coverage figure is cited, a finding is carried from an old SHA, the target carries a suppression list or baseline ratchet, or gates run per lane, module, or flag; also before filing fan-out findings or seeded second pass; on a `FULL` review also its composition, effective-config and rule-to-enforcement checks; on a `DIFF` also its size bands, shared-state blast-radius trace, and transition checks.

**How much ground truth the scope owes** (don't run a `FULL` gate ritual to
review ten lines, and don't skip it on a repo):

| Scope | Gate work owed |
|---|---|
| `FULL` | The whole matrix above: aggregate gate by name + exit code, per-subtree coverage, and the planted-defect probe (missing / empty / wrong / path-excluding config). |
| `DIFF` / `FILE` | Run the tests that **cover the changed paths**, and read the **CI path-filters** for those paths — a change under a filtered-out path is effectively ungated, which is a finding. **Plant only when the gate itself is what changed**; otherwise state the probe as out of scope. |

**A tool-produced count is a floor until you check for a cap.** Before quoting a
count a script emits, grep the script for a `limit`/`slice`/`head`/`take`/`break`
or early return on that collection and label the number `>= n` when one exists —
an instrument that stops recording at six reports six, not the total (distinct
from the caps *you* impose).


If a pipeline/app exists and running it is cheap, safe, and non-destructive, run
it and capture the **before** output for a later quality-delta. Never touch paid
APIs or production data without approval. Anything that won't build, test, or run
as documented is a Blocker until proven otherwise.

**Phase 2 — Domain audits.** Walk every applicable domain section (A–W). For
each, produce findings with `file:line` + impact + fix. Load the domain's
`references/*.md` for detection procedures. Domains that don't apply are marked
N/A with a one-line reason. Start from Phase 0's triage-first hits and blast-
radius order. **On a `DIFF`, classify each changed hunk by *kind* before walking
domains — the PR's title and line-count are not the review's depth budget.** Bucket
the change into **mechanical** (a rename, a format-only reflow), **behavioral** (logic
changed on an *existing* path), and
**new-surface** (a brand-new route / endpoint / handler / consumer / permission — a new
trust boundary), and route each at matched depth: a mechanical hunk gets a fast
*confirm-it-is-mechanical* read (no behavior rode in on the rename — a moved guard, a
flipped default, a widened type); a behavioral hunk gets the full domain audit for the
paths it touches; and a **new-surface hunk gets the full Phase 3 adversarial opener set
(below) — every opener, not a subset (the dual-surface caller check is the one most
easily skipped) — regardless of the PR's stated size or title** — a new endpoint buried
in a PR titled "refactor" is both the highest-risk change and the easiest to wave through
at the diff's face value. The bucket, not the PR's framing, sets the depth. A hunk that
fits none cleanly — a pure deletion, a test-only or config-only change — defaults to the
**behavioral** read (toward more scrutiny, not less). (Distinct from Phase 0's blast-radius
*ordering*, which ranks what to review *first*; this sets what *depth* each hunk earns.)
**Multi-file or contract-changing `DIFF`: out-of-diff tracing is mandatory** (`method-situational.md`:
`impact_map.py`, `context_pack.py`).

**Intent-conformance — a lens distinct from correctness.** Besides "is the
code right," ask "does the change do what it *claimed*": does the diff satisfy its PR
description, linked issue, or stated acceptance criteria? A flawless implementation that does
X while the ticket asked for Y, or silently drops a stated requirement, is a finding — cited
to the **stated intent** available in context (the PR / issue text), and where no intent is
stated, say so rather than infer one. This is the review-side counterpart to the delivery
spec gate (`agentic-delivery` G1); it catches a whole class the domain audits, which ask only
"is it correct," miss. **Count-invariant for a claimed add/remove:** a diff that says it
*adds* an item — a list entry, a `case`, a config key, a test — is falsified by an unchanged
count. `git show <base>:<file> | grep -cE '<item shape>'` against the working copy must move by
the number claimed; a delta of **zero on an "add"** means the new text was spliced into an
existing item and silently **replaced** it (two items fused into one), and the mirror case
falsifies a claimed removal. The bytes stay valid, so lint, format, and checksums pass over the
fusion — only the count delta or a human read catches it (this review's own worked near-miss). **Stated invariant / landed guard → bypass census:** when a module
states an invariant or a guard lands on one path, inventory callers/entry points
that can skip it (procedure: `references/security-appsec.md` for untrusted egress;
`references/data-quality.md` for artifact→consumer). When the target is large,
run these as parallel one-invariant audits under the contract in
`references/parallel-audit.md` — read-only toolset, pinned `START_SHA`,
identifier masking — and re-verify every subagent finding at source before it
enters the report. **Concurrently with the fan-out, the lead reads the top-N
highest-blast-radius files independently and adversarially** (N sized to the
target; Phase 0's triage ranks blast radius) — so a hardened, zero-survivor
fan-out still has a **non-empty confidence basis**, the finders' empty returns are
cross-checked by a second independent read, and a slow or stalled unit never leaves
the highest-stakes surface unread. Phase 5 reports this lead-read coverage
alongside finder coverage. **A refused delegation is not a blocked domain:** if a
specialized subagent rejects a free-form domain prompt (fixed prompt shape,
single-shot, wrong review type), immediately retry **once** with a
general-purpose subagent or run the audit in-process — under the same read-only,
pinned-ref contract — and note the substitution. Never let a harness's prompt
contract stall **A01/domain B**; the fallback is the audit, not a skip. Depth:
`references/parallel-audit.md`.

**Mine the code's own comments for admitted deviations — a class of finding a
structural search cannot reach.** The drift searches elsewhere in this method key on
*structure*: a duplicated component, a copied string or markup block, a repeated
scaffolding cluster (`ux-components.md`'s *one component per concept*
twin-search), or the inverse sweep that greps a hand-rolled `aria-modal` / skeleton and
diffs it against the shared primitive's importers (`a11y-focus.md`, `a11y-live.md`). All of them are
blind to a call site that **reimplemented** a shared component/helper/guard from
scratch and therefore shares no literal with it. But a developer who deliberately
bypassed a shared abstraction often **says so in a comment** — *"not using the shared
`<Select>`, it can't do X"*, *"hand-rolled instead of the DS modal because …"*,
*"inlined the fetch, the shared client doesn't fit here."* Grep those admissions as
their own pass — the phrasings cluster around a small set of tells (`instead of`, `not
using` / `not the shared`, `can't use`, `rather than`, `hand-rolled`, `workaround`)
sitting next to an import or a shared symbol's name — because each hit is worth **two**
findings at once: (1) this call site has drifted from the shared abstraction and may
have shed whatever correctness the shared version bakes in — an a11y behavior, a guard,
a dedup — the exact regression `a11y-live.md`'s bypass-the-shared-component family
names; and (2) the shared abstraction has a **real gap** its author already hit, so the
root-cause fix (principle 9) is usually to close that gap at the source rather than
bless the workaround. It is higher-confidence than a cold duplicate search because the
author **pre-verified** the deviation for you: the comment is a first-party admission
that the shared path did not fit. **Opposite polarity from the two other
comment-as-claim rules in this method** — the carried-forward suppression-reason (Phase
1, `method-situational.md`) and the incident-narrating comment (Phase 4) warn you *not to over-trust* a comment
as still-true; this *harvests* a class of comment that **is** a finding you would
otherwise miss. And distinct from `ux-components.md`'s adoption-is-total move,
which reads the **shared component's own** doc-comment (it names the call sites it
fixed) to hunt stragglers — this reads the **call site's** comment to find the bespoke
bypass that never touched the shared component at all. Treat a match as a finding to
confirm at source (read the workaround; confirm it still bypasses the shared thing at
HEAD), not as proof on its face — the comment may itself have drifted, per the Phase 1
rule (`method-situational.md`).

**Diff every ad-hoc re-derivation of a *canonical* predicate against the canonical — a
partial reimplementation reads real fields yet tests a *subset* of the conditions.** A
specific, high-frequency case both the comment-mining pass above and the copyable-idiom
sweep (Phase 4) miss: the project **correctly centralizes** a boolean — *is this fully
configured / wired / eligible / complete* — in one shared helper that legitimately requires
**A and B** (`isWired = x => x.hasKey && x.hasWebhook`), but somewhere else a **count,
filter, badge, or percentage** re-derives the *same* concept inline and implements only
**part** of it (`items.filter(x => x.hasKey).length`, dropping `hasWebhook`). Every field it
reads is genuine and the code looks right in isolation; the only symptom is that a
**user-facing count/percentage silently disagrees with the canonical predicate** — the
dashboard says "8 of 10 configured" while the helper that actually gates behaviour counts 6.
A grep for the *idiom* (Phase 4) will not find it — the re-derivation shares no literal with
the helper — and no comment admits the bypass (the comment-mining pass above), because the
author did not think they were bypassing anything; they re-expressed a "simple" check.
**Technique: start from the canonical predicate, not from a duplicated string.** Enumerate
the fields/conditions the shared helper reads (`hasKey`, `hasWebhook`), then grep every site
that reads **any** of them in a boolean/count/filter context and diff its condition set
against the canonical's — a site that tests a **proper subset** is the finding. **Fix: call
the shared predicate; never reimplement a subset of it** — a count over
`items.filter(isWired)` cannot drift from the gate. **Adjudication vs the nearest rules:**
distinct from `testing-situational.md`'s *diff-the-guard-conditions-across-N-sibling-copies*
(that has **no** canonical — N peer copies drifting from one another, fixed by reconciling or
extracting them; here a **designated canonical exists** and the bug is one **narrower**
re-derivation of it, fixed by calling it); distinct from a **value-set** subset (a data set
missing members, not a predicate missing a conjunct); and distinct from the
**audit-every-implementation** sweep (Phase 4, which fans a fix across every call site of one
function — here the re-derivation is **not** a call site of the helper at all, which is
exactly why a call-site audit skips it). It is the **structural-search complement** to the
comment-mining pass above: that pass catches a bespoke reimplementation via the developer's
*admission comment*; this catches one that shares neither a literal nor a comment, by keying
on the **fields the canonical predicate reads**.

**Sweep-scope issue → enumerate the target set, diff it against the files touched.** When an issue's
scope is a sweep ("every page", "all mentions", "each handler"), do not accept "closes #N" on the
author's say-so: enumerate the target set yourself (a route list, a directory glob, a grep) and diff it
against the files the change touched. Any target not touched is a finding, or an explicit,
reasoned exclusion in the PR; the issue stays open for the remainder. A lane that covers 7 of roughly 20
pages and reports "done" is the failure this catches. Same discipline as **audit-every-implementation**
(Phase 4), applied to the issue's stated scope instead of one function's call sites.

**Product UI (domain P) → rendered route sweep.** On a `FULL` or broad-`DIFF`
review of a product UI, enumerate every route and rule domain P on each across the
render matrix, reporting coverage as a ledger — the domain-P analogue of Phase 3's
anonymous-GET sweep, and the step that turns per-route rules into whole-product
coverage. Procedure and the matrix: `references/ux-sweep.md` (*Rendered
route sweep*). A route not rendered is `unverified`, not clean.

**Rewritten browser spec → account for the retired coverage.** When a `DIFF` rewrites an
existing browser/E2E spec because its target surface became unreachable in the test
environment, do not pass the rewrite on its new-surface green: check that the coverage
the old spec provided is named as a gap and pinned by a source-level structural fallback,
and flag its absence as a finding. Procedure: `references/testing-ui.md` (*A
rewritten browser spec names its retired coverage*).

**Phase 3 — Adversarial / red-team pass.** Switch to attacker mindset (the
openers below). For any networked app, work these **openers in order** before the
creative attacks — they are ordered by yield, and each one narrows the next:
1. **Anonymous GET sweep** — every documented GET with no cookies and no Bearer;
   flag every large or identity-bearing `200`.
2. **Two-principal object-swap** — authenticate as A, request B's object ids; a
   `200` is IDOR regardless of how the UI hides it.
3. **Dual-surface every caller of the same loader** — the API handler *and* every
   RSC/SSR page/route that calls it; one redacting while another does not is the
   common shape.
4. **Then** injection, SSRF, traversal (path-serving/archive sink — `references/appsec-files.md`), prompt
   injection, exhaustion, races.

Procedures for all four are in `references/security-appsec.md`. Then actively try
to break auth, inject, exfiltrate, exhaust, poison, and to find useless/costly
work. Assume a hostile user **and** a hostile upstream.

**Beyond the security openers, author a disposable probe test to *discover* an
unsuspected defect in changed logic — do not stop at the tests that already exist.**
Each dynamic move so far leans on something already present: the planted-defect
probe (Phase 1) mutates code to prove a *gate* catches a *known, injected* defect;
fix-verification (Phase 4 below) runs the *existing* suite against a *suspected*
finding; the openers above attack a *running* security surface. None exercises a
new or changed **correctness-bearing** unit — a calculation, a state transition, a
parser/validator, an off-by-one boundary — when no test reaches it. For such logic,
write a **minimal, disposable** test that calls it at its stated boundary conditions
in the same throwaway worktree at `START_SHA` the planted-defect probe uses — the
same transient-worktree-probe mechanism principle 7 permits, never the working tree.
As Phase 1 reverts and confirms its planted defect, **delete the probe and confirm it
is gone** when done, so no unprompted write is left standing. A
**red** result is a finding with a real repro attached — a stronger claim than a
static read. A **green** result records only *"no defect at the inputs probed,"*
with the probe and its inputs; it is **not** an invariant, and is promoted to a
`checked_sound` / *Invariants verified to hold* row (`report-format.md`) **only if
the test pins the property** across the input class, not one example. **Bound the
blast radius before you run it:** the throwaway worktree contains *filesystem*
effects, not *outbound* ones — if the unit cannot be exercised without a network,
paid, or stateful call (a payment or model-calling handler, a live DB write),
**stub that boundary or skip**, and record `could-not-check` (distinct from
found-nothing) rather than fire a real side effect to get a result. The
confirm-before-billable-or-shared-state caution and the could-not-check-vs-found-nothing
discipline bind the reviewer's own probe, not only the target's gates.

**Phase 4 — Synthesize & rank.** Deduplicate, assign severity, separate blocking
from non-blocking. Note systemic patterns (one root cause behind many symptoms)
rather than listing every instance. **A finding matching a copyable idiom** — a guard
expression, a state-check, a data-flow pattern pasted rather than abstracted
(`disabled={!x}`, an unchecked identity flag, a hydration-gate) — is scoped by **grepping
the idiom across the tree in the same pass**: the search result *is* the blast radius,
reported as one class-finding with its full instance set (how many sites, and where),
never the first callsite alone. Stopping at one site under-scopes the finding and leaks a
second fix into a later increment — the review analogue of the *one component per concept*
duplicate-twin sweep (`ux-components.md`), for a bug pattern rather than a duplicated
component; after the fix, a re-grep of the idiom confirms none remain (the class is closed
only when that search returns clean — a zero-survivor check, principle 2). `scripts/fix_class_gate.py` gates only a pinned test per fix commit (or a `No-Test-Reason:` trailer), never class completeness. **A fix that already scoped itself to an
enumerated list is judged against that list — but a green test pinning the list proves
non-regression, not completeness.** The same class discipline runs in reverse when the
fix is the review *target*: a change that lands as *apply treatment T to instances
[named list]* — the routes a bug report named, the handlers an investigation walked —
ships a regression test over exactly those entries, and that test can only prove the
**named** instances do not regress; it is structurally incapable of proving the list
complete against the rest of the tree (the *a green gate clears only the surface it
enumerated* rule above, at remediation scope). The report enumerates the symptoms
someone hit — a **sample** of the qualifying shape, not its population — so re-derive the
shape precisely (a shared wrapper, a fetch shape, a missing guard) and run the same
independent sweep this bullet prescribes, then **diff the full match set against the
fix's named list**: whatever the sweep finds that the list omits is the gap, named. Such
a fix passes intent-conformance against the ticket and is still incomplete against the
code — the Phase 2 / Phase 4 seam. Separate an **acknowledged** boundary from a
**silent** one: a *category X stays a follow-up* note is legitimate when drawn after a
full enumeration, a real gap only when the search never left the ticket; and an
**easier**-to-fix sibling skipped while harder ones were fixed is the tell of an
accidental miss, not a deliberate deferral. (The field-shape version — patching a shared
request-body builder only where reported — is `domain-h.md`.) **The same completeness discipline also runs *inward*, into the file the
fix just landed in.** The sweeps above go *outward*, across the tree — grepping the fixed idiom (or the
re-derived shape) to land every instance, then re-grepping to confirm none survive. Two routine ways
of *verifying* a hardening fix defeat that check while leaving the fixed file's own other
paths unswept — paths that hold **no instance of the fixed idiom for a grep to reach**. A
fix justified by **parity with a sibling/twin file** (*"the other handler already guards
this; this one now matches it"*) supplies no idiom to grep at all, and proves only that
the fixed file is *as broad as* that sibling — never that it lacks a **second path to the
same data or sink**: an inner helper, a self-recursive branch, or another function
independently interpreting the same untrusted input, for which a flatter sibling has no
counterpart to match. A fix justified by a **top-level/outermost guard** (an
`isinstance`/type/auth/escaping check on the whole input) closes only the outer layer —
every `.get`/subscript/`for ... in`/decode on a *field beneath* it, in **any other
function of the same file**, is a separate, still-unguarded read of that value (not the
one-function rule in `reliability-error-handling.md`, which is other throwing calls
*inside a single function*; this is other functions across the file). So after matching
the twin or landing the outer check, **sweep the fixed file itself**: grep it for every
function, branch, and nested access reaching the same sink over the same input, name each,
and confirm the new guard's *actual scope* reaches it — the class is closed only when the
fixed file's own remaining paths are accounted for, not when the diff reaches parity with
a sibling or an outer check goes green. This is the **inward companion** to the outward
instance-set/named-list sweep: that one lands the siblings a fix skipped; this lands the
fixed file's own deeper paths the *verification method* skipped. Also identify
**compounds** — findings from
different domains where one disables another's safeguard; a compound's severity
is the joint effect, which can exceed either part, so state it as one finding
with the fix order. **Distinguish a live defect from a documented past one:**
comments often narrate fixed incidents in present tense — before reporting, check
(a) is there a test pinning the corrected behavior? and (b) does
`git log -S'<symbol>' --oneline` **on the ref that governs "shipped"** (`git log
-S'<symbol>' origin/<that-ref>`) show the fix already landed? (A **bare** `git log -S`
reads whatever checkout is out — branch-blind; on a diverged repo the deploy line is a
different ref, so scope the containment check to it, `branch-and-merge-hygiene.md`.) If
either is yes, it is a historical note, not a finding. **When a review files its findings as tracked
issues, dedupe against recently-*closed* issues, not only open ones** — a finding matching an
issue closed in the last few weeks may already be fixed, so re-filing it re-lanes shipped work
and erodes trust in the tracker; search closed issues for the symbol/symptom (the route, the
guard name) before filing. But **a `wontfix` / `duplicate` / `stale` / bot-triage close is not
a fix** — check the close **reason**, and if the finding still reproduces at HEAD (`method-situational.md`'s
re-validate-the-`file:line`-still-exists check), file it anyway rather than suppress a
live defect. **Distinguish a defect from intended
behavior a test encodes:** before reporting, check whether the proposed fix would
break an existing **passing** test **present at the base ref** (`git show <base>:` — not one
the diff itself ships): a **pre-existing** test enshrining the behavior means it is intended
by design (the fix is wrong, not the code), so it is `REFUTED`, not a defect. But a test the
**diff itself adds** that encodes off-spec behavior does **not** REFUTE — a self-certifying
test is re-checked at its base (principle 2), and a diff shipping tests for the wrong
requirement is the intent-conformance finding (Phase 2), not a refutation of it.
Re-reading the source the finder read cannot catch this class — the source looks
exactly as described; only the tests and the suite encode **design** intent (the
*stated-request* intent lives in the PR/issue — the Phase 2 intent-conformance lens), so locate the
tests that exercise the finding, and for a change to security/cost/concurrency
logic apply the fix in a throwaway worktree and run the suite before confirming
(`references/parallel-audit.md` §4). **Weigh the failure direction** (fail-open vs
fail-closed) as an explicit severity axis — see the rubric below. **Snippet-or-drop:** every surviving
finding carries a **verbatim snippet re-read at the pinned ref** — `git show
$START_SHA:<file>` (or a byte dump per principle 2 when the claim hinges on
invisible characters). A finding you cannot quote at `START_SHA` is `unverified`
with the artifact named, or it is dropped; a paraphrase from memory is how a
plausible-but-absent line number reaches the report. A **quantitative** claim (a
count, a metric, a before/after delta) likewise names the ref it was measured at,
inline — "N at `origin/main`", or "in the uncommitted tree" when the working tree
is the subject; on a dirty checkout those are two different products.

**Presence and absence are not the same claim.** A **presence** finding carries its own
evidence — the file and line — and a reader checks it in seconds. An **absence** finding
("X is missing," "there is no Y") claims that *no* implementation exists anywhere, and it
is **unfalsifiable from the report alone**: the report cannot show the thing it did not
find, so an absence inherits the **searcher's vocabulary** — any capability written in an
idiom the searcher did not try reads as missing. Absence findings are the
highest-leverage and least-verified thing an audit emits, because under parallel delivery
an absence is read as a **work order** (build the missing thing), and a false absence
becomes a second, competing implementation next to the working one. So hold an absence to
a higher bar: (a) **search by behaviour, not one idiom** — enumerate the encodings a
concept can take (a focus ring is `ring` / `outline` / `stroke` / `box-shadow` / a
rendered overlay; navigation is a route / query param / hash / id-keyed overlay; state is
a class / data-attr / ARIA / component state) and grep all of them, since one pattern is
one hypothesis, not a survey; (b) **confirm the absence at runtime** — render it and look
(principle 2: *an absence is evidence only after a positive control fires*); if you could
not boot (memory pressure, no build), the finding is **`unverified` — unconfirmed-absent**,
not a gap; (c) when it leaves for a downstream builder, the brief instructs the builder to
**re-confirm the gap before building** and report back if the capability already exists;
(d) a disproven absence is **reported back loudly** to whoever holds the inventory, or the
same false gap is re-briefed to the next lane. The verification surface a finding names
(`report-format.md`, *name the procedure*) includes, for an absence, the search space it
covered.

**Perceived-absent or "broken" premises — `method-situational.md`.** Load it when a reporter calls a capability missing that the code already implements (a `delivery-gap`), or a task premise says a value is hardcoded, decorative, or always N.

**Anti-slop (drop before the report).** A finding that does not change an
owner action is not a finding. Drop or demote to Nit/Info:
- a missing community-health file on a **private** repo with no outside
  contributors (already batched in `docs-and-dx.md`);
- restyling, renaming, or "consider maybe" with no defect;
- **DIFF scope only: a gap finding scored below 80** (FULL/FILE keep pre-existing findings; an
  `unverified` security lead keeps its provisional severity). Score each 0-100 for "this change causes a real, reachable failure": 25 for
  pre-existing issues, hypothetical callers or style; 80 for a trace verified on a normal path. Report only ≥80;
  log the rest in the coverage ledger as `declined: <reason>`;
- a second copy of a fact the project's own gate already enforces and the
  review already confirmed green;
- a **settled nit** the team has already seen and declined — kept in a committed, path-scoped
  **review-calibration** record (accepted / rejected findings for this repo, in git, not a
  hosted memory service) that the reviewer reads to avoid re-raising what the owner already
  dismissed. **The record NEVER suppresses a security, logic, null-deref, or
  data-validation/data-loss finding** — those are re-raised every time regardless of prior
  dismissals; calibration silences *style/preference* noise, not correctness or safety;
- a security finding in a **chronically-noisy class** — DoS, rate-limiting,
  resource-exhaustion, generic input-validation with no reached sink, open-redirect — with
  **no demonstrated impact path**: demoted to a non-blocking `unverified`/Nit **lead** —
  reported at provisional severity that blocks only once a path is shown, not asserted as a
  confirmed High on suspicion (the *mechanism-unproven* rule applied to the classes that most
  produce false alarms; a proven impact path re-promotes it to its real severity);
- a recommendation that would break a passing test (already `REFUTED`);
- a kit leftover (`AGENTS.md` / `CLAUDE.md` still describing a scaffold
  `app/` layout while the real product lives in `apps/` or `packages/`) —
  that **is** a finding, but **one** DX finding with the smallest fix
  (rewrite the leftover to match the tree, or delete it). Do not also
  emit a wall of "add more docs" on the same files.
Chat BLUF lists **confirmed defects that would change a merge or a
ship**, not a catalogue of every possible improvement.

**Phase 5 — Report / Phase 6 — Imprint.** Procedure in `method-report.md` (read it when writing the report or imprinting); templates in `report-format.md`.

---
