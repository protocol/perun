# Product UX depth — the enforcing gate (Phase 6 imprint) and the UI-evidence gates

Read this when a UI change is claimed verified on screenshot evidence, the project's auto-merge or CI policy gates UI changes, a Phase 6 imprint pairs this bar with a UX-evidence gate, or the task is a parity task (gate 4, the parity differ). Split from `product-ux-quality.md`, whose stance, data-state rules, encoding rules, 🚩 grep, and pre-ship checklist apply to every UI review.

## Enforcing gate (Phase 6 imprint)

**A UX-bearing change does not auto-merge on code-gate green alone.** Lint, unit tests, type-check, and
a build passing prove the *code*, not the *rendered result* — auto-merging a UI change on those plus
**presence-only** evidence (a screenshot exists but is unread) ships the exact layout regressions this
reference catches. Gate a UI-change class on the UX-evidence gate below **with its inspection cited**,
not on the code gates alone; treat a **disabled or crashed** UX-quality gate as a **P0 repair that
blocks merges of that change-class** until restored — a silently-off quality gate is worse than none, it
reads green over unexamined UI (cf. `merge-operations.md`, self-reported ≠ trusted control; and
the auto-merge-on-bot-PRs flag in `dependency-currency-and-upgrades.md`). **🚩**: auto-merge on a
UI-bearing change with only code/build/lint gates + a presence-only screenshot; a UX-quality gate
disabled "temporarily" with merges still flowing.

A standard with no gate is advisory (SKILL.md Phase 6: *pair each imprinted standard with the gate that
enforces it*). When imprinting into a project that ships a UI, pair this reference with a UX-evidence
gate — held to the skill's own gate discipline: **a gate must tell "could not check" from "found a
problem," fail *open* on the former, and never be stricter than the standard** (`frontend-a11y.md`, the
`innerText` and disabled-contrast traps; SKILL.md Phase 1, gate-vs-standard). Three gates for any UI
change, in descending confidence of what they can prove — plus a fourth that fires only on a parity
task:

