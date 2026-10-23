# Migration & prototype-reference parity

Read this when the reference you are matching is a **prototype / mockup / design export** (a
static page, a design-tool frame, a clickable prototype — typically built on a handful of
seed rows), or the task is a **port / migration to a reference design**. Expands section P
of `SKILL.md`, alongside `frontend-a11y.md` (a11y correctness) and `product-ux-quality.md`
(the design half). The failures this file prevents: porting a migration screen-by-screen
with **no unified chrome** (an unbounded defect stream), over-claiming parity from the wrong
evidence, recommending the **deletion of real features** to match a sparse reference, and
shipping a UI that matches structurally yet feels poor to use.

---

## Unify the chrome/shell before porting screens — one level above component unification

The unification precondition (`ux-components.md`, one component per concept) has a
level **above** individual components: the **chrome/shell** — per-page header, tab/section
strip, stat-tile frame, sub-nav, and the rule that decides which tabs a surface shows.
Porting the *outer* frame (sidebar, top bar) to a shared component does **not** unify the
*inner* chrome: it can still split into independently-authored families — one composing the
shared header + nav-link tabs, a sibling bypassing it with a bespoke inline header (a raw
font-size, not the token) + a hand-rolled local-state pill strip. When it does, every
downstream "why is this styled differently / this has fewer sections / the strip won't
stick" complaint is one divergence per surface, "fixed" per-surface without converging. **A
per-surface migration with no unified chrome is an unbounded defect stream** — the tell that
the divergence is structural, not per-screen.

- **Enumerate the chrome primitives first, and confirm every surface renders through the
  shared ones *before* porting individual screens.** A surface that reimplements a chrome
  primitive is a **structural defect**, not a nit.
- **Align the outlier family *to* the consistent majority**, not the reverse — if two
  surfaces diverge and thirteen agree, fix the two; don't rebuild all fifteen.
- **Render the same sub-view *superset* across structurally-similar surfaces** (per-entity
  dashboards) with honest-empty states — not a hand-picked per-entity subset — so absence
  reads as "nothing here yet," not "this entity is different." **The one exception is
  load-bearing:** if a view would render a **misleading aggregate** at that scope (a
  rate/total that is wrong or meaningless for this entity), keep it **hidden** —
  **computed-not-fabricated (principle 3) beats tab-count symmetry**. Symmetry is the
  default; a hidden view is justified only by "the number it would show is wrong here,"
  stated in the finding.
