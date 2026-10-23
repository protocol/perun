# Product UX depth — rendered sweep, screenshot evidence, composition critique, and export surfaces

Read this when the review is FULL (or a broad DIFF) over a runnable UI, a finding rests on screenshots (full-page or per-viewport), surfaces are compared for consistency, the owner says the app "feels like a prototype", or the product ships a download / print / copy-as-image path. Split from `product-ux-quality.md`, whose stance, data-state rules, encoding rules, 🚩 grep, and pre-ship checklist apply to every UI review.

## Rendered route sweep — apply domain P across every surface (FULL reviews)

The domain-P rules (`product-ux-quality.md` and its sub-files) are individually correct and still miss a whole class of defect, because on a
`FULL` (or broad-`DIFF`) review of a product UI **no step renders the assembled product
route-by-route**. The enforcing gate's (`ux-gates.md`) screenshot is per-change (the route a diff touched), so a
defect spanning many routes is found the way an owner finds it — scrolling the running app one
screenshot at a time, after a green gate and a clean code read. The sweep is the domain-P
analogue of Phase 3's anonymous-GET sweep (`method.md`): a cheap, systematic, whole-surface pass
turning "we have the rules" into "we applied them everywhere."

1. **Enumerate every route** — from the router tree **and** the nav manifest (a route in one but
   not the other is itself a finding), including detail overlays and tabbed sub-views — **and
   every export path** (download / print / copy-as-image): each is a second render surface,
   ruled as its own surface (below), not across this route matrix.
