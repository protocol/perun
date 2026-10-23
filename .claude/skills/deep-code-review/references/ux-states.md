# Data-state depth — remainder indicators, reconciliation, empty honesty, shared-hook readiness (domain P)

Read this when a list/table/dashboard caps or slices rows below a known total, a bulk
apply/import writes back per-row success/failure counts, an empty state names (or implies) a
cause, a view renders a definitive record (audit log, security events, a decision-bearing
balance/count), or more than one component consumes one shared hook/context instance. Expands
`product-ux-quality.md`'s "Every data state" base rule (empty / loading / error / partial /
overflow) with the detection and remedy depth a typical review doesn't need.

---

**A capped or sliced list needs an explicit remainder indicator whenever more rows exist than
are shown.** A `.slice(0, N)`, SQL `LIMIT N`, or `take(N)` rendering fewer rows than the
underlying `total` is truncating, not paginating, unless the cut is visible: a correct top-line
summary count ("142 issues") doesn't prove the itemized list beneath is complete — count and
rendered rows are independent reads of the same data, and nothing forces them to agree, so a
silent truncation reads as the whole set. Whenever `total > shown`, render an explicit remainder
— "+12 more," a page control, "Show all N" — never a list that just stops (Nielsen: visibility
of system status). **🚩**: a `.slice(0, N)` / `LIMIT` / `take(N)` render path whose length can be
less than a known `total`/count, with no adjacent remainder text or pagination control.

**A partial-apply operation's success counters must reconcile to the operation's own total —
when they can't, and nothing says why, the *partial* state above has quietly gone dishonest.** A
"paste/import N rows, apply what matches" endpoint typically buckets results (`applied`,
`skipped_duplicate`, `unresolved`) and also computes real per-row failure detail —
`error_count`, `errors[]` — from the same operation. The failure detail goes missing not from a
bad render branch but one layer earlier: the client's response type declares only the success
fields, so `error_count`/`errors` are dropped before any render branch could exist for them —
visible badges can sum to less than the request's own `parsed`/`total` with no indication
anything failed, an honest-looking partial render that quietly undercounts. Distinct from the
remainder-indicator rule above: there a list is truncated **in render** below a total the client
already holds; here nothing is sliced on purpose — the client's own declared type is narrower
than what the endpoint returns, invisible to anyone reading only render code. Detect by diffing
the route handler's actual response shape against the client-side type that parses it: any
server field absent from the client type — especially a count or array of failure reasons — is a
candidate silent drop; confirm by checking whether success counters can sum to less than the
total. **The remedy is both halves — the client type declares the failure fields *and* the
render surfaces them** (a count, or the first/aggregate reason); widening the type with no
render branch just relocates the silence a layer down. **🚩**: a hand-maintained client response
type narrower than what the endpoint actually returns, especially one dropping an
`errors`/`error_count`/`rejected` field; visible counts that can't be reconciled to the input
total with no "N failed" surface.

**An empty state must not imply a conclusion it hasn't earned.** "No rows shown" isn't "nothing
happened": an empty activity feed, an all-green board with no data behind it, or a zero-count
that's really an *uncollected* count all read as "all clear / no risk / no activity" when the
source may never have been queried. The empty state must distinguish *no data collected or
covered* from *collected, and genuinely none* — full-map.md principle 2 (*an absence is evidence
only after a positive control fires*) at the UI layer. Name the coverage, not only the remedy: a
bare "Nothing here" over an unprobed source is a false all-clear, not an honest empty.
(`data-freshness.md`: same rule where the number is *scored* rather than *shown*.)

**A hardcoded empty-state message that asserts a cause is a fabricated cause the moment more
than one path reaches it.** "No results — try changing filters" names one cause (an over-narrow
filter) and one remedy; honest only if a filtered-to-zero query is the *only* way `count === 0`
renders. Once a fetch error, a permission denial, and a genuine empty all fall through to the
same zero-rows branch, that copy is a guess dressed as diagnosis: a permission-denied user is
told to change filters that were never the problem, a fetch failure reads as "no matches"
(Nielsen: help users recognize, diagnose, and recover from errors). Before trusting the copy,
enumerate every path that reaches the empty branch and confirm each matches the case the message
describes; where paths diverge, branch the copy per cause or fall back to a cause-neutral empty
rather than let one hardcoded string speak for all. Extends, not restates, the coverage rule
above: that asks whether the *source was queried at all*; this asks whether the empty state's
*named cause* holds on every path that reaches it.

**A value's *stakes* decide whether degrading a fetch failure into "empty" is acceptable at all
— a third axis, independent of coverage and cause.** The coverage rule above asks whether the
copy *names* whether the source was probed; the cause rule asks whether a *stated cause* holds
on every path that reaches it, and allows falling back to a **cause-neutral empty** when paths
diverge — this rule narrows that fallback: cause-neutral wording isn't enough on a
**definitive-record surface**. A low-stakes, **supplementary** value — a related-items rail, an
optional recommendation widget — may reasonably let a fetch failure fall through to its ordinary
empty/blank render; the cost of a wrong read is small. A value the user reads as a **definitive
statement about history or state** — an audit log ("this never happened"), a security-events
list, a balance or count a decision rests on — carries no such exemption: it **must surface a
distinct, retryable error state**, never the same branch as a genuine zero, because here "empty"
*reads* as "confirmed none," and a swallowed fetch error becomes a false all-clear no copy can
fix — the defect is architectural, not lexical. Distinct from `data-freshness.md`'s
observed-low-vs-unobserved rule (a *scored* value, measured wrong) and from the silent-swallow 🚩
in `domain-f.md` / `reliability-error-handling.md` (an error *discarded* at the code
layer, with no log or signal): here the fetch error is caught correctly, and the defect is which
**rendered** state a correctly-handled failure is allowed to collapse into.