- **Unify a control that exists in two *behaviors* by its styling, not by one dual-mode
  component.** A navigation link and a local-state toggle can look identical yet carry
  **different semantics** — `aria-current` for the nav location vs `aria-pressed`/expanded
  for the toggle. Extract the **styling** into one shared primitive and wrap it in two thin
  behavior wrappers; do **not** collapse them into a single component with two
  mutually-exclusive prop modes, which breaks a11y (the unwired mode emits the wrong role,
  focus, and keyboard order — `frontend-a11y.md`). This is the **complement** of the
  feature-flag rule, not a contradiction of it: a feature that is *present-or-absent with
  the same semantics* belongs **inside** the component (`ux-components.md`, one
  component per concept, #123); two *different behaviors* stay **separate wrappers over one
  shared style**.

## Own the shared shell before the page lanes spawn — one writer per shell primitive

Unifying the chrome/shell (above) is a **precondition**; the moment a multi-screen
port/restyle **fans out to parallel page lanes**, the shared shell becomes contested write
state — every lane needs the same handful of files (layout, nav, tokens, chrome primitives),
so concurrent edits **clobber or silently revert** each other's changes, invisible to a
per-PR review that passes each lane while the defect lives **between** them.

Before spawning any page lane, the lead publishes a **shell-ownership ledger** on the
integration PR — the same table shape as the fan-out **Unit manifest** (`parallel-audit.md`
§1, lead-owned, filled before spawn); do **not** restate it. Its load-bearing rules:

- **Exactly one lane owns each shared-shell path** (layout, nav, tokens, chrome primitives).
  Ownership is a **partition**, not a suggestion: two lanes listing the same shell path is
  the collision, on paper, before a line is written.
- **The shell lands first.** Page lanes branch from / rebase onto the merged shell, so they
  restyle **against** the unified chrome, not alongside a moving one.
- **A page lane editing a shared-shell path it does not own is a finding** — even when its
  diff is correct in isolation — because it silently diverges the shell the other lanes
  built on (the per-surface-divergence, unbounded-defect-stream failure this file opens
  with).

**Severity.** A restyle fan-out with **no ownership ledger** is a **High** coordination defect
(do-no-harm, principle 4 — lanes clobber the shell, invisibly until integration); a cross-lane
shell-path edit is its own finding against the owning lane. Both are **review-side**
detections; *enforcing* single-writer ownership at write-time is a delivery-overlay concern,
out of scope for this self-contained review-only rule.

## Verify parity surface-by-surface, on real data — never from a structural or seed-data audit

A structural component audit, a green test suite, and a section-by-section screenshot
comparison **over-report** parity. They miss exactly the divergences that appear only on
real data and real use: which view a route **defaults** to, whether a composer carries every
field the reference has, whether shared components are actually unified or quietly
reimplemented per page, whether a sub-view was dropped, whether live data is even populated.
Parity is verified **surface-by-surface, interactively, on real data**: for each surface,
drive the real control and diff against the reference's **actual rendered behaviour** —
default state, every field, every sub-view/mode, data population — not its static
screenshot. Treat every "matches well" as **unverified** until the real surface is exercised
against the real reference. (The structural / green-suite / seed-screenshot stand-ins are
the "Beware the proxy" completion trap — `report-format.md`.)

**"Aligned / matched / mirrored" is a two-sided claim, gated by `scripts/parity_differ.py`.**
Read this when a port, restyle, or migration is about to be called aligned to its reference:
run the differ before the claim. MATCH (exit 0) requires comparing the **rendered** design
against the **rendered, running** app, per named section and its element inventory — a page
height, element sizes, a screenshot, a token-name similarity, or a lane's self-report is not alignment and may never
be quoted as a verdict; a one-sided measurement produces a confident **wrong** pass. One side
missing or unreadable → `COULD_NOT_CHECK`, never a pass. Design-populated sections present
but empty in the app → `CANNOT_COMPARE`: seed the app's data to the design's data state first
— never condense or remove the empty sections to "match," the design wants them populated.
Extra app sections are a reported superset; a differing item fails unless owner-accepted
(`--accept`: owner-authored only — the differ checks commit authorship and prints
`MATCH_WITH_ACCEPTED`, never a plain MATCH). The
`MISMATCH` list **is** the work queue — mirror it section-by-section, and never spawn a
mirror lane for a section the differ already reports MATCH. Compare like-for-like: the
design's default view against the app's **same** view, and verify the owner's stated-priority
surface first, not whichever view the app happens to default to.

**Seed through real write paths, never a hand-edited store.** A committed, idempotent,
dev-only seed command (invocation named in the lane brief) writes each sample row through the
app's own creation flow, labelled sample, never production (chrome-vs-data rule below).
Seed identities are fictional, never the prototype's sample names; in-repo evidence is the app
alone on that data, and design-vs-app composites stay out of the repo. Text privacy gates can't
read pixels: a `binaries_gate.py` allowlist entry for a screenshot is a privacy review.
For the differ's matched-state diff of gated sections, render both sides past sign-in (one
dev identity), or its `missing` list is an auth gap, not a build order (the MISMATCH
precondition line); the signed-out default surface stays its own required check
(`rendered-parity.md`). Disclose the comparison state beside the verdict (goalpost rule, `rendered-parity.md`).

**Match the design's sample-data shape, not just its data state.** Seeding the app to the
design's populated/empty/loading/error state (above) is necessary but not sufficient — an app
seeded with a different **text length** or **item count** than the design's own sample data
reproduces wrapping/overflow that looks like a styling defect but is really "different input."
Match the design's sample-data **shape** — string lengths, row/item counts, and the same set of
states — from the design's own sample, never invented independently. This is fixture work only:
never extend it into changing the product's actual rendering logic, hiding a state, or otherwise
altering real behaviour to raise the score; any deviation from a straight fixture match is
disclosed in the finding, not concealed.

