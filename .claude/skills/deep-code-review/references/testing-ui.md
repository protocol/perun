# Testing rendered UI and browser specs

Read this when the target renders a UI or ships browser / E2E specs. Split from `testing-and-evals.md`; the general test taxonomy and smells there apply to every review.

## A conditional-render behaviour needs a rendered-DOM assertion, not a source scan

A "show more" disclosure that never actually collapsed shipped through
thousands of green unit tests (issue #1105). The tests were **source
scans**: a regular expression over the component's source *text*, pinning
that certain strings appear in a certain order. A source scan proves the
author typed certain characters; it cannot observe conditional rendering —
the bug was a list sliced by a live count sitting next to a *second*,
unconditionally-mapped list of the same rows, so every row always rendered
regardless of what the "collapsed" string check asserted. A single
screenshot caught it.

**The rule.** Any conditional-render behaviour — collapse/expand, a gated
section, an empty state, a disabled state — needs **at least one test that
renders the component and asserts what is and is not in the DOM**, before
and after the interaction. A test that reads the component's source as text
(`fs.readFileSync`/`open()` plus a regex or `.includes()` over `.tsx` /
`.jsx` / `.vue` / `.svelte` content) is fine as a **lint-shaped invariant**
(an import-ban, a banned-pattern check) but is **never behaviour evidence**
— it cannot fail when the markup renders correctly in source and wrong at
runtime, which is exactly the bug class above. Review flags a **behaviour
claim** whose only test is a source scan:

```js
// NOT evidence the disclosure collapses — proves only that the string
// "hidden" appears somewhere in the component's source text.
const src = fs.readFileSync('./Disclosure.tsx', 'utf8');
expect(src.includes('hidden')).toBe(true);

// Evidence: render it, drive the interaction, assert presence/absence.
render(<Disclosure items={rows} />);
expect(screen.queryByText(rows[5].label)).not.toBeInTheDocument(); // collapsed
fireEvent.click(screen.getByRole('button', { name: /show more/i }));
expect(screen.getByText(rows[5].label)).toBeInTheDocument();       // expanded
```

**Mechanism.** `scripts/source_scan_tests.py` (opt-in via
`DCR_SOURCE_SCAN_LINT=1` in `templates/dcr-gates.sh`) is a heuristic lint,
not a parser: it lists test files (`*.test.*`, `*.spec.*`, `__tests__/`,
pytest's `test_*.py`/`*_test.py`) that read a UI source file (`readFileSync`,
`fs.promises.readFile`, a `?raw` import, Python `open()`/`Path().read_text()`,
or a path via a variable) and check it with a regex/`.includes()`/Jest
matcher (`.toMatch(`/`.toContain(`/`.toMatchSnapshot(` count too), with
**no** render/mount/`screen.` call anywhere in the file, printing
`path:line` for each. A file carrying both a check and real render coverage
is exempt (under-flag is the safe direction) — so is a comment/string
mentioning `render(`/`mount(`, and so is a plain `.ts`/`.js` or other
(`.astro`) component: only `.tsx`/`.jsx`/`.vue`/`.svelte` are seen. Fails
closed (exit 2) on an unreadable test file or zero files found, unless
`--allow-empty`. A flagged test is a lead for a human to add the missing
rendered-DOM assertion, not an automatic defect.

**Legacy source-text tests tax a later file split — a cost the scan above doesn't measure.** Each
lint-shaped regex-over-source check hardcodes the file's path/layout, so splitting the file repoints
every one (one observed run: 74% of a page's tests were source-text regexes; a 2.1k-line split
repointed 32 of them). Mitigate with: a **shared source reader that throws loud on a missing path**
(a moved file fails every dependent check by name, not silently); a **render-loader** shared per test
file as the on-ramp from source-text to rendered-DOM checks (+0.8s/file, suite time flat); and a
**ratchet on `scripts/source_scan_tests.py`'s finding count** against a stored baseline — new work may
not raise it, even while legacy findings stay tolerated. `source_scan_tests.py` itself has no
baseline support today; a wrapper that stores and diffs its finding count against a baseline is to
be built, not assumed to already exist.

## Prove a rendered-layout claim with geometry, not class names

A UI test that asserts **the class that is supposed to produce a layout** —
`expect(pill).toHaveClass(…)`, `toBeVisible()`, a markup snapshot — proves only that
the author wrote the class they typed; it passes while the two elements render **on
top of each other**. Overlap, collision, and clipping are **geometric** properties,
provable cheaply and deterministically, and a class assertion can never catch them.

For any pair of adjacent elements whose collision is user-visible (a label + its
status pill / badge, a row's text + its action cluster, a header + an overflow
control), the test that counts is a **rendered bounding-box assertion**, run at
**each width the project already screenshots** (an overlap is width-dependent and
usually shows only at the narrow one):

```js
// Playwright: adjacent elements must not intersect at the target width.
// boundingBox() returns null for a non-rendered element — assert presence first.
const a = await label.boundingBox();
const b = await pill.boundingBox();
expect(a && b).toBeTruthy();             // both rendered (not null)
const intersects = (r1, r2) =>
  r1.x < r2.x + r2.width && r2.x < r1.x + r1.width &&
  r1.y < r2.y + r2.height && r2.y < r1.y + r1.height;
expect(intersects(a, b)).toBe(false);    // non-intersection
expect(a.width).toBeGreaterThan(0);      // and neither collapsed to zero
```

Equivalent primitives elsewhere: `getBoundingClientRect()` pairs in a browser-backed
unit runner, or `elementHandle.boundingBox()` per locator. Two companion assertions
share the mechanism:
- **Clip / truncation:** `scrollWidth > clientWidth` on an element that must not
  ellipsise.
- **Disabled-looks-disabled:** assert the **computed** affordance (`opacity`,
  `cursor`, or painted colour) of a disabled control, not the `disabled` attribute or
  the class — an attribute that blocks the click while the control still *styles* as
  live is a dead control that looks clickable.

**Scope discipline — invariants, not pixels.** These assertions are for
**non-intersection and non-clipping**, which hold on every renderer. They are **not**
for absolute positions or exact widths, which are renderer- and font-metric-dependent
and produce the cross-OS flake the bar warns against (the renderer-tolerance / pinned-
exception discipline, `ux-gates.md` gate 3). The assertion is "these two do
not overlap," never "this is 132px wide." Show it **red before / green after** the
fix, like any regression test. This is the mechanical proof behind the
screenshot-inspection checklist's **overlap** and **clip** items
(`ux-gates.md` gate 1).

## Capturing the pre-hydration render — the disabled-until-hydrated write control

The geometry assertions above run against the *hydrated* DOM, and one gate-1 defect is
invisible there: a write control gated on client-only state (`useSession` / `useAuth`) is
server-rendered `disabled` and enables only once the client bundle hydrates, so for the
SSR → hydration window it looks like a permanent dead control (`ux-gates.md` gate 1,
*not-dead-before-hydration*). Catching it needs a snapshot taken **before the client bundle
runs** — three captures, cheapest first:

- **Server HTML** — fetch the route's server-rendered markup with no JS executed (the raw
  SSR/SSG response, the same bytes the user first receives) and parse it.
