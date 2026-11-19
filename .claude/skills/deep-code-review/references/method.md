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
radius order.

**On a `DIFF` or `FILE`, read `method-diff.md` before walking domains:** hunk-kind depth, the intent-conformance lens, the count-invariant for a claimed add or remove, the sweep-scope-issue diff, the retired-coverage check for a rewritten browser spec, and the fix-completeness sweeps. Skip it on a `FULL` review of a whole repo.

**Stated invariant / landed guard → bypass census:** when a module
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

**Lenses: read `method-lenses.md` when** a call site may have bypassed or re-derived a shared helper, component or predicate, or a new or changed correctness-bearing unit (a calculation, state transition, parser or boundary) has no test that reaches it (the Phase 3 disposable probe). Two stubs fire without a prior suspicion, because the lens cannot trigger itself:
- Comment-mining: on a `FULL` or `FILE` review where the repo has a shared `components/`, `ui/` or `lib/` dir, grep `instead of|not using|hand-rolled|workaround` next to an import or shared symbol; each hit is a bypass finding. Procedure in `method-lenses.md`.
- Canonical predicate: whenever the repo has a shared boolean helper (`isX`, `hasX`, `canX`), grep for a count, badge or percentage that re-derives it inline from a subset of its fields. Procedure in `method-lenses.md`.

**Product UI (domain P) → rendered route sweep.** On a `FULL` or broad-`DIFF`
review of a product UI, enumerate every route and rule domain P on each across the
render matrix, reporting coverage as a ledger — the domain-P analogue of Phase 3's
anonymous-GET sweep, and the step that turns per-route rules into whole-product
coverage. Procedure and the matrix: `references/ux-sweep.md` (*Rendered
route sweep*). A route not rendered is `unverified`, not clean.

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

For untested correctness-bearing logic, author a disposable probe in the throwaway worktree: procedure in `method-lenses.md`.

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
only when that search returns clean — a zero-survivor check, principle 2). `scripts/fix_class_gate.py` gates only a pinned test per fix commit (or a `No-Test-Reason:` trailer), never class completeness.
When the target is a fix scoped to a named list or justified by parity with a sibling, `method-diff.md` holds the completeness sweeps.
Also identify
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
requirement is the intent-conformance finding (Phase 2, `method-diff.md`), not a refutation of it.
Re-reading the source the finder read cannot catch this class — the source looks
exactly as described; only the tests and the suite encode **design** intent (the
*stated-request* intent lives in the PR/issue — the intent-conformance lens in `method-diff.md`), so locate the
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
  a known-vuln dependency's path is its advisory's impact plus a verified unauthenticated or self-signup route to the vulnerable call: one request crashes/hangs the process = High, volume/leak only = Medium, known-exploited = Critical/High;
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