1. **Screens-changed evidence — the artifact, plus the inspection it demands.** On any diff that can
   change a rendered page, require a screenshot of each affected route — the **whole affected surface**,
   not a clip of only the diff's own region (a regression on an adjacent part of the surface is never in
   a cropped shot) — at a narrow and a wide width (e.g. 390 / 1440), or an explicit
   `No UX change: <reason>` line. A screenshot proves a human/agent *looked*; it does **not** prove the
   render is correct — and "screenshot attached" **with no cited inspection** is `unverified`, not
   `verified` (the treatment a parity claim with no named surface gets). The defects that survive every
   other gate are the ones only a look at the image catches, so a UI status **names what it inspected**
   from this checklist (defined once here; a status cites the items):
   - **overlap** — no two text / interactive elements intersect (mechanical proof: the bounding-box
     non-intersection assertion, `testing-ui.md`);
   - **clip / truncation** — no unintended ellipsis or cut glyph at the narrow width
     (`scrollWidth > clientWidth`, same file);
   - **contrast** — text meets AA against its *painted* background (`frontend-a11y.md`);
   - **disabled-looks-disabled** — a functionally disabled control is *visibly* disabled (cursor /
     opacity / painted colour, not only the attribute; the *no-dead-controls* interaction-completeness
     rule in `ux-interaction.md`, seen in the render);
   - **not-dead-before-hydration** — a write control gated on client-only state shows a loading
     affordance (or is optimistic-enabled with a **replayed** click), not a bare disabled default, in
     the **pre-hydration** render; the static `disabled={!session}` tell is an `unverified` lead until
     that snapshot confirms it (principle 2), so a harness that cannot capture pre-hydration reports
     *could-not-check*, never a pass;
   - **state named** — which data state the shot is of (empty / loading / error / populated), so an
     absence reads honestly (gate 2's state coverage; the empty≠all-clear rule in `product-ux-quality.md`);
   - **sticky-chrome collision** — nothing content-bearing paints under a sticky/fixed header or bar;
     visible only mid-scroll, so it is checked at scroll offsets, not only at the top of a fresh render;
   - **gutters present** — every scroll container and sticky bar has padding, so content is not flush to
     the edge or to the chrome;
   - **optional slots reserve space** — a row's rail and baseline hold whether or not an optional
     element (avatar, badge, trend) renders; check the absent-slot variant, so a row doesn't go ragged
     when a slot collapses;
   - **no reflow on a state change** — a control keeps its box across loading→loaded and
     collapsed→expanded (a before/after box compare — the same geometry primitive as *overlap* above),
     checked on the transition, not only at rest;
   - **tabular numerals** wherever numbers stack in a column, so values don't jitter the alignment as
     they update (the tabular-figures rule of *Match a named standard* in `product-ux-quality.md`, here as a mid-update
     stability invariant).

   Of these, **sticky-chrome collision reads only mid-scroll**, and **reflow (and numeral jitter) only
   across a state change / value update** — a single top-of-page shot can't see them, so on a `FULL`
   review they're ruled across the **rendered route sweep**'s matrix (`ux-sweep.md`). **Gutters and
   optional-slot reservation read at rest** (the latter in the absent-slot data variant) — check them on
   the per-change shot too, and re-confirm in the sweep rather than defer to it. And
   **not-dead-before-hydration reads only before the client bundle runs** — a fourth timing class
   neither the at-rest shot nor the mid-scroll sweep can see, because both capture the *post-hydration*
   render; it needs a snapshot taken inside the SSR → hydration window (a pre-hydration or CPU-throttled
   capture, `testing-ui.md`), and where the harness can't take one the item is *could-not-check*,
   not clean.

   **A PR-body image embed is not evidence unless it renders for the reviewer, not just the author.** A
   `![...](<url>)` pointing at a private raw-content host — a raw-file URL requiring an auth header or
   an authenticated session a markdown renderer's plain `<img>` fetch can't supply — **may render only
   for a viewer already authenticated to that host** (and can break even for the author, under
   cross-origin cookie scoping), showing a broken-image icon for everyone else viewing the PR; on a
   private repo, that's every reviewer reading the PR body cold. The markdown tag *exists* in the diff;
   the evidence does not (existence is not content — full-map.md principle 2, the same gap the pre-ship
   receipt check in `product-ux-quality.md` closes for a captured-but-blank image; this closes it for a
   captured-but-invisible one). Gate on **visibility, not presence**: an **uploaded attachment** (the
   review platform's own image upload, served through its own proxy) or an **in-repo, diff-able image
   file** committed with the change both satisfy the bar; a link to a private raw-content host does not,
   even when the file behind it is a real, correct screenshot. **🚩**: a PR-body `![...]` whose URL is a
   raw-content-host link — not an uploaded attachment or proxied URL — on a private repo, with no
   in-repo image file backing it.

   A screenshot with an unstated inspection is an artifact read as the verification it is not.
2. **State-coverage in tests (proves the branches exist).** A component test that renders a data view
   asserts the **empty and error** branches, not only the populated one — extends
   `testing-and-evals.md`'s "test the failure, not just the feature" to UI states.
3. **Encoding self-test (heuristic — scopes its own claim).** Where a design system exists, a lint/unit
   check that no single colour token is bound to two semantic names, and that every status/delta element
   carries a non-colour channel (icon/text + `aria-label`). Both are **heuristic**: a static "one token,
   one meaning" check can't see runtime binding, and "has a non-colour sibling" false-positives on
   decorative nodes — so it **warns and lists**, never fails closed, reporting what it couldn't resolve
   as `unverified`, not clean. Model: a renderer-tolerant ratchet — a pinned exception is *allowed*,
   never *required* to exhibit. Same gate, same discipline, for **chart anatomy** (data-viz, `ux-dataviz.md`): a
   heuristic assertion that an `<svg>`/canvas chart exposes **axis tick text or a hover/focus readout
   target** and that a series isn't colour-only — it **warns and lists**, never fails closed, because it
   false-positives on a legitimately decorative chart (the `aria-hidden` + printed-number exemption
   in `ux-dataviz.md`), and whether the readout returns the *right* value stays a human inspection.

4. **Parity differ (parity tasks only — proves *equivalence*, not just that a human looked).** For a
   "make X match reference Y" task, run a mechanical differ **before** any pixel-matching and gate
   every "matches" claim on it. The differ drives both the reference and the target for each screen and
   emits (a) a side-by-side + pixel-diff **image** and (b) a **structured** mismatch list — each
   section's element inventory, present/absent per side (`scripts/parity_differ.py`); size is
   never completeness evidence. **The artifact shown to a reviewer is the diff image, never a sentence.** **Render
   both sides at the same viewport width** and diff the corresponding region — a cropped or scaled
   screenshot of **one** side is a **hypothesis, not evidence**; never infer a present/absent delta from
   one side alone. Before recording an element as app-only or design-only, **confirm its state on the
   other side**: present-but-collapsed, present-but-**disabled-by-data** (a stepper bound to one item
   has nothing to step to), or present-in-a-menu — "absent in this crop" is not "absent in the design".
   This is the evidence feeding the classification (`migration-parity.md`,
   *restyle-an-app-only-feature*): a delta that doesn't exist has no bucket, and every wrong inference
   here is one destructive edit — a removed control, a duplicated element — away. **🚩** a "missing" /
   "extra" parity call whose only evidence is a one-sided crop, or made with the other side's state
   unchecked. Load a no-routing prototype **once and click-navigate** its in-page tabs (it has no
   per-screen URL to fetch), and diff against an existing **running build** of the design if one is in
   the repo rather than reverse-engineering its source (reference-fidelity order,
   `rendered-parity.md`). It diffs **chrome / structure / styling, not data values** — diffing the numbers would flag
   real data as a mismatch and tempt the fix that fabricates (`migration-parity.md`). What it **cannot**
   prove: an intentional improvement from a regression, and its pixel threshold is **agreed, not
   derived** — a human still owns the ship call. **Parity is *set equality*, not containment — run the
   present-or-absent list above in *both* directions.** Produce it per screen as **design → app** (what
   the design has that the app lacks) *and* **app → design** (what the app renders that the design does
   not); an element on exactly one side is a finding **regardless of which side**, and the app→design
   half is the one that gets skipped. The **operative test** for an app-only element — *does removing it
   lose a user capability?* If **no**, it's pure **decoration** (an extra header, a "Showing N of N"
   line, a duplicated label): default **remove-to-match**, and "intentional extra" is the
   rationalisation that ships the mismatch. If **yes** (a per-card upvote, a filter bar, a view tab, a
   deep-link button — removing it removes upvoting, filtering, navigating), it's a **feature**: the
   default is **not** escalate-and-wait but **restyle it into the target's design language**. Deleting
   it to match the mock is a **High** do-no-harm finding, never self-certified. `migration-parity.md`'s
   *restyle-an-app-only-feature* rule governs the classification (and the
   re-express-in-the-target's-own-primitives mechanics), its severity, and the exception ledger;
   escalation to the owner is the **fallback** when no target primitive fits, not the whole answer.
   Scope all of this to **chrome / features**; **data** (values, counts, series) legitimately differs
   (`migration-parity.md`). *Done* on a parity task = the design→app list is empty; the app→design list
   is empty **or every entry is resolved** — restyled into the target's design language, decoration
   removed, or an owner-adjudicated keep/removal (a bare app→design list is not an automatic differ fail
   — the differ can't tell an intentional improvement from a regression, so that half routes to
   classification and, where needed, human adjudication); and the pixel delta is under the agreed
   threshold for every screen in the correspondence table, with those diff images attached — never an
   assertion.

Ship these **idempotent and additive**, per Phase 6 — detect-and-stop if present, add only what is
missing, defer to an existing style guide (the parity differ only when the task is a parity task).

**Drive every changed interactive control in a real browser before "No UX change".** A passing logic test proves a function was called, and a static screenshot proves someone looked; neither proves the control is reachable, visible, or in the right enabled/disabled state in the rendered page. For each changed control: open it, act on it, reload, verify it again, at a narrow and a wide width, with before/after screenshots, before the PR is marked ready.

## Layout-shift (CLS) work is a chain: land fixes with their partners

Fixing a hydration or font-swap bug can expose a larger hidden source of layout shift that the first bug masked. Measure
CLS (and the shifting element's width) before and after each fix; do not land a fix that makes a measured width or
shift worse unless its partner fix lands with it.

## A UI built in slices is not verified by per-slice tests — gate the assembled page

Every slice of one page can pass its own tests and merge while the assembled page is unreachable from navigation, view-only, or still dominated by the old layout. Before the page is called done, open it as a real user would: arrive via navigation (not a direct URL), run the reference product's core actions end to end, and run the parity check against the design reference. **Check:** the receipt names the navigation path taken and the core actions performed, not just the slice tests that passed.