- **JS-disabled render** — load the route with scripting off (Playwright:
  `browser.newContext({ javaScriptEnabled: false })`), which freezes the pre-hydration paint.
- **Throttled capture** — screenshot within the hydration window under slow-CPU emulation;
  least reliable (a race), used only when the two above cannot reach the route.

The assertion is the same across all three: a control that **will** become interactive must
not present as a bare `disabled` (or `aria-disabled="true"`) with **no loading sibling in its
container** in that pre-hydration snapshot — it carries a skeleton/spinner affordance, or is
optimistically enabled (its click captured for replay, never a no-op).

```js
// Playwright: the pre-hydration paint must not show a dead write control.
const ctx = await browser.newContext({ javaScriptEnabled: false });
const page = await ctx.newPage();
await page.goto(url);                               // server HTML, no hydration
// scope to the control's own wrapper so the affordance is a sibling, not page-global
// (a page-wide match would pass on any unrelated spinner; a broken scope that matches
// nothing would fail every disabled control — stricter than the standard, gate 1 forbids):
const box = page.locator('[data-testid="composer"]'); // the write control's container
const btn = box.getByRole('button', { name: /add|submit|post/i });
const disabled = (await btn.getAttribute('disabled')) !== null
  || (await btn.getAttribute('aria-disabled')) === 'true';
const affordance = await box
  .locator('[aria-busy="true"], [data-loading], .skeleton, [role="status"]').count() > 0;
expect(disabled && !affordance).toBe(false);        // dead-until-hydrated is the defect
```

