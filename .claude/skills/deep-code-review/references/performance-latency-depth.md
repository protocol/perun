# Performance depth — handler await ordering and cache expiry

Read this when the target has a server request handler, page loader or resolver that assembles one response from several async calls, or an application-level cache layer (memoization, Redis, CDN). It fires at FILE or FULL scope on what the repo contains, not only on a diff. Moved verbatim from `performance-db-cost.md`; "above" and "below" in these bullets resolve against that file's *Indexes*, *Necessity*, *N+1* and *External / API / LLM calls* bullets, and its 🚩 grep list stays there.

To measure a timing claim, run `scripts/perf_compare.sh` (hyperfine A/B against the base; rules and how to read the verdict: `tool-hub.md`), or `scripts/app_pentest.sh --load` for a running endpoint (`app-pentest.md`).

## Handler await ordering

- **Sequential `await`s with no data dependency are an accidental serialization, not
  a design choice.** A request handler / page data loader / GraphQL resolver that
  assembles one response from a few independent backend calls (a main entity fetch
  plus an unrelated sidebar, count, or config read) is often written in natural
  top-to-bottom order, `await`-ing each call before the next line runs. A call that
  reads nothing produced by an earlier call has no data reason to wait for it, yet
  still runs last — the handler pays the *sum* of every call's latency instead of
  the *max*, adding a full extra round-trip to time-to-first-byte on every request.
  The code stays correct (right data, right shape), so nothing fails; it surfaces
  only as a slow-page field report or a TTFB regression, not a test. Detect by
  listing, for each `await` in the function, whether its arguments (or a variable it
  closes over) trace back to a *preceding* `await`'s result in that same function —
  any call whose inputs don't is a parallelization candidate regardless of what it
  does. Fix by starting every mutually-independent call together
  (`Promise.all`/`Promise.allSettled`, `asyncio.gather`, an errgroup) and keeping
  sequential only the calls that truly consume a prior call's output — a call that
  reads `main.ids` after fetching `main` is a genuine dependency and correctly stays
  sequential; that shape is not the anti-pattern. Distinct from **N+1** above (a
  query *per row* of an existing result — this is a handful of independent
  *top-level* calls, present even for a single row/request) and from the
  client-side critical-request-chain waterfall in `web-fetch.md`'s Core Web
  Vitals section (the browser's dependent-fetch chain hurting LCP/TTI, versus the
  server handler's own `await` ordering hurting TTFB here). And distinct from the
  terse `async/parallel where safe` line above, which states the principle: this
  names the concrete failure shape (sum-vs-max latency), the detection trace (each
  `await`'s arguments back to a prior `await`'s result), and the genuine-dependency
  carve-out that one-liner leaves implicit. **A *correct* concurrent group already
  in the function is not proof the whole function is parallel — run that same trace
  on every `await`, including the ones *after* a group.** The recurring shape is a
  loader that already starts its first reads together (a `Promise.all`, a
  hoisted-promise pair, an `asyncio.gather`) and then, in a later change, tacks a
  new independent read on *after* the group as a lone `await`: its author added read
  k+1 at its natural point-of-use without reopening the top-of-function group, and
  its inputs never trace back to anything the group returns, so it has no data
  reason to run last yet still adds its full round-trip to the sum. The group's
  presence is the camouflage — a reviewer reads it as "concurrency already handled"
  and the change added only one line, with the group it should have joined sitting
  unchanged (often outside the diff hunk), so a diff-only pass waves it through.
  Tell it apart from a never-parallelized loader by *provenance*: the group and the
  trailing read land in different commits (blame / `git log -L` on the function).
  Fix by starting the new read *with* the group, not beside it — but preserve its
  error handling in the move: a fail-all group (`Promise.all`/`gather`) rejects as a
  whole on any member's failure and discards the siblings' results, so a read that
  carried its own `.catch`/fallback loses that isolation if it is blindly folded in.
  Hoist it to its own promise, keep the `.catch` on it (or use `Promise.allSettled`),
  and `await` it at its point of use — keeping the latency win without coupling a
  non-critical read's failure to the critical ones.
- **Two projections of one dataset that each re-load the raw source, awaited one after the
  other, pay double I/O *and* double latency — the compute-once-derive-many miss inside a
  single handler.** A request handler / SSR loader that needs two differently-shaped views
  of the *same* data (a summary card and a detail table; a totals rollup and a line-item
  list; a chart series and its CSV export) often calls two exported helpers —
  `getSummary()` and `getDetails()` — that each *internally* re-run the shared loader
  (`loadRawEvents()` then reduce it one way; `loadRawEvents()` again then reduce it the
  other) and `await`s them in top-to-bottom order. The shared read runs **twice** (2× DB
  query / file read / API call) and the two reads **serialize** though neither consumes the
  other's output — 2× the I/O *and* 2× the latency on a critical path (TTFB / SSR). Each
  helper is clean in isolation (right data, right shape), so a per-file review approves
  both; the waste lives only in the *pair* and shows only as the network tab's two
  identical source reads and a load time that is their sum. Rank the fix: **read the source
  once and pass the records into both projections** (best — it deletes the second read, and
  with one read there is nothing left to parallelize); **`Promise.all` on the two helpers
  is only the fallback for when they must stay independent — it overlaps the latency but
  still reads the source twice**, a partial fix, not the fix. Detect by listing every
  `await` a handler makes into the same data module before it branches, then confirming the
  shared loader runs ≤1× per request and any reads left separate run concurrently;
  acceptance = one source read per request, both projections' outputs unchanged. Distinct
  from **Redundant full-collection scans** (External / API / LLM calls), whose subject is a
  collection pulled for an O(1) find/dedupe it never needed — here the full dataset is *legitimately*
  required, only read once too often and shaped twice. Distinct from the **Sequential
  `await`s** bullet above, whose independent calls read *different* sources so `Promise.all`
  is the whole fix — here they read the *same* source, so `Promise.all` leaves the duplicate
  read standing. Distinct from the client-side **identity fan-out** hook in
  `web-fetch.md` (N mounted consumers each re-fetching one shared singleton, coalesced
  behind a Provider/cache): this is two sibling projections inside *one* handler, coalesced
  by hoisting the single read and deriving both locally.
- **An expensive `await` placed *above* an early return is paid on every request that takes
  the early branch — even when that branch never reads its result.** A handler / loader /
  resolver fetches something costly at the top (a DB query, an API/LLM call, a full-collection
  read) and only *then* hits a guard that returns early on the common path — a cache hit, a
  `304`, an empty/redirect/short-circuit response, a permission or feature-flag bail — where
  the returning branch does not consume the fetched value; only the *rarely-taken* rest of the
  function does. Because the fetch runs before the guard, **every** request pays for it and the
  hot branch discards the result, so the app issues and throws away that query on its most
  frequent path. It reads clean line-by-line — the fetch genuinely is needed *somewhere* in the
  function — and the waste is purely the **ordering**: the call sits before the branch that
  decides it isn't needed. Common shapes: a page loader that reads the full record/list at the
  top for an edge-case render but returns a cached or empty response on the common branch
  without touching it; a resolver that `await`s an enrichment call before an authorization or
  feature-gate early-return. **Fix — relocate the call, don't cache it:** move the `await`
  *below* the early return so only the branch that consumes it issues it, or make it lazy (a
  thunk / deferred promise the consuming branch awaits) so the hot path never triggers it.
  Caching (the *Necessity* bullet's cure above) does **not** fix this — a cached read is still a
  needless lookup on a branch that discards its result; the lever is *where the call sits*, not
  *how often it recomputes*. Detect: for each `await` in the function, confirm its result is
  read on **every** branch that can `return` after it — an `await` whose value is consumed only
  *past* an earlier `return` is the finding; acceptance = count the call's invocations on the
  early-return path (zero after the fix, one per request before). Distinct from **Sequential
  `await`s** and the **twin-projection** bullet above, whose reads are all genuinely *used* (fix
  = parallelize, or read once) — here the read is *unused on the branch that always runs*, so
  only relocating the call helps; from **over-fetch / whole-collection** above, which trim what a
  *used* result contains (here nothing on the hot path uses it); and from dead code in
  `domain-h.md` (an unreferenced function nobody calls) — here the call **runs** on
  every request and only its *result* is dead on the hot branch.

## Cache invalidation, key space and refresh

- **Invalidate every *derived* entry, not just the entity's own key.** The correct-key rule
  above covers one entry; a write must also invalidate every composite / aggregate / list /
  rendered-fragment entry that *embeds* the mutated entity (a user's name cached inside a
  rendered comment, a row inside a cached list or count). HTTP caches make the split explicit:
  a cache "MUST invalidate the target URI" on an unsafe method but treats related URIs only as
  *candidates* for invalidation (RFC 9111 §4.4) — derived-key fan-out is the application's job,
  not the protocol's. Tag each entry with a surrogate key per entity it depends on and purge by
  tag, or keep an explicit dependency index; a write that clears only `entity:{id}` and leaves
  the entries embedding it is a stale-read bug no single-key test catches.
- **Bound key *cardinality*, not just total size.** A key built from an unbounded or
  high-cardinality input — raw free text, a full query string with volatile params, a
  per-request timestamp — makes almost every lookup miss while filling the cache with
  single-use entries, so it adds latency and memory pressure for no hit-rate benefit.
  Normalize and allow-list the key inputs to the dimensions that actually recur. Distinct from
  a *wrong* key (correctness, above) and from unbounded *total size* (the eviction bullet) —
  here the key *space* is too large to ever reuse.
- **Stampede / thundering herd on expiry.** A hot key expiring lets N concurrent
  misses all hit the origin at once — an outage amplifier on an expensive origin.
  Require **single-flight** (coalesce concurrent recomputes behind one lock/lease)
  or a **soft-TTL / early-recompute** with jitter; the de-dupe under *External
  calls* above is the same mechanism applied at cache-expiry.
- **An unconditional refresh-on-every-read cache is not a stampede risk (no expiry to race), but
  paired with a query whose sort the primary key can't serve, the two compound into a full-table
  sort on every single request — check both halves, not one.** A synchronous cache getter that
  fires a background reload on **every** call — single-flighted so concurrent calls collapse to one
  in-flight reload, but with **no TTL or staleness gate** at all — looks like a reasonable "never
  more than a request or two stale, never blocks" design in isolation, and often is: the
  single-flight guard means it isn't the stampede-on-expiry case above (there is no expiry here to
  race — the reload is retriggered by call volume, not by a timer). The compounding risk sits on the
  query side: a composite primary key covering the natural identity columns (`(tenant, as_of,
  recorded_at)`) reads as "the table is indexed" at a glance, but a hot read ordering by a
  **different** leading column (`ORDER BY as_of DESC, recorded_at DESC` — newest-first by date
  rather than by the PK's leading id) can't be served by that PK — with no matching index, the
  engine scans and sorts the **whole table** on every execution (*Indexes*, above, for the
  EXPLAIN-driven detection). Reviewed separately, each half is defensible (a documented, deliberate
  cache policy; a table that visibly has a primary key); reviewed together, an unpruned append-only
  source table growing in one dimension and read frequency growing in another multiply into a
  per-request full-table sort that is invisible while the table is small. **Fix:** add an index
  matching the actual `ORDER BY` shape and, independently, consider gating the reload behind a short
  TTL so read volume stops multiplying query volume 1:1.