**Pin the target export first.** When a design package holds several exports of one prototype,
grep each for distinctive UI strings from the newest change-log entries; the one holding all is
the target (record it where every lane reads it), never the largest or best-named. None matches →
ask the design owner (`method-situational.md`'s stale-input rule).
Even the pinned export is **one requirement source, not the requirement set**: feedback from
other sources that it never captured is kept in the delivery ledger
(`agentic-delivery/scripts/feedback_ledger.py`). Before re-aligning to the design, run its
`accept-file`; the owner commits it as the differ's `--accept`. Send a design-vs-feedback
conflict to the owner; never settle it by re-aligning.

**Verify a served bundle is complete and current before trusting any score off it.** A
comparison harness that fetches the pinned export from a shared dev server can be handed a stale
or partially-copied bundle — an interrupted sync, an old cached build — silently skewing every
score run against it: some sections compare against pages no longer in the current design, or
against an incomplete asset set. Before trusting a run, checksum the served bundle's files against
the source export and confirm the file set and hashes match. `parity_differ.py --design-bundle-dir
<served dir> --design-checksum <sha256sum-format manifest>` enforces this in the tool itself: any
file missing, extra, or hash-mismatched refuses the whole run before `--design`/`--app` are even
read. A mismatch is `COULD_NOT_CHECK` — the same discipline as a missing or unreadable side,
above — never a scored comparison off an unverified bundle.

**Check order: foundation first, one gate — `parity_differ.py --workflow`.** Token **values**
(`token_differ.py`), then primitives (open FOUNDATION/PRIMITIVE style rows block every section:
BLOCKED_BY_FOUNDATION, exit 7), then per-section inventory (completeness = items matched, never
pixels) + computed styles, then `--report` screenshots: an earlier stage often explains a later
diff — fix, re-run first.
A section with no text `data-cs` (image/chart/map) stays UNVERIFIED unless an owner-committed accept row `visual-reviewed<TAB><section><TAB><reason><TAB><owner>` covers it.
Volatile or harness-only content (clock, ad, dev banner): mark it `data-parity-ignore`; each is listed, a design-side one needs an owner `ignore` row (differ docstring, IGNORED).
A section's style bar relaxes only through an owner-committed `threshold<TAB><section><TAB><style-identity %>` row; default strict, FOUNDATION/PRIMITIVE never waived (ACCEPTED DEVIATIONS).
Style output gives identity %, mismatch count per property, and top diffs `text | prop | design | app` (COMPUTED STYLE).
Rows wrapping differently fail: capture `data-lines` (a line-box count, never a height) on both sides (LINE COUNTS).
Mark each section's anchor `data-anchor`; an app crop missing it or holding a neighbour's is UNVERIFIED, exit COULD_NOT_CHECK_CROP (9) (SAME-CROP GUARD).
Once a page passes, `--baseline F --write-baseline`; later runs exit REGRESSION (8) listing only new deltas (BASELINE). A relabeled control (same `href`/`data-testid`, new text) reports CHANGED_LABEL, not a removal — an owner `relabel<TAB><old>→<new>` row tags it (ACCEPTED) (#1168, BASELINE).
Refresh a `--baseline` only inside the PR whose intended change causes the visual difference,
never as a drive-by pass: a baseline refreshed by an unrelated cleanup, or by a PR other than the
one that changed a section's rendering, absorbs whatever regression that section carries into the
new "expected" fingerprint, and every future run then reads it as clean. `--write-baseline`
records the app side's fingerprint from a **passing** run (BASELINE) — passing is not the same as
**intended**; re-run `--write-baseline` only when the visual change that just landed is the one
you meant to make, in the same PR, never a blanket re-baseline of every section.

**A defect in the reference design itself is never copied into the product to raise the score.**
A prototype can be wrong at some viewport or state — content clipping that is an unintended
rendering bug in the design tool, not a deliberate choice — and blindly matching the app to it
ships the defect. When a mismatch traces to the reference, not the app, escalate for an owner
decision; once decided, record the outcome as a named, versioned accept-file row (the `style` or
`visual-reviewed` kind above, its `reason` field naming the reference defect and the decision) —
never as a silent exception with no record of why.

## Scope a parity claim to the correspondence table — one screen verified is not the product

`ux-gates.md` gate 4 already defines *done* on a parity task as the
present-or-absent lists empty **"for every screen in the correspondence table."** That table
**is** the coverage ledger; #200's rule is only that it **exists before any claim** and that
a claim is **scoped to the rows actually verified**, never phrased over the product.

- **Enumerate every in-scope route/screen as a row before claiming parity.** Each row
  carries its own state: `verified` (rendered and compared, with the evidence) /
  `unverified` / `n-a (out of scope, reason)`. An unrendered screen is an **unprobed
  surface** — `unverified`, not matched (`full-map.md` principle 2: an absence is evidence only
  after a positive control fires).
- **A parity status is scoped to the `verified` rows and may never be phrased over the
  product.** Aggregate phrasing — "the app matches," "parity achieved," "all pages" — is
  valid **only** when **every** row reads `verified`; otherwise the honest form is `N of M
  screens verified — remaining: <list>`. Generalizing a claim from a sample to the
  population is a **High** communication defect: it retires the verification task — the
  owner stands the lanes down and stops checking — and the mismatch surfaces later as the
  trust-collapse dynamic (`product-ux-quality.md`'s repeated-owner-rejection rule). The
  verdict cap lives in `report-format.md` (capped below Approve while any in-scope screen is
  `unverified`).
- **Sample the strongest screen first, not the cheapest.** When screens are verified
  incrementally, verify a **chrome-bearing, data-dense** screen first; a static prose /
  changelog page is the **weakest** possible sample — it exercises almost none of the shared
  shell, and this file already puts shell unification ahead of screens, so a screen with no
  shell proves almost nothing about the shell.

## Anchor findings on treatment, not data-volume — a sparse mockup is not a feature spec

When the reference is a prototype on seed data, a section-by-section comparison flags the
production surface as "too dense / too tall / a wall of cards" because it renders **real**
data (dozens–hundreds of rows) while the mockup shows three to five. Much of that "gap" is a
**data-volume artifact**, not a design difference — the mockup's calm emptiness is partly
just emptiness. Anchor findings on **treatment** (layout structure, spacing scale, component
choice, hierarchy, chrome/nav, default view, empty/overflow handling), **not** absolute list
length, page height, or item count. The differ is the one exception: it always compares row
and value-slot counts, so seed the app to the design's data state first; `data-sample` masks
values, never counts.

**Run a foundation check before classifying screen-by-screen: diff both sides' design tokens
by resolved value, not name.** Bucket-(a) gaps recurring on every screen despite repeated
restyling are usually one root — a **different token foundation**. Match colour/spacing/type
by **computed value**; a low match (one audit: ~4% of the design's colours, ~3 of ~1,400
names) confirms it, and no per-screen fix converges until remapped — adopt the design's
**values** under the app's existing token **names**.

Separate three kinds of "gap" explicitly — they have **opposite** fixes:
- **(a) genuine treatment difference** — restyle to match.
- **(b) data-volume artifact** — the surface is larger because it holds real data; the fix
  is **progressive disclosure / capping / pagination**, *never* deletion.
- **(c) a real extra feature** the production surface has and the mockup lacks — **preserve
  it**: preserve the *capability* and **restyle it into the target's design language**,
  never delete it (see *Restyle an app-only feature into the target's design language* below
  for the classification, its **High** severity, and the ledger). A design mockup is a look
  reference, not a feature spec.

**"Drop / replace / remove X to match the reference" is a review smell** for any surface
that renders real data: it is a path to deleting working features and violates do-no-harm
(principle 4) and the never-remove-a-working-feature-without-confirmation bar — and when
the *X* is app-only **functionality** (removing it loses a user capability), deleting it
without a named owner approval is not merely a smell but a **High**-severity finding
(*Restyle an app-only feature into the target's design language* below). Rewrite the
recommendation as "adopt the reference's layout and default; move the extra content behind
progressive disclosure" for a data-volume gap, or "restyle the feature into the target's
design language" for a real app-only feature. A page-height or item-count delta versus a
seed-data mockup is a **notice, not a defect** — say so in the finding, so a downstream
implementer does not read it as a cut order. Before recommending any structural change to a
real surface from a mockup, confirm the difference is **treatment** (reproducible on
**equal** data), not volume.

## Restyle an app-only feature into the target's design language — don't delete it, don't leave it old

`ux-gates.md`'s parity differ runs **both ways** and flags an **app-only element**
(present in the app, absent from the design) as a finding. That rule and the
*preserve-a-real-extra-feature* rule above read as **opposites** — "mismatch" vs "preserve
it" — and when two rules collide an implementer reaches for the **harsher** one: *delete it
to match*, the wrong default and the costliest mistake on a restyle. Resolve the tension by
**classifying** the app-only element with the differ's operative test — *does removing it
lose a user capability?* (`ux-gates.md` owns that test) — into exactly one of
three buckets:

- **Decoration / pure shell** (no capability, no real data — an extra header, a "Showing N
  of N" line, a duplicated label) → **remove-to-match.** This is the only bucket that
  deletes, and it deletes nothing a user can *do*.
- **Real functionality** (removing it loses a capability — a filter, a view tab, an upvote,
  a deep link) → **restyle it into the target's design language.** Re-express the capability
  in the reference's own primitives (its button, its tab, its filter control): **look**
  reaches parity, **capability** stays — not "leave it in the old visual language," not
  "escalate and wait." Only when **no** target primitive fits does the element escalate to
  owner adjudication — the **fallback**, never the default.
- **Owner-approved removal** → a **named decision**: an owner has accepted losing the
  capability to reach parity. Record who accepted it and where.

**Severity.** Deleting — or recommending deletion of — app-only **functionality** without a
named owner approval is **High** (do-no-harm, principle 4; `full-map-principles.md` severity rubric): it
**blocks** unless a named owner accepts the loss (the *owner-approved-removal* bucket **is**
that acceptance). Removing pure **decoration** is not this finding — no capability is lost.

**Fill an exception ledger before implementing a restyle** — one row per app-only element:
`element · bucket (decoration/functionality/owner-approved) · verdict
(remove/restyle/named-removal) · target primitive`. The ledger proves each element was
**classified**, not silently deleted; a restyle deleting an unledgered element is the
do-no-harm finding above.

**Classifying a difference is a diagnostic step, not the deliverable — it must terminate in
the bucket's resolution, never a report of it.** A concrete "align X to the reference"
instruction is not a request to audit and adjudicate: bucketing every gap as intentional /
acceptable / already-superset and landing nothing is the instruction quietly downgraded into
a judgement call nobody delegated — worse across a multi-agent pipeline, where a reviewer's
classification reads to the orchestrator as verified alignment (`agentic-delivery`). "Keep
current" is a bucket outcome too, not a default: valid only behind a **named owner's
sign-off on that difference**, never an agent self-granting itself the exemption — the
*owner-approved-removal* row above is that sign-off, not a template for the rest.

## Match the chrome, never the mock's data — copying a sample value is fabrication

Separate **chrome** (layout, colour, geometry, tab set, headers, control affordances —
**must match**) from **data** (values, counts, denominators, series — **must stay real**). A
mock is built to *look* complete, so it fills every number with plausible sample values —
the one thing that must **not** cross into the product. **Copying a mock's number into the
real product is fabrication** (principle 3), a Blocker-class data-integrity defect surfacing
weeks later when someone trusts a value lifted from an illustration, not computed.
**Inverse** of the treatment-not-volume smell above: there the mock's *sparse* data tempts a
wrong cut, here its *invented* values tempt a wrong copy — a design mockup is neither a
feature spec nor a data spec.

- **Read the prototype's own disclaimers first.** Mocks routinely label their sample numbers
  ("values marked *sample* are illustrative until the backend is wired"); that label is the
  boundary between chrome-to-match and data-to-ignore.
- **Brief the chrome-vs-data split into every parallel worker.** A lane without the caveat
  will "helpfully" reconcile the numbers and inject fabricated data, invisible to the
  coordinator until it ships (`agentic-delivery`).
- **This is why the parity differ ignores text values entirely** — see the Phase-6
  parity-differ gate (owns the differ's exact scope) in `ux-gates.md`.

**Acceptance:** every number in the matched product traces to a real computation or an
honest empty state; no value present in the product originates from the design mock.

## Flow-cost — navigation cost, scroll burden, and cognitive load are first-class

Structural and pixel parity are necessary but not sufficient: a UI can match the reference
element-for-element and still feel poor, because the failures live in the **interaction
flow**, invisible to a per-screen diff. Run a **flow-cost pass**, distinct from structural
correctness, for each primary task:
- **Navigation cost** — count clicks + scroll distance to complete the task **and to reverse
  / switch**. Flag "must scroll back up to a top nav to change section" (→ sticky nav or
  tabbed sections), "N clicks for a common toggle," and "content pushed below a tall
  element."
- **Cognitive load** — the number of simultaneous choices offered, instructional sentences
  that could be a tooltip or removed, competing primary actions. (N interchangeable variants
  of one thing is the **variant-bloat** smell — cut to one default:
  `product-ux-quality.md`.)
- **Completion bar** — "the components match" or a green suite is not "done" for UI work;
  the bar is the subjective-quality completion bar defined under "Beware the proxy"
  (`report-format.md`).

## Ground the craft bar in cited heuristics, not ad-hoc taste

"Looks about right" is not a standard, and a redesign that references no established
heuristics is guessing — which produces the weak hierarchy, inconsistent spacing,
low-contrast grey-on-tint, and wall-of-text that draw repeated rejection. Apply a **cited**
per-screen checklist and **name the principle** each item comes from: a review cites the
principle, it does not assert "this looks off / fine."

Grounded in **Nielsen Norman Group's 10 Usability Heuristics** (Nielsen, 1994; last reviewed
2024 — verbatim names in `docs/standards-index.md`), **Refactoring UI** (cited by name), and
the **target's own design system** where it publishes principles. The heuristic names below
are NN/g's own:

- **Visibility of system status** (NN/g #1) — loading / empty / error / offline states exist
  and are honest; the current view and selection are always legible.
- **Match between the system and the real world** (NN/g #2) — labels in the user's language,
  not the schema's.
- **User control and freedom** (NN/g #3) — a clear exit and undo from every state; nothing
  irreversible on one mis-click.
- **Consistency and standards** (NN/g #4) — one component per concept, one spacing scale,
  one type scale, platform conventions (depth: `ux-components.md`, one component per
  concept; scales from Refactoring UI).
- **Error prevention** (NN/g #5) — constrain inputs; confirm the consequential.
- **Recognition rather than recall** (NN/g #6) — keep options visible; don't force the user
  to carry state across screens.
- **Flexibility and efficiency of use** (NN/g #7) — one strong default path plus an
  accelerator for the expert; keep power **behind progressive disclosure**, off the default
  surface.
- **Aesthetic and minimalist design** (NN/g #8) — hierarchy and **de-emphasis** (Refactoring
  UI); every added element competes with the primary action; cut self-evident instructional
  prose.
- **Help users recognize, diagnose, and recover from errors** (NN/g #9) — errors say what
  happened and how to fix it, in plain language.
- **Help and documentation** (NN/g #10) — reachable when needed, never a substitute for a
  self-evident UI.
- From Refactoring UI (by name): **one spacing scale and one type scale**, **semantic
  colour** (not decorative), intentional **empty states**, and **motion** with specific
  durations / easings that honour `prefers-reduced-motion`.

A **"does this feel premium?"** pass closes it — but as a prompt to locate the specific
heuristic a screen violates, never as a substitute for naming it. (Benchmarking the redesign
*direction* against two or three comparable products is a separate move:
`product-ux-quality.md`, *Match a named standard*.)

---

## 🚩 grep / signals

- A parity claim ("matches the reference") with **no mechanical differ evidence** — backed
  only by a structural audit, a green suite, seed-data screenshots, or an assertion with no
  diff image / structured mismatch list attached, and no surface-by-surface real-data pass.
- A parity / completion claim phrased over **the product / the app / all pages** with **no
  correspondence table** and no `N/M` coverage fraction — a sample generalized to the
  population (a **High** communication defect); worse when the one screen verified is a
  static, shell-less page.
- A **structural** divergence (different columns / grouping / composition) characterised as
  **"close" / "1:1" / "mostly there"** — a category error; a different structure is a
  different screen.
- A number in the matched product **copied from the design mock's *sample* value** — present
  in the product but tracing to the mock, not a real computation.
- A recommendation to **drop / remove / replace** a surface or its content to match a
  **prototype / mockup** reference (real data → progressive disclosure, not deletion).
- An app-only **feature** (removing it loses a capability) **deleted or slated for
  deletion** to reach visual parity, with **no named owner approval** and **no
  restyle-into-target attempt** — a **High** do-no-harm finding, not a parity win.
- A restyle that resolves app-only elements with **no exception ledger** classifying each as
  decoration / functionality / owner-approved before implementation.
- A multi-screen restyle **fanned out to parallel page lanes with no shell-ownership
  ledger** (single owner per shared-shell path, shell-lands-first — a **High** coordination
  defect), or a page lane's diff **editing a shared-shell path it does not own** (layout /
  nav / tokens / chrome primitive), even when correct in isolation.
- "Match the reference and use judgment" with **no cited heuristic** named behind a redesign
  recommendation.
- A primary task that needs a **scroll back to the top nav** to switch sections, or N clicks
  for a common toggle.
