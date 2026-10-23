# Product UX quality — the "at-home" bar (domain P, design half)

Read alongside `frontend-a11y.md` when the target renders a **product UI a human operates** —
dashboard, table, form, chart, legend, metric display. Expands section P of `SKILL.md` (design
half). `frontend-a11y.md` owns a11y **correctness** (WCAG 2.2 AA, keyboard/focus, contrast, Core
Web Vitals, cross-view accessible-name pass); this owns whether the UI feels **at-home** —
conventional, self-evident, correct in every data state, cleanly encoded. Same spine as the rest
of the method: respect the existing design, separate a defect from a redesign, verify live,
ground every claim in a named standard — never "looks nicer."

Ground the design half in the tiers the skill already tracks: **WCAG 2.2** (colour, contrast —
via `frontend-a11y.md`), **Nielsen's usability heuristics** (named, not URL-cited — by-name list
in `README.md`), and the public precedent of top products (Linear, Stripe, Notion, Vercel,
Figma, Datadog, Google/Material, Robinhood) — named the way this skill already names Cursor,
Copilot, and OWASP: no new URL, version, or date the reviewer did not fetch (principle: no
fabrication).
## Routed depth — load on trigger

This file holds what every UI review needs: the read-first stance, every data state, encoding and colour-alone, self-evidence and density, the named-standard rule, the 🚩 grep, and the pre-ship checklist. Depth lives in sub-files; load one only when its trigger matches the target or the diff:

| Load | When the target or diff … |
|---|---|
| `ux-writes.md` | writes from the UI: an optimistic update with a rollback, a load-to-edit form seeded from a fetch and saved as a full replace, or a resolve / archive / dismiss action that removes a record from view |
| `ux-dataviz.md` | renders a chart, sparkline, heat-map or calendar grid, KPI or metric delta, confidence / score / tier, count badge, or progress / attainment / ratio tile |
| `ux-lists.md` | renders a feed, list, table, or dashboard of items: its default order and sort modes, whether each unit says why it matters, or rows whose trailing chips must align across rows |
| `ux-states.md` | caps or slices a list/table below a known total, writes back per-row success/failure counts from a bulk apply/import, names (or implies) an empty state's cause, renders a definitive-record surface (audit log, security events, a decision-bearing balance/count), or has more than one component consuming one shared hook/context instance |
| `ux-components.md` | renders one concept in more than one place: a shared component or design token, a design-system migration, sibling view variants, a shared search or view-switch across layouts, or one component at single-entity and aggregate scope, or the pre-ship one-component-per-concept box is being ruled |
| `ux-interaction.md` | adds or changes an interactive control: an input's read-back, a completion message, rich text, a filter or facet option, an in-page anchor, a disabled or hydration-gated control, a disclosure default, change history, or hover / focus parity across instances |
| `ux-sweep.md` | is a FULL (or broad DIFF) review of a runnable UI, rests a finding on screenshots, compares surfaces for consistency, answers an owner's "feels like a prototype", or ships an export / print / share path |
| `ux-gates.md` | claims a UI change verified on screenshot evidence, sets or reviews auto-merge policy for UI changes, imprints a UX gate (Phase 6), or is a parity task (gate 4, the parity differ) |


---

## Matching a convention is an observation, not a licence to redesign (read first)

Mirrors `frontend-a11y.md`'s "Respect the existing design" — the rule keeping this reference
net-positive on every axis. A product-UX finding **improves** the product; it must never
silently restyle it.

1. **Separate the defect from the redesign.** A blank screen on a reachable state, a delta
   coloured the wrong way, a legend that is a wall of prose, a dead control — these are
   **defects**, fixed in place, minimally, preserving the existing look. A change that alters
   layout, spacing system, type scale, component set, or brand *to match a convention* is a
   **redesign** — an owner decision, not a review fix.