**A control hidden or disabled by permission, with no reason shown, is a defect.** If edit controls render only for members and everyone else gets a read-only page with no explanation, the user cannot tell "not allowed" from "broken". Every permission-gated surface needs a view-only state that says why and how to get access (a client gate is still not a security boundary: `appsec-design.md`). Test: render as a non-member and assert the reason text is present.

**An empty list must disclose *why* it is empty — a filter or search removed everything, versus
nothing exists yet — and any header, count, or banner above it must be gated on content, never
implying rows a filter has hidden.** These are two halves of one defect: the render never
separates *filtered-to-none* from *genuinely-none*. On the **copy** side, a single
`items.length === 0` branch reuses one reassuring, success-styled line ("You're all caught up")
for both — honest onboarding when the account is truly empty, but a **false completeness claim**
when a search matched nothing while N real rows sit hidden, so the user reads the task as done
and abandons it. Unlike the cause rule above — where the copy *names* a cause and the fix is
lexical — here the copy names nothing; it asserts a *state*, and the signal that falsifies it is
**already in the component's props and merely unread**: an unfiltered `totalCount` beside the
filtered `items.length`, or a `searchActive`/`filterActive` flag a sibling list already threads.
That single cause-neutral fallback is **not enough here**, because the two truths need different
*next actions* — reserve the positive/"nothing exists yet" copy for a zero **unfiltered** total,
and when the total is non-zero but the view is empty render a neutral "no matches" state
carrying a **clear-/adjust-filter affordance** (narrowing the fallback the same way the stakes
rule above narrows it for definitive records). On the **chrome** side, a section's header,
count, "N done" badge, or a "see all / show breakdown" affordance emitted **outside** the
content-presence conditional — a title rendered unconditionally above a row built by
`list.filter(...)` that can come back empty, with no sibling empty branch — leaves a heading
over a blank strip and an affordance pointing at nothing (a dead control, see
`product-ux-quality.md`'s *No dead controls*); gate the chrome on content-presence, or pair it with an explicit empty/no-match fallback
under the same conditional. **Detect** by grepping the empty-state string and enumerating every
path that renders it — one success-styled line reachable from both a filtered and an unfiltered
branch is the copy defect — and by finding a `.filter(...)`/search-fed list whose header, count,
or affordance is emitted before it with **no** adjacent `length === 0` branch. Distinct from the
coverage rule above (whether the source was *probed* at all) and from the *dead filter option*
in `ux-interaction.md` (an option matching zero rows in **any** data, versus a valid filter matching zero
**now**); `frontend-a11y.md` assumes the classes of emptiness already exist and enforces one
voice and one next action per class — this owns whether the filtered-vs-genuine distinction is
drawn at all.

## A correct loading/failed signal is only as good as its least careful consumer

The stakes rule above governs what a **correctly-handled** fetch failure may render as; this asks a
narrower, later question — **given** a hook/context whose contract already separates loading/failed from
a confirmed value honestly, does **every** consuming surface actually read that signal? A shared hook
reused across sibling UI surfaces (a provider/context, so two renders share one fetch instead of
duplicating it) can expose its readiness/error field correctly and still ship the exact failure it was
built to prevent, one layer up: one consumer branches on the field and renders honestly; a second, off
the **same shared instance**, destructures only the value and renders it raw. The same transient failure
surface A discloses, surface B renders as a confident wrong zero — indistinguishable from a genuine
"none" — with the only textual disclosure sitting elsewhere on the page, in a component the reader may
never reach.

**A correct contract does not imply a correct consumer, and one correct consumer does not imply the rest
are.** A reviewer who audits the hook plus the one call site that clearly does it right, and concludes
"this is handled," has verified the contract, not its adoption — the same gap the shared-component
adoption-is-total and divergent-props rules name for a shared **component** (Unified across modules,
`ux-components.md`), but a different **stakes** class: divergent props there is a visual-consistency defect (a
feature chip present at one mount site, absent at another); a sibling ignoring a readiness signal is a
**data-honesty** defect (a wrong value rendered as settled fact) — hence its place in this data-state
neighborhood, not the component-consistency one.

**Detect** by grepping the hook/context **name** itself, not just its file, to enumerate every consumer
of the shared instance — a component-scoped search misses a sibling elsewhere on the page; check each
independently for a readiness/error branch, never inferring from one correct consumer that others do
too. Verify by forcing the shared fetch to reject and loading the page at **every** consuming surface,
not only the one already known to handle it correctly.

Same all-consumers/all-call-sites sweep discipline as a write-guard covering every mutation primitive or
a soft-delete scope covering every read (`data-quality.md` §5, §6), and a normalization fix required at
every query call site (`i18n-l10n.md`) — a shared correctness property holds only where every consumer
actually exercises it, not wherever the built-once thing merely exists.

**🚩**: two or more components consuming one shared hook/context instance where only some destructure and
branch on its readiness/error field; a consumer destructuring only the value field, with no
readiness/error check anywhere in that render path, while a sibling consumer of the same instance does
check it.