This is the **positive control** for the *not-dead-before-hydration* detector — the instrument
that converts the static `disabled={!session}` *lead* into a finding (principle 2: *an absence
is evidence only after a positive control fires*). Where the harness cannot produce any of the
three captures for a route, the item is **could-not-check** and fails **open**; a missing
snapshot is not a clean pass (`ux-gates.md` gate 1). It complements
`domain-p.md`'s SSR/static-HTML inspection, which catches hydration-*nesting* faults
in the same server-rendered output.

## Assert a client-only element's absence only after hydration completes

A `querySelector` run right after a heading wait can execute before client hydration replaces the server-rendered markup, so a real client-only element looks absent and a bug reads as a false negative. Wait on a hydration-complete signal (a `data-hydrated` marker, an attached handler, or the element's enabled state), not a fixed sleep: a few seconds of `sleep` is the field workaround and violates the no-fixed-sleeps rule. Finding: an absence assertion gated only on a text or heading wait, or on a sleep.

## A rewritten browser spec names its retired coverage and pins the wiring it can no longer reach

The geometry assertions above prove a rendered claim you can still reach. This is the
opposite case: a redesign makes a spec's target surface **structurally unreachable in the
test environment** — a surface that now renders only user-submitted content while the
test store is intentionally empty, so there is nothing to drive the interaction — and the
spec is correctly rewritten against a different surface. The trap is that the rewrite
**silently drops** what the old spec covered: surface A and surface B both exercised an
overlay; B is redesigned to nothing-to-click; the spec moves A-only; a later change
removes B's wiring (the feed's import of the shared overlay-link component) and **no test
goes red**, because the only spec that covered B is gone.

When a spec is rewritten because its surface became unreachable, three things are owed —
and their absence is a finding:

1. **Name the retired coverage as a gap.** What did the old spec assert that the new one
   does not? A dropped assertion is an *absence*, and an unrecorded absence reads as
   coverage (principle 2: *an absence is evidence only after a positive control fires*).
   Record it where coverage gaps are already tracked (the *honest coverage taxonomy*
   in `testing-and-evals.md`), not in a commit message the next reader never sees.
2. **State whether the wiring is now unverifiable via a browser test** without seeding
   the store (or standing up a costly fixture), and why — so the gap is a decision, not
   an accident.
3. **Add a source-level structural gate that pins the wiring** the browser spec can no
   longer reach: a unit/source assertion that the feed component still imports and uses
   the shared overlay-link component (the pattern the codebase's other overlay-wiring
   tests already use). This guarantee is **weaker** than the browser scenario it replaces
   — it proves the component is *referenced*, not that the interaction *works* — so it is
   a **named fallback for a retired check, never a substitute** that lets a team trade
   rendered coverage for import checks and call the surface covered.

## A state-dependent spec must assert its precondition, not lean on a default

A browser / E2E spec that depends on an **implicit UI default** passes only by
coincidence, and the coincidence breaks silently:
- **A flipped default breaks specs that leaned on the old one — at the browser tier,
  not on commit.** A spec that asserts on content visible only while a card is
  *expanded*, or that clicks a bulk "Expand all" a redesign already removed
  (`if (await btn.count()) await btn.click()` — a no-op when the count is `0`), is
  green *only because the default happened to match what it needed*. Flip the default
  and it fails on the slow gate. Make each such spec **drive the state it needs
  explicitly** (open/collapse the specific control by its own affordance), and prefer
  an explicit state assertion over a best-effort "click if present" — a control the
  redesign has since removed silently leaves the precondition unmet.