2. **Surface the convention gap under "Decisions needed (owner)."** When a design deviates from
   a named top-product pattern (legend, delta, empty state, date picker, table), record it with
   the precedent cited and the **minimal-visual-impact** fix offered first — as
   `frontend-a11y.md` handles a layout/brand change. Notice the gap; let the owner decide.
   "Looks nicer" is not a reason — nor is "the convention says so."

---

## Repeated owner rejection is a redesign trigger — surface options, don't tune (or impose)

The section above bars a redesign driven by *your* taste; this is its complement: a redesign
driven by the **owner's own repeated rejection** of the same element is warranted — but as
options the owner chooses, never a change you tune your way into or impose. Both obey principle
5 (*respect the existing design; separate a defect from a redesign; surface it, don't impose
it*).

- **Trigger: the owner rejects the same element two or more times** ("bulky / confusing / too
  heavy / looks wrong"). That repetition — not a reviewer's aesthetic read — is evidence the
  approach is **structurally** wrong, not under-tuned. A first rejection is feedback to apply;
  the *same* rejection twice says the structure, not the parameters, is the defect.
- **Stop tuning.** Nudging padding, arrows, spacing, or counts can't remove a structural defect
  (three overlapping rings don't stop overlapping because the arrows moved). Re-tuning after a
  second identical rejection is the failure this rule names — the design-half form of principle
  9 (*root-cause, not symptom*): after the same failure twice, change the approach, don't repeat
  the fix.
- **The same move for a *verification* claim: repeated correction means your method is broken,
  not their patience.** A stakeholder repeatedly correcting your "it matches / it's the same" is
  evidence your **verification method** is wrong, not a cue to ask for more examples. Build the
  comparator (the **parity differ**, Phase-6 *Enforcing gate* in `ux-gates.md`), show its diff, and report
  only what you actually inspected ("the nav now reads A · B · C, I looked at it") — never a
  blanket "it matches"; an honest "not yet verified" beats a false positive (principle 9: after
  the second false "matches", change the instrument, don't re-assert).
- **Name the structural flaw in one line**, then research how **two or three comparable
  products** (named, per *Match a named standard* below) solve the same problem — the muscle
  memory the new direction should borrow.
- **Hand the owner concrete options to choose — show, don't tell.** A side-by-side of two or
  three real directions is a decision the owner makes in seconds; a paragraph describing them is
  not. Product/redesign choices are owner decisions, never carrying Blocker/Critical gate
  language (SKILL.md Phase 5).
- **Variant/option bloat is the supply-side of the same smell.** N interchangeable ways to view
  or style one thing — seven style-toggle tabs on one diagram, eight overlapping list modes —
  reads as unfinished, not powerful: the *choice* is the defect, so **cut to one strong
  default**, not tune the set. Test: would a first-time user know why to pick one over another?
  If not, it's bloat, not flexibility. Distinguish redundant variants (overlapping modes,
  decorative toggles) from genuinely different tools (a diagram vs a table serve different tasks
  — keep both); keep the power path reachable behind **progressive disclosure**, off the default
  surface.

---

## Every data state — rule on each, not just the happy path

Every view is intentional and honest in **all five** states, each ruled on (finding, clean, or
`unverified`):
- **empty** — say what will appear and how to get it (never a bare void);
- **loading** — skeleton/spinner, no layout flash;
- **error** — what failed and how to recover, **never a raw stack or blank**;
- **partial** — some data present, some missing/degraded, shown honestly;
- **overflow** — too many rows → scroll/paginate/virtualize **inside the component's own
  container**, never breaking the page layout; a capped or sliced list also needs an explicit
  **remainder indicator** whenever more rows exist than are shown (`ux-states.md`).

A blank screen or a raw error on a **reachable** state is a P0 "not-at-home" defect, not a nit —
severity by reachability, like any other defect. (Nielsen: visibility of system status; help
users recover from errors.) `frontend-a11y.md` owns the *phrasing/consistency* of empty states
across routes; this owns whether each state **exists and is honest**.

Depth — capped/sliced-list remainder indicators, partial-apply reconciliation, an empty state's
coverage/named-cause/stakes, filtered-vs-genuine emptiness, and a shared hook/context's readiness
signal read by more than one consumer: `ux-states.md`.

## Encoding hygiene — one visual channel per dimension

Never make **one channel carry two meanings**. The classic bug: colour encoding two independent
variables at once (green = both "instrumented" *and* "trending up") — ambiguous, and invisible
to an a11y-only pass. Split dimensions across channels — **shape/fill** for one, **colour** for
another, **position/size** for a third. Run out of channels ⇒ you have too many encodings; cut
some. Fewest encodings wins.

## Never colour alone — colourblind-safe as a method

`frontend-a11y.md` owns the WCAG rule (1.4.1 Use of Color; and the 1.4.3 disabled-control
exemption that a gate must not over-flag). This owns the **testable method**: pair every hue
with **shape, icon, or text** (▲▼ ↑↓ ✓ ✗ or a word) plus an `aria-label`. Colour reinforces;
shape carries the meaning. The one-line test: **it must read correctly in greyscale.** Works in
greyscale = works for the ~8% of men with deuteranopia, and for everyone.

## Self-evident over explained — progressive disclosure

Layout + labels + standard components make meaning obvious **without** inline prose. **If a screen needs
a paragraph to be understood, the design failed — fix the design, not the paragraph.** Demote
explanation to a "?" tooltip, a hover, a collapsible "How this works", or a dismissible first-run hint —
available, not shown by default. Legends/reference blocks: **collapsed by default**; when open, a **grid
showing the actual glyph** beside its meaning, never a paragraph describing marks in words. Teach on the
artifact itself via hover/focus; the legend is the fallback teacher, not the primary one. (Nielsen:
aesthetic-and-minimalist design; recognition over recall.)

## Drawers, hierarchy, density

- Detail drawers **overlay** the current view — never navigate the background away; the user
  keeps their place and can inspect several items in a row.
- Correct collapse **scope**: a child collapses within its parent's subtree, not siblings two
  levels up.
- Declutter dense rows — few visible chips, secondary actions behind a menu, detail on hover.
  **No dead controls** — a toggle that does nothing is worse than none; it's a trust defect, not
  a cosmetic one.
- **Footprint tracks information — the opposite failure from a dense row.** The declutter rule
  above fixes an *over*-dense row; the converse defect is wasted space — an
  empty/undefined/placeholder record rendered at a **populated record's footprint** (a full card
  reading "No data source / No owner / —"), a grid stranding half a wide viewport, or a toolbar
  row holding one control across the full width. Collapse or group placeholders (a compact row,
  not a full card), give a grid/list a **density target at the wide viewport** (name the
  top-product precedent — a metrics grid, a list view — not a taste call), and fold stranded
  single-control chrome. The test is **information-per-screen, not pixels-per-item**: a screen
  that could show N× more at a glance without crowding is a density defect, ruled like any other
  — the *space-appropriateness* complement of *Every data state*'s honest-empty rule: a
  full-card empty state is honest and still wastes the footprint.

## Match a named standard; visual & number-format consistency

Before designing an element, recall how the best products solve it and **name the standard
applied**; reinventing a solved problem (legend, delta, table, date picker, empty state) is a
cost, not a feature. Then keep it consistent: one type scale, one spacing rhythm, one component
set, consistent **number formatting** — locale/thousands separators and **tabular figures in
columns** so digits align. The same mark/legend renders identically wherever it appears.
`frontend-a11y.md` owns **accessible-name** consistency across routes; this owns **visual /
number-format** consistency — the drift a per-route pass and a name-only diff both miss.
(Nielsen: consistency and standards.)

---

**🚩 grep**: a data-fetch / `useQuery` / `await` render path with no `isLoading`/`isError`/empty
branch, a `.map(` over a list with no length-0 case, a table/grid with no `overflow`/pagination,
a `catch` rendering `err.message`/stack into the DOM, or a `.slice(0, N)`/`LIMIT`/`take(N)`
render whose length can be less than a known `total`/count with no adjacent remainder/pagination
text, or a client response type that omits a server-computed `error_count`/`errors`/`rejected`
field so its success counters can't reconcile to the total (states) · a colour scale keyed on a
field that also drives an icon/shape, or `>1` semantic use of one `--color-*` token (encoding) ·
a status/delta rendered by `color`/`background` with no sibling icon/text node, or a
colour-coded status dot with no `aria-label` (colour-alone) · a delta coloured green-for-up /
red-for-down unconditionally, an arrow/percentage with no magnitude, or a "change" number with
no period anchor (delta) · a paragraph of instructional copy rendered inline on every load, or a
legend built from text descriptions of marks rather than the marks (self-evident) · a
"drawer"/"detail" that pushes a route change or unmounts the list, or an `onClick` that is a
no-op / `// TODO` (drawers / dead controls) · `>1` font-size/spacing value for one role, or
column numbers interpolated without `toLocaleString`/tabular figures (consistency) · the same UI
string, section heading, or markup block duplicated across ≥2 component files, or a second
hand-rolled copy of a row/card/field a shared component already renders (one concept built more
than once) · a text input that persists markup while rendering its raw `**`/`*`/`<u>` tokens
back to the user (not WYSIWYG) · an add/create/edit handler that writes to a store with no path
that reads the value back into the same view (write-only input) · an editable record's write
path with no history/log table behind it, or an agent/model-authored value merged in with no
field distinguishing it from a human edit (change-history / silent AI edit) · a
`confidence`/`score`/`priority` rendered as a raw `{n}%` or float with no defined tier label
beside it, or a model confidence number published as precision (confidence tier) · an
`<svg>`/chart with no `<text>`/axis node and no hover/focus readout target, or a line/area drawn
across `<3` data points (data-viz) · a `position: sticky`/`fixed` element whose scroll container
has no padding (gutter), or an action revealed by `onMouseEnter`/`:hover` with no focus/keyboard
sibling (hover-only) · two or more components consuming one shared hook/context instance where
only some destructure and branch on its readiness/error field alongside the value
(sibling-consumer signal) — the footprint, reflow, and per-class-parity defects are
**render-only**, caught by the route sweep in `ux-sweep.md`, not a grep.

## Pre-ship checklist (mirror SKILL.md's report discipline)
- [ ] Does it need explaining? If yes, redesign until it doesn't (or demote the text to progressive disclosure).
- [ ] All five data states handled and honest — empty / loading / error / partial / overflow — an empty state names its **coverage** (no-data-collected vs collected-and-genuinely-none), never implying a false all-clear, and any **named cause** in its copy holds on every path that reaches it, not only the one it describes; it distinguishes **filter/search-removed** from **genuinely-none** — the positive/onboarding copy is reserved for a zero **unfiltered** total, while a non-empty total with an empty view gets a neutral no-match state carrying a **clear-filter** action — and any **section chrome** (header, count, "all done" banner, see-all affordance) is **gated on content-presence** or paired with an explicit empty/no-match fallback, never captioning rows a filter has hidden; a **definitive-record surface** (audit log, security events, a decision-bearing balance/count) shows a **distinct, retryable error state** on fetch failure rather than degrading to empty — a low-stakes/supplementary value may acceptably degrade, a definitive one may not; and a capped/sliced overflow list carries an explicit **remainder indicator** whenever `total > shown`; and a partial-apply operation's visible success counters reconcile to the input total — a client response type narrower than the endpoint's actual return (a dropped `error_count`/`errors` field) is a silent undercount, not a clean partial state; and a **load-to-edit** form does not let an **unresolved** read (a failed/timed-out fetch, not a confirmed-empty one) seed its `initial`/`defaultValue` into a **full-object replace** on save — the save is gated (disabled, patched, or confirmed) until the value resolves, since here a failed read degrades into a **destructive write**, not merely a misleading display?
- [ ] Every shared hook/context's readiness/error signal is read the **same way at every consuming surface** — checked independently per consumer, not inferred from the one call site that clearly gets it right; no sibling consumer destructures only the value field while another sibling of the same instance branches on the readiness/error field?
- [ ] One channel per dimension; nothing colour-only; reads correctly in greyscale?
- [ ] Deltas are caret + magnitude, coloured by sentiment; flat is a muted `—` with a period anchor?
- [ ] Confidence / score / priority shown as a **defined labeled tier** (text + a colourblind-safe cue), not a raw `%` or point score, and no model-authored number published as precision?
- [ ] A progress / attainment display shows **coverage / readiness** ("N of M measurable / instrumented"), never a fabricated `%-complete` / grade with no measured reading; an unmeasured item renders **"awaiting reading"**, not a manufactured number; a display "awaiting reading" on nearly every row is **held, not shipped**?
- [ ] Does each primary information unit answer **why it matters** (a derived / structural signal — count, recency-delta, graph-degree — **never a fabricated importance score**), not just what happened; where an action is possible, is a concrete **next step** named; and is the **most decision-ready surface in the first paint and stable** (not a post-hydration `aria-hidden` island, not below fixed non-interactive chrome)?
- [ ] Does the **default ordering serve the user's job** (not reverse-chron by default on a decision surface), and is **each exposed sort/rank mode self-explaining ("orders by …") and measurably distinct** (near-identical modes collapsed; an opaque / near-constant sort key is false precision — measure its distribution first)?
- [ ] Matches a **named** top-product pattern; convention gaps surfaced to the owner, not silently redesigned?
- [ ] If the owner has rejected this element **twice**, stopped tuning — structural flaw named, two or three comparables researched, concrete options surfaced for the owner to choose?
- [ ] Consistent type scale / spacing / components / number format with sibling views (tabular figures in columns)?
- [ ] One shared component per concept — reused/extended, not reimplemented per page; a fix landed in the shared component, not one caller; **sibling view-variants import one shared lookup/primitive (an enum→label/colour map, a sub-element's derivation+render) rather than each re-declaring it**; **searched the tree for a duplicate twin (a duplicated visible string/heading) a diff-scoped review would miss**; and every component built for this surface has at least one **mount path** from a router/page entry, static or dynamic/lazy/registry-based (zero paths = a dead-render candidate — wire up or retire, owner's call)? (procedure: `ux-components.md`)
- [ ] Interaction loops close — read-back on every input (no write-only), WYSIWYG not raw markup, no dead controls — checked on the route that actually renders?
- [ ] Any action **labelled non-destructive** (resolve / archive / dismiss) that removes the record still shows it **persists** — a persisted-state label, an undo, or a discoverable resolved/archived view — so it doesn't read as a hard delete? (Default-hiding behind a *known* filter is a convention, not this; soft-delete is out of scope; **fail-open** — a human adjudicates.)
- [ ] Every **disabled action explains its cause and a recovery path** — the unmet prerequisite + a concrete next step, in **reachable** text (nearby or a focusable wrapper/popover, not a tooltip on the disabled element, which may get no hover/focus); an action permanently unavailable to the current role is hidden or replaced, not a dead end?
- [ ] **No write control renders as a dead/disabled default during the SSR → hydration window** — a control gated on client-only state (auth/session) shows a loading affordance (skeleton/spinner) or is optimistically enabled with its click **replayed** after hydration (never a dropped no-op), not a bare disabled button; confirmed on a **pre-hydration** snapshot, and *could-not-check* (no pre-hydration capture) fails **open**, not a silent pass?
- [ ] Drawers overlay (don't navigate away); collapse scope correct; no dead controls?
- [ ] Verified live in the running product, in more than the happy-path state — **including the default state a user lands on** (signed-out / no-role / default route / local default), not only a mock or a hand-picked persona view?
- [ ] Any "matches / exact / parity" claim checked against the **default served state of the tree under review** as the canonical surface (not whichever tree happens to hold the port — name url · branch · sha, `report-format.md`) — and if it rests on a non-default surface, does it **name** that surface and say the default was not checked?
- [ ] "Looks the same" backed by a **rendered-appearance** diff of the default state vs the reference (screenshot / computed styles), **not** section-presence, DOM order, a passing test, or loaded data — and stating **which axis** (structure / styling / content / data) the evidence covers, without "fixing" data to answer a styling complaint?
- [ ] Parity task: differences classified **structural vs cosmetic** (structural parity first; a structural divergence **never** called "close / 1:1"); every "matches" claim gated on a **mechanical differ** (diff image + structured mismatch list attached, not an assertion); reference read at its **highest fidelity** (running build > source > screenshot); **no mock sample value copied** into the product; and the differ run **both ways** (design→app and app→design), both lists **resolved** (design→app empty; each app→design entry restyled into the target language, decoration removed, or owner-adjudicated — an app-only element is a finding to resolve, never a silent bonus)?
- [ ] Parity **delta** established by rendering **both sides at the same viewport width** (a one-sided crop is a hypothesis, never the evidence), and each app-only / design-only element's **state confirmed on the other side** (present-but-collapsed / disabled-by-data / in-a-menu) before it is called a delta?
- [ ] Did **not reconfigure the default** (persona / seed / flag / env) and then claim "verified on the default" — checked the pre-existing default and disclosed any change to it?
- [ ] Every styling / placement delta enumerated in **one** side-by-side pass and fixed against that inventory — not piecemeal-fix-then-redeclare-done?
- [ ] Told "not the same" → **asked which axis** before acting (after one wrong guess, asked not guessed), and compared the **reference itself** at the element × breakpoint × theme, not from memory?
- [ ] Parity target expressed in **measured device-pixels at the actual render scale** (not user-space units — equal user-units ≠ equal pixels), and same-axis oscillation treated as a **duplicate-implementation-at-different-scale** signal (measure the ratio, don't tune)?
- [ ] No status is green-with-a-caveat — a status the author can immediately qualify is **downgraded**, not asserted beside a hedge (`report-format.md`)?
- [ ] UI change: headed-browser receipt on the exact route after the action (screenshot or equivalent) — and the receipt is a **valid non-empty image**, not a proxy/504-wiped stub that passes a bare existence check (existence is not content — `full-map.md` principle 2), captured from a **clean or separate tree** (a shots script that stashes uncommitted changes discards the very diff under review), and the image **shows the target feature**, not an error / login / empty-state wall (a login page is itself a valid non-empty image — confirm the feature is present, and capture in a dev/identity-bypass mode not a route-auth-walling production build, `testing-ui.md`); and where the receipt is embedded in a PR body, it **renders for a cold reviewer** — an uploaded attachment or an in-repo image file, never a bare link to a private raw-content host that shows broken outside an authenticated session? Unit tests alone are not this box.
- [ ] **Layout invariants hold across the sweep's matrix** — no content under sticky chrome, gutters present, optional slots reserve space, no reflow on a state change, tabular numerals in columns — checked **mid-scroll and on state transitions**, both themes, not only at the top of a fresh desktop render; and **footprint tracks information** (no empty record at a populated card's size; grid dense enough at the wide viewport)?
- [ ] **Charts are legible** — a value axis or direct labels, a **keyboard-reachable** hover/focus readout of value + its date/category, real samples marked and no trend implied across sparse points — and **interaction states are consistent per component class** (hover/active/focus parity across instances; every hover affordance also reachable by keyboard and touch; tooltips add information, not a repeat of the label)?
- [ ] **Every export / print / share path inspected as its own surface** — the downloaded artifact doesn't clip off-viewport content, bakes in the axis/legend/labels that live only in interactive chrome, honors or normalizes the theme, is self-describing (title / as-of), and exports each data state honestly (never a blank canvas)?

Parity claims (the default-state canonical surface) and "Looks the same" (the four rendered-appearance axes) live
in `rendered-parity.md`.