2. **Render each across the matrix** — the matrix the layout-invariant checks (Enforcing gate,
   `ux-gates.md`) refer to: **{~390px, ~1440px} × {light, dark} × {top, mid-scroll}**, plus any **state
   transition** a route has (loading→loaded, empty→populated, collapsed→expanded). Render the
   **running build at the intended base ref** — verify the checkout first; a stale tree renders
   the wrong product (render from a clean tree at the right ref — the receipt rule in `product-ux-quality.md`'s pre-ship checklist).
3. **Rule the domain-P checklist on each route** — states, encoding, delta, **data-viz**,
   **density/footprint**, interaction **completeness and consistency**, and the **layout
   invariants** (this step *applies* those rules, not restate them) — and record a per-route
   line: `route · viewport · theme · state · what a user sees · severity`.
4. **Report coverage as a ledger, not a verdict.** A route not rendered is `unverified`, never
   clean (the `COVERAGE_LEDGER` discipline, `method.md`); a clean finding generalises **only**
   to the routes actually rendered, never past them (`migration-parity.md`, *Scope a parity
   claim to the correspondence table*). Group findings by root cause: a class spanning many
   routes is **one** systemic finding, not forty.

## A full-page stitched screenshot fabricates fixed/sticky defects — verify against the live DOM before filing

An automated UX audit capturing **full-page** screenshots (`page.screenshot({ fullPage: true })` in
Playwright/Puppeteer, and equivalents) doesn't photograph the page in one shot — it **scrolls the
viewport and stitches** segments into one tall image. A `position: fixed` or `position: sticky` element
is painted **in every segment**, so the stitched result shows it **duplicated down the page** (a header
repeated at each scroll step) or **displaced** from where it actually renders — a **capture artifact of
the stitching, not a defect in the page**; the live product shows the element exactly once, correctly
pinned. It burns a fix cycle because the stitched image looks authoritative: a "duplicated header",
"overlapping toolbar", or "footer floating mid-page" reads as a real layout bug, gets filed, and a
builder chases a problem no real viewport has. **Before filing any suspected fixed/sticky defect sourced
from a full-page capture, reproduce it against the live DOM** — open the running page and scroll it, or
take **per-viewport** captures at specific scroll offsets (the `{top, mid-scroll}` shots the *Rendered
route sweep* above already uses, which don't stitch) — and file only what survives. **Distinct** from
the *sticky-chrome collision* invariant in the Enforcing gate (`ux-gates.md`), a **real** defect (content painting
**under** sticky/fixed chrome, seen mid-scroll) — this is its inverse, a **false** defect the capture
*invents* for a correctly-pinned element; and a UX instance of `method-situational.md`'s *reproduce a finding
against the right surface* family (dev-vs-prod build, the gate's own detector) — here the wrong
instrument is the **full-page stitch capture mode**, the right one the live render or a non-stitched
per-viewport shot.

## An unscoped overflow/responsiveness audit floods real findings with false positives

An automated overflow/responsive-layout audit run without written scoping rules over-reports
heavily — worst when the audit is delegated to a lower-capability model that infers scope from
the prompt alone ("check for overflow") rather than from checked instructions, and interprets it
maximally literally: every hidden, off-screen, or not-yet-revealed element becomes a "defect." A
report dominated by noise is worse than no report — a reviewer either hand-triages everything
(defeating the point of automating it) or starts ignoring the audit's output entirely. One
observed run: the same audit category, run once without scoping rules by a cheaper/faster model,
reported 95 "defects"; a follow-up pass applying the three rules below on the same surface found
zero real page-level scroll issues — the entire gap was scoping, not detection capability. Ship
any overflow/responsiveness audit with these rules written into its own instructions, never left
implicit:

1. **Count overflow only when it causes page-level horizontal scroll, or clips content that is
   actually visible outside a designated scrollable container.** An element wider than its parent
   that a container legitimately scrolls, or that never forces the page to scroll, is not a
   defect.
2. **Exclude elements hidden from sighted layout (`display: none`, `visibility: hidden`,
   sr-only clip).** These are not overflow defects by definition — they're not visible to
   anyone. `aria-hidden` alone does not qualify: the element still renders and can still scroll.
3. **Open click-to-reveal UI before judging its contents.** A collapsed accordion, an unopened
   menu, or a closed modal's inner layout must be opened first; judging its overflow while closed
   inspects markup nobody sees.

This matters *more*, not less, when the audit is delegated to a cheaper/faster model — write the
rules into the audit's own prompt/instructions rather than assuming they're implied.

## A clean checklist is a floor, not a ceiling — read the render and critique composition

The gates (the enforcing gate's named pixel checklist in `ux-gates.md`, the rendered-route sweep, the
full-page-stitch caution above) prove a screenshot was *taken* and scanned for enumerable, per-element
defects — overlap, clip, contrast, a missing empty/loading state, a focus ring. They do **not** prove
the surface *looks acceptable*, and treating "every checklist item passed" as "this is fine" is a
category error a binary list structurally invites. **Composition quality — spacing rhythm, alignment
consistency (a column of badges that don't share a right edge), visual density, information hierarchy,
chrome/nav consistency, element overlap — is a *relational* judgment across everything on screen at
once, not a yes/no property of any one component**, so no fixed line item expresses it, and a
checklist-shaped audit returns a confident "no defects found" on a page a human flags for cramped,
ragged, or unscannable layout in seconds. The clean report is not evidence of quality; it's the
**default output of a shallow pass**, rewarded because a short "no defects" costs less than prose that
must justify each finding (clean-pass bias). A second bias compounds it: a checklist audit that *does*
surface something visually wrong is disproportionately likely to **wave it away as a "screenshot
artifact"** rather than file it — the legitimate full-page-stitch caution above inverted into a blanket
excuse. **The requirement is not a longer checklist:** a UX audit must *read the rendered screenshots*
and produce a **written per-surface composition critique against a named best-in-class bar** — the
operative question is "would a senior designer at a top product org ship this?", answered in a few
sentences about spacing, alignment, density, hierarchy, chrome consistency, and overlap — and a bare "no
defects found" with no such critique is **`unverified`, not a pass** (a status with an unstated
inspection — the enforcing gate's own rule, `ux-gates.md`). Capture **multiple real-viewport screenshots at the scroll
positions a user actually lands on**, never a single full-page stitch: the stitch both hides composition
problems (nothing is framed as a user sees it) and fabricates others (a `fixed`/`sticky` element pasted
at its first-frame position). **Distinct** from the full-page-stitch caution above (a capture artifact
producing a false *positive* on fixed/sticky chrome — verify against the live DOM before *filing*): this
is the opposite direction, a checklist producing a false *negative* on real composition defects, and it
warns that reasoning must not be inverted into an excuse to *discard* a real finding unverified.
Distinct too from the enforcing gate's pixel checklist (necessary, and it catches the enumerable defects
— but not sufficient for composition) and from requiring only that a screenshot be *inspected* against
that checklist or that review cite heuristics rather than taste: this reports the failure that survives
all three — the checklist exists, is consulted, and still rubber-stamps.

## A cross-surface difference is a defect only when it carries no meaning — classify before filing

The Unified-across-modules audits in `ux-components.md` (and the composition critique just above) hunt for one concept
**rendered differently across surfaces** and call it drift. The failure mode of that hunt is the **false
positive**: not every cross-surface difference is accidental drift — some are **intentional and
distinct-semantic**, a concept deliberately drawn two ways because the two instances *mean* different
things, and filing those as drift (then "unifying" them) **destroys a real signal** — a net-negative
"fix" violating do-no-harm and the read-first *separate a defect from a redesign* spine. Before filing
any "renders differently on A vs B" finding, run a **three-question classifier**:

1. **Same concept?** Are both instances the same underlying concept (same entity, same component role) —
   or two different things that merely look alike? Different concepts are not a consistency finding at
   all.
2. **Same intended meaning?** Do the two instances mean the same thing in their contexts? If the
   difference tracks a genuine semantic distinction — a status badge *filled* on the active board but
   *outline* on the archived view (outline **signals** archived), a primary action a solid button on the
   create form but subdued/absent on a read-only detail page (the action **isn't available** there) —
   it's intentional-distinct-semantic, not drift.
3. **Does the difference carry meaning?** Is the visual difference **doing work** — communicating that
   semantic distinction — or noise with no semantic correlate?

**File as drift only when all three say "same concept, same intended meaning, and the difference carries
no meaning."** Otherwise it's intentional-distinct-semantic: leave it, or — if the distinction itself
seems wrong — surface it under *Decisions needed (owner)*, never a Blocker/Critical, never a silent
"unify" (the product-choice gate discipline, SKILL.md Phase 5). **Distinct** from the
composition-critique rule above, which fights the opposite error — a checklist **false negative** that
rubber-stamps a real defect; this fights the **false positive** where the same audit flags a meaningful
distinction as a defect, two symmetric guards on one "is this consistent across surfaces?" question.
**Distinct** too from the shared-value-resolver bullet under *Unified across modules* (`ux-components.md`): that's a
false **negative** (a shared resolver makes a concept *look* unified while its render drifts — a real
defect hidden); this is the false **positive** (a concept renders differently and *looks* like drift
while the difference is intentional) — the exact inverse error, why the
*render-identically-at-all-mount-sites* question there must pass this classifier first, so the drive to
unify never collapses a distinction the product intends.

## Sibling ports of one component drift apart

Two independent ports of the same UI component (two apps, or a legacy and a new surface) diverge: one gets an accessibility or state fix and the other does not. When a UX finding looks like a port-specific issue, grep for the component's literal values (class strings, labels, ARIA attributes) in every sibling and fix or file all of them. Finding: a fix landed in one port while an identical literal sits unfixed in a sibling.

## "Feels like a prototype" is usually one or two shared-primitive roots — fix the root, not each surface

When users call a web app "a mediocre prototype" — hover states that behave oddly, motion that isn't
smooth, pages that seem to take seconds to appear — the cause is rarely scattered per-page bugs; it's
usually **one or two shared-primitive roots**, each producing the symptom on *every* surface that
touches it, so one base fix repairs all of them and a symptom-by-symptom patch pass never converges.
This is the diagnostic form of root-cause-not-symptom (full-map.md principle 9): don't file N per-page
tickets, find the shared root. Two roots recur often enough to check for by default:

- **Root 1 — bespoke interactive elements bypass the design-system primitive and so lack the base
  affordances it bakes in.** A design system puts `cursor: pointer` and a hover/focus `transition` on
  its `Button`/`Link` primitive; any element written as a raw `<button>`/`<a>` (a one-off, a third-party
  wrapper, a "just this once") inherits neither, so it reads as inert (default arrow cursor over a
  clickable thing) or janky (colour/background snapping with no ease). The fix belongs at the
  **base/global layer**, not per component: a global `button:not([disabled]) { cursor: pointer; }` and
  one shared `transition` on `a, button, [role="button"], [role="tab"]`. Two mechanics are load-bearing:
  use the **attribute selector `:not([disabled])`, not the pseudo-class `:not(:disabled)`** — the
  pseudo-class's lower specificity lets a per-instance utility (`cursor-help`) get silently
  out-specified back to the base rule (a real, previously-hit regression, worth a test); and **exclude
  `box-shadow` from the transitioned properties** (never `transition: all`), because keyboard focus
  rings are commonly a `box-shadow` and easing one in over ~150 ms reads as laggy, unresponsive keyboard
  navigation — a genuine a11y regression traded for a cosmetic one. Pair the transition with a
  `prefers-reduced-motion: reduce` zero-out (`frontend-a11y.md` owns the reduced-motion rule, including
  the JS-driven case; this only adds that the base transition needs the same guard).
- **Root 2 — an SSR page ships above-the-fold content at `opacity: 0`, waiting on client JS to reveal
  it.** An entrance-animation pattern renders an above-the-fold element with `opacity: 0` (or a
  `translateY` offset) in the server markup and a client effect flips it visible on hydration. But the
  server already sent the real content — it's merely *invisible* until the bundle loads, parses, and
  hydrates, so a page that rendered correctly and fast **reads as an empty/blank multi-second load**;
  the animation library manufactured the delay. Fix: never gate already-rendered SSR content above the
  fold behind a JS reveal — play the same effect as a **pure CSS `@keyframes` starting at first paint**
  (`animation: fadeIn 300ms ease-out`), or drop the `opacity: 0` initial state above the fold and
  reserve reveal-on-scroll/-mount for content starting below the fold (where the delay is invisible
  anyway).

**Don't over-fix:** in most design systems the `Button`/`Link` primitive and focus ring are already
correct — the gap is specifically the code that *bypasses* them, so audit for **bypass sites** (raw
`<button>`/`<a>` outside the primitive), don't rewrite components that already work. **Verify, don't
assume:** for Root 1, read `getComputedStyle(el).cursor` and `.transitionProperty` on the actual bespoke
element before/after, not by eye; for Root 2, `curl` the route with no JS running and confirm the real
content — not a shell/skeleton — is in the raw HTML with its visible styling already applied, not
shipped `opacity: 0`. **Distinct** from four neighbours: the *interaction-consistency* bullet in `ux-interaction.md` (a
*shared* component whose hover/active/focus reaction diverges *across instances* from per-instance
overrides) — Root 1 is an element that never went through the primitive at all, lacking the base
affordance rather than diverging on it; the *not-dead-before-hydration* / dead-`<Suspense>` bullets (`ux-interaction.md`, `web-fetch.md`; an
*interactive control* disabled or blank pre-hydration) — Root 2 hides *already-rendered non-interactive
content* whose data was ready, gating only its *visibility* on hydration; the composition-critique rule
above, how you *notice* the app feels off — this is how you *diagnose it to the shared root* once
noticed; and the concept-fragmentation root (*Unified across modules — one component per concept*, `ux-components.md`)
— the **opposite topology**, a third prototype-feel root worth checking for by default. Both roots above
share a *single* base-layer / shared-primitive cause whose **one fix propagates to every surface**; the
concept-fragmentation root is the inverse — there is **no** shared component to fix, the concept is
re-implemented N independent ways (a stat tile built four ways, a status pill five, each drifting so a
fix landing in one twin leaves its copies broken), so the remedy is to **consolidate to one
parameterized component**, not repair a base layer. Both share only the tell that a **symptom-by-symptom
patch pass never converges**.

## Export / print / share is a second render surface

A **download / print / copy-as-image** feature emits the view through a *different* code path than the
screen — canvas/`toDataURL`, SVG serialisation, a `@media print` stylesheet — so a green on-screen
render says nothing about the artifact the user actually walks away with. It silently **clips** content
past the viewport, **drops** axis/legend/labels that lived only in interactive chrome, ignores the
current **theme**, or exports an empty/partial view as a blank image. Treat each export path as a review
surface in domain P (the sweep above already enumerates them):

- **Find the export paths** — grep `toDataURL`/canvas capture, SVG serialisation, `@media print`, and
  `download`/`export`/`copy image` handlers.
- **Produce the artifact and inspect it like a route** — no clip of content extending past the viewport;
  **axis / scale / legend / labels baked in** (an interactive-only readout — the hover value+date the
  *Data visualization* rule in `ux-dataviz.md` requires — needs a *static* equivalent in the export); **theme**
  honored or explicitly normalised; enough **title / as-of / context** that the artifact is
  self-describing out of its app.
- **Every data state exports honestly** — an empty or partial view exports with its honest label, never
  a blank canvas (*Every data state* in `product-ux-quality.md`, applied to the export).
- **Mechanise where you can** — snapshot the exported artifact's dimensions and the presence of its key
  elements (axis text, legend), held to the same could-not-check-vs-found-nothing discipline as the
  enforcing gate's heuristics (`ux-gates.md`).

A *different* axis from reproducing an audit finding against the production build (`method-situational.md` verifies
*which build the reviewer reads*; this inspects an artifact the *product emits*), and where the data-viz
checklist (`ux-dataviz.md`) is most often lost — the on-screen chart carries axes and a readout the serialiser
drops.