- **Pin the equivalence between a "should-render / should-expand" predicate and the
  set it gates.** When one boolean decides whether to show or expand something and a
  *separate* path builds what renders inside, independent computation lets them drift —
  the predicate says "expand" but the body is empty, or it collapses a group that has
  content. Derive both from the same source where possible, and pin
  `predicate(x) === (renderSet(x).length > 0)` **in both directions and non-vacuously**
  (at least one input exercising each branch), so a later edit to either side cannot
  silently make them disagree — the class of bug where a "smart default" hides real
  content or expands an empty container.

## A visual receipt proves the feature only past the auth wall

- **A visual receipt must show the feature, not a wall past it.** When the review
  needs a screenshot of a changed screen, non-empty is **necessary, not sufficient**
  — an error, login, or empty-state page is a valid non-empty image that proves
  nothing about the change. Capture authenticated content through a **dev /
  identity-bypass render mode**, not a production build that auth-walls every route
  (which screenshots a login page perfectly). Prefer a **deterministic readiness
  signal** (a specific selector / text is present) over a network-idle heuristic,
  which a live hot-reload socket keeps busy so the capture waits forever and yields
  zero images. (Distinct from reproducing a **build-specific** defect, which must use
  the production build — `method-situational.md`; this is capturing *feature* evidence past an
  auth gate.)

## A locator keyed to visible text breaks the moment the component's own edit mode replaces that text

- **Prefer a stable, name-based identifier (role + name, or test id) over visible text for a locator that must survive
  re-rendering.** A row located by its currently-visible text is fragile against any
  state where the component legitimately swaps that text out — most commonly an edit
  mode replacing a read view with an input/editor. Reading a row's text, acting on it,
  then re-locating by that *same* text breaks the moment the row is mid-edit and no
  longer shows it — a false red (one observed suite's largest false-failure source,
  including its own opened editor panel replacing the read view the next assertion
  expected). Use a `data-test-id` or the item's own stable id/version field instead;
  address an already-open editor by its own container role/state, not by re-querying
  the original row.
- **Any UI interaction test must reproduce the open/activate step before typing or
  asserting — never target a locator that bypasses it.** Example: a click-to-edit
  field's spec must perform the click/focus that opens it before typing. Shortcutting
  to typing skips the interaction a real user performs, so it can't catch an
  event-bubbling regression in open/close (the skip-list gap in `ux-interaction.md`'s
  click-anywhere-to-edit bullet) — one observed defect shipped past a check that typed
  into the field's value without opening it first.
- **A programmatic `element.click()` / `dispatchEvent(...)` fires a control a real pointer
  can't reach.** Calling the DOM method directly (Testing Library's `fireEvent.click`, a
  raw `HTMLElement.click()`, or a hand-built `dispatchEvent(new MouseEvent(...))`) invokes
  the element's click handler regardless of what a real click would have hit first — an
  overlay scrim, a `pointer-events: none` sibling, a control positioned under something
  else. The test goes green on a control a user's actual click can never reach (one
  observed case: a real overlay hid a "dead" control; the programmatic-click spec never
  noticed). jsdom has no layout engine, so even Testing Library's `userEvent` cannot see an
  overlay scrim there — catching this needs a **real-browser** pointer test (Playwright/
  Cypress `.click()`, which does actual hit-testing against the rendered page) so the spec
  fails the way a user's click would. Playwright/locator `.click()` (e.g. `page.locator(...).click()`
  or `page.click(...)`) *is* the correct real-pointer form — it hit-tests the rendered page — so
  a check must not flag it. **Check**, scoped to e2e/UI spec dirs:
  `grep -rnE '\bel(ement)?\.click\(\)|dispatchEvent\(|fireEvent\.' <e2e/UI test dirs>` should
  return zero hits outside a documented, hit-tested exception.
