# Performance, database & cost review

Read this when the target has a database, makes external/API/LLM calls, runs
batch jobs, or has any hot path where latency or spend matters. Expands section
E of `SKILL.md`. The lens is two-sided: **is it fast enough, and does each unit
of work earn its keep?**

---

## Algorithmic

- No accidental O(n²)+ on a hot path (nested scans over the same collection,
  `list.contains` in a loop, repeated sort). Right structure: set/map for
  membership and lookup, not a linear scan.
- Compute-once: hoist invariant work out of loops; memoize pure results with a
  correct key; don't recompute what you already have.
- Bound the work: an operation whose cost scales with untrusted input needs a
  cap (page size, max depth, max iterations).
- **False-positive twin of the O(n²) rule: don't flag a nested scan over a
  *bounded, config-scale* collection — reserve the finding for *unbounded /
  request-scale* growth.** The shape that triggers the rule (nested loop,
  `list.contains` in a loop) is a cost only when **n grows**. Over a collection
  whose maximum size is fixed at build time — a dozen supported currencies, a
  handful of feature flags, a fixed enum, a table's columns — n² is a *small
  constant × small constant*: no growth term, no measurable cost, and a set/map
  rewrite is churn with no win. The false positive fires when a shape-only pass
  (or a `for`-in-`for` grep) pattern-matches "quadratic!" without asking **what
  bounds n**. Before filing it, trace the collection's maximum size to its
  *source*: bounded by config / enum / schema / a hard cap → **not a finding**;
  scales with request input, dataset size, or an attacker-controlled count → a
  real finding (and, when the count is attacker-controlled, also a DoS lever —
  cross-ref *Bound the work* above and the API4 response-size axis in
  `security-api.md`). Only the unbounded case earns the set/map rewrite.

## Database

- **N+1**: a query issued per row of a previous result (query inside a `for`/
  `map`/serializer). Detect by reading the data-access path and by counting
  queries per request in a test. Fix with a join, an `IN (…)` batch, or the
  ORM's eager-load. A **GraphQL resolver** N+1 is the *structural* variant this
  textual grep misses: a field resolver invoked once per parent node in a list
  fires N nested fetches with **no loop visible at any single call site** — the
  fix is a per-request batch/cache seam (the **DataLoader** pattern), and the same
  queries-per-request test catches it.
- **Serialized single-row write per item of an input collection — an N+1 on the
  *write* side that survives a missing-`await` scan because every write *is*
  awaited.** A handler that persists an incoming batch with a per-item write in a
  loop — `for (const x of items) await db.insertOne(x)` (or `.save`/`.create`/
  `.update`/`execute("INSERT …")`), common in ingest / import / webhook / fan-out
  / sync helpers — issues **one network round-trip per item**: N items pay N times
  the write latency, serially, so throughput collapses and a large batch times
  out. Every line is individually correct — the promise is awaited, so a
  floating-promise / no-`await` lint sees nothing — and no *prior query result* is
  being looped, so the read-N+1 grep and its DataLoader seam don't match either;
  the defect is purely the **round-trip count**, invisible at any single line and
  visible only as a writes-per-request count or a throughput cliff under load.
  **Fix:** collapse the loop into **one** batched write — `insertMany` / a single
  multi-row `INSERT … VALUES (…),(…)` / `COPY` / the ORM's `createMany`/
  `bulkCreate` / a batched upsert — chunked to a *bounded* number of round-trips
  where the driver caps batch size (still O(chunks), not O(rows)), inside one
  transaction where atomicity matters. **`Promise.all(items.map(x =>
  db.insertOne(x)))` is not the fix** — it overlaps the latency but still issues N
  round-trips and can swamp the connection pool or serialize on write locks; the
  lever is *one* call for N rows, not N calls at once. Preserve the per-row error
  attribution the loop gave you — a bulk write that aborts the whole batch on one
  bad row loses per-item isolation, so map failures back to rows (ordered /
  continue-on-error + collect the rejects) when partial success matters. Distinct
  from **N+1** above (a *read* per row of a *prior query result*, fixed by a join /
  `IN` / eager-load — here it is a *write* per item of the handler's *own input*,
  fixed by a bulk-write API) and from the **Sequential `await`s** / twin-projection
  concurrency bullets below (a fixed handful of *distinct* calls parallelized with
  `Promise.all` — here it is N *identical* writes that must be *batched into one*,
  where `Promise.all` is the wrong tool).
- **Indexes**: the columns in `WHERE`/`JOIN`/`ORDER BY` on hot queries are
  indexed and the index is actually used — confirm with the query plan
  (`EXPLAIN`/`EXPLAIN ANALYZE`); a seq scan on a large table is the finding.
  Watch for indexes made unusable by a function/cast on the column, or by
  leading-wildcard `LIKE`.
- **Over-fetch**: no `SELECT *` when a few columns are needed; select only what is used.
  Result sets are bounded and paginated. Prefer **keyset/seek** pagination over a large
  `OFFSET` — which is not only a scan-cost problem but a **correctness** one: `LIMIT/OFFSET`
  is *positional*, so a row inserted before the window between two page fetches shifts
  everything down and **duplicates a row across pages** (a delete before it **skips** one);
  a `(sort_key, id)` cursor is stable under concurrent writes (the cursor key must be
  unique/tie-broken — see the non-unique-timestamp-cursor trap in
  `time-date-correctness.md`). (use-the-index-luke, *no-offset*.) This drift isn't only a
  concurrent-write hazard: `LIMIT`/`OFFSET` with no `ORDER BY` that constrains rows to a
  unique order is undefined even on a **static table with zero writes**, because the query
  planner may choose a different plan — and therefore a different row order — for different
  `LIMIT`/`OFFSET` values on identical data ("you are very likely to get different plans
  (yielding different row orders) depending on what you give for LIMIT and OFFSET,"
  PostgreSQL §7.6 *LIMIT and OFFSET*); no writes between page fetches does not make plain
  `OFFSET` pagination safe — only a total, unique `ORDER BY` does.
- **Whole-collection payload for a single-entity view**: a generic detail overlay/drawer (opened
  from many pages, for many entity kinds) whose data source returns the **entire** underlying
  collection on every open — not a projection sized to the one requested id — because a few renderers
  cross-reference sibling entities. The whole-collection shape is usually defended by a real,
  previously-litigated correctness comment, which stops review from asking the **orthogonal**
  question: given that shape, why is it *also* uncached? Marked `no-store` "because the data
  can change" (or simply carrying no `Cache-Control` or validators at all — for a dynamic,
  likely-credentialed JSON response, uncacheable in practice either way), it recomputes and
  retransmits a large **build-time/batch-static**
  majority (descriptions, formulas, prompts) in full on every open, while only a small slice (a live
  status, a pending-changes index) is genuinely request-volatile. Fix: branch on the requested
  id/kind for a right-sized projection where the cross-reference requirement allows; and split
  caching — cache the deterministic majority (keyed by the data's version/build id, or HTTP
  cache/ETag) and fetch only the volatile slice per request. Pin a **byte-size ceiling** regression
  test, since this surface is paid from every mount site (grep the fan-in) and grows silently with
  the collection. Distinct from column-level over-fetch above (that trims columns; this trims the
  row-set *shape* and fixes the caching axis) — and from the redundant-full-collection-scan bullet
  below: that removes a scan whose only purpose is dedupe/freshness (which must stay current, never
  cached), whereas here the whole-collection shape is legitimate and only the volatile slice needs
  current data, so the deterministic majority is safe to cache.
- **Push work to the DB**: filter/aggregate/join in SQL, not by pulling rows into
  app memory and looping. But don't hide an unbounded computation behind a view.
- **Connections & transactions**: a pooled connection (not one per call) — and
  likewise reuse one HTTP/SDK client per process, since constructing a fresh
  client per call throws away its connection pool; transactions scoped as tightly
  as correctness allows; no long transaction held across a network/LLM call (lock
  contention); no application logic inside a DB lock window. A borrowed/checked-out pool connection must be
  **released on every path including the error/throw path** (the general form is `security-appsec.md`
  A10) — a leaked checkout starves the pool under load; watch **pool exhaustion** (active connections
  trending toward max with checkouts never returned) as its own symptom, distinct from constructing a
  fresh client per call above.
- **Hot partition / partition-key design (NoSQL)**: a low-cardinality or skewed
  partition key (a status enum, a single active tenant, a monotonically increasing
  timestamp prefix) concentrates traffic on one physical partition regardless of the
  table's overall provisioned or on-demand capacity. DynamoDB caps throughput **per
  partition**, not just per table: "Every partition in a DynamoDB table is designed to
  deliver a maximum capacity of 3,000 read units per second and 1,000 write units per
  second" (AWS, DynamoDB partition-key best practices) — a hot key throttles long before the
  table-level limit is anywhere near reached, and raising table-level provisioned or
  on-demand capacity does not fix a single-partition hotspot. Fix: choose a
  high-cardinality key that spreads access evenly, or shard a naturally hot key with a
  random or calculated suffix (write sharding) and fan the read back in.

## Schema & data migrations (safety)

Migration safety is filed in domain E but is **reviewed here even when the PR
carries no query-performance change** — so domain E is not marked N/A once a diff
touches a migration, and domains F (`reliability-error-handling.md`) and K
(`release-engineering.md`) route to this section rather than restating it.

A migration is a deploy-time hazard, not just a query. Check:
- **Locking**: `ALTER TABLE` / `CREATE INDEX` on a large table without the
  non-blocking variant (`CREATE INDEX CONCURRENTLY` in Postgres — use the engine's
  online-DDL equivalent elsewhere, e.g. MySQL `ALGORITHM=INPLACE` or gh-ost; plus
  safe column-add order) locks writes and can take an outage.
- **A failed or transaction-wrapped `CONCURRENTLY` build is its own hazard.** On Postgres a
  failed concurrent index build "will fail but leave behind an 'invalid' index" — one "ignored
  for querying purposes" that "will still consume update overhead" (Postgres docs); recover by
  dropping and retrying, or `REINDEX INDEX CONCURRENTLY`, never by assuming the index is simply
  absent. And `CREATE INDEX CONCURRENTLY` **cannot run inside a transaction block** (a regular
  `CREATE INDEX` can), so a migration runner that wraps each migration in one transaction by
  default must use its escape hatch or the concurrent build fails outright.
- **Backward compatibility during rolling deploy**: old and new code run
  simultaneously mid-deploy — a migration must be compatible with both. Follow
  expand → migrate → contract: add the new column/table (nullable), backfill,
  switch reads/writes, then remove the old — across separate deploys, never in
  one destructive step.
- **`RENAME COLUMN` / `RENAME TABLE` is the canonical accidental in-place break.**
  A bare Postgres rename is metadata-only and fast, so it *looks* atomic and safe —
  but it is a **backward-incompatible interface change**: old pods still running
  mid-deploy select/write the old name, which no longer exists, and error until the
  rollout finishes. File it as a **compatibility** hazard, not a locking one (it
  takes no meaningful lock). The expand → migrate → contract path above *is* Martin
  Fowler's **parallel change** (also known as expand and contract) — "a pattern to
  implement backward-incompatible changes to an interface in a safe manner"
  (`ParallelChange`);
  a rename must run it (add the new name alongside the old via a column or view, cut
  readers then writers over, drop the old in a later deploy), never as one step.
- **`NOT NULL` without a default** on an existing table breaks inserts from old
  code and can rewrite the whole table; add nullable + default first, backfill,
  then enforce. This is conservative, though — it omits *what actually triggers the
  rewrite*. A **non-volatile (constant) default is metadata-only**: Postgres stores
  the value in the catalog, "making the `ALTER TABLE` very fast even on large tables
  … In neither case is a rewrite of the table required" (`sql-altertable.html`). A
  full **table-and-index rewrite** is forced only by a narrower set — flag these
  four by name: a **volatile default** (e.g. `clock_timestamp()`), a **stored
  generated column**, an **identity column**, or a **column whose domain type has
  constraints** — which "will cause the entire table and its indexes to be
  rewritten" (a *virtual* generated column never does). "We added a default, so it's
  safe" is the false friend. (This **rewrite** is a distinct mechanism from the
  constraint-family **validation-scan-under-lock** below: a rewrite rebuilds every
  row and index; a validation scan reads existing rows under lock without rebuilding
  them.)
- **Backfill** runs **outside** the DDL transaction, in bounded batches, so it
  doesn't hold a lock or blow up the transaction log.
- **Rollback path** exists and is tested; the migration is idempotent/resumable.
- **Take the rollback snapshot before the mutation, not after.**
- A migration that transforms data must not degrade it — cross-reference the
  monotonic-quality invariant in `data-quality.md`.
- **Lock *acquisition* is a hazard, not only lock *duration*.** Even an instant, metadata-only DDL
  must first **acquire** its lock; in PostgreSQL `ALTER TABLE` takes an `ACCESS EXCLUSIVE` lock that
  conflicts with every other mode. A single long-running transaction on the target makes the fast
  DDL wait — and because the lock manager grants a request only if it conflicts with no existing
  **or already-waiting** lock (`src/backend/storage/lmgr/README`), the pending `ACCESS EXCLUSIVE`
  then makes **every later request queue behind it** — a fast migration becomes a table-wide stall
  (the wait-queue / FIFO rule; the user-facing `explicit-locking` docs describe the wait but not
  this queue effect by name). Check: run DDL with a bounded `lock_timeout` + retry/backoff, and
  confirm no long transaction is open on the target.
- **Backfill throttles on an observed backpressure signal, not just batch size.** Bounded batches
  cap transaction-log growth, not replica lag or I/O saturation; the loop reads a live signal
  (replication lag, load, error rate) and pauses above a documented ceiling — a fixed inter-batch
  sleep with no signal is not a throttle (gh-ost's replica-lag throttling, already named above, is
  the reference shape).
- **The constraint-add hazard is a family, not just `NOT NULL`.** Adding `UNIQUE` / `FOREIGN KEY` /
  `CHECK`, or changing a column type, on a populated table triggers the same full-table
  validation-scan-under-lock already flagged for `NOT NULL` — a reviewer matching the literal
  `NOT NULL` misses the siblings. Use the two-phase form: `ADD CONSTRAINT … NOT VALID` (commits
  immediately, no scan) then a separate `VALIDATE CONSTRAINT` (weaker `SHARE UPDATE EXCLUSIVE` lock,
  existing rows only); for uniqueness, `CREATE UNIQUE INDEX CONCURRENTLY` then `ADD CONSTRAINT …
  USING INDEX`; treat a type change as a rewrite hazard on the same expand-contract path. (Distinct
  from the soft-delete `UNIQUE` partial-index rule in `data-quality.md`, a NULL-semantics bug, not a
  lock/scan-cost one.)
- **`migrate` is dual-write plus a completion proof, not one step.** While the backfill runs, every
  write path writes **both** the old and new location so no row lands only in the old shape; before
  cutting reads over, the two are verified to **agree** with an explicit zero-remaining-gap check —
  not "the backfill job exited 0" — gating the enforce/contract step. Distinct from the cross-system
  dual-write in `reliability-error-handling.md` (DB + bus atomicity); this is the same-table case.

## External / API / LLM calls — the cost-and-value lens

The org-level frame is **FinOps** — cost as a continuous practice, not a one-time audit:
**inform** (tag/allocate spend to a team, feature, or environment so it is *visible* and
attributable), **optimize** (rightsize, commit/reserve steady load, kill idle or orphaned
resources), **operate** (a budget with an **anomaly alert** and a named **owner**). A cloud bill
with no allocation/tagging, no owner, or no anomaly alert is a finding independent of any one
call's cost — and, per `release-engineering.md`, buying a cost tool before the spend is allocated just
visualizes an unattributed bill.

Every billable or slow call must map to value delivered.
- **Necessity**: is the call needed *now*, or is it "call it every run/every
  request" out of habit? Unchanged inputs should not be re-fetched, re-embedded,
  or re-scraped. Cache by a correct key with correct invalidation. The sharpest
  version is an external call in the render body of a dynamic / `no-store` page
  (or a hot handler): it fires on *every* view, bounded only by how often humans
  or bots hit it — invisible until the bill or a rate-limit lands. Data identical
  for all viewers is cached globally, not per user.
- **Near-static config**: schema, field definitions, enum/dropdown options,
  feature flags, and other slowly-changing config fetched at request rate are
  effectively constants pulled over the wire on every call. Cache with a long TTL,
  or promote genuinely fixed values to committed configuration with a startup
  check that they still match the source — so drift fails loudly at boot instead
  of silently.
- **Redundant full-collection scans**: "fetch the whole list/table to find or
  dedupe one item" is O(collection) calls (pagination) for an O(1) need; doing the
  *same* scan twice in one logical operation (a handler scans, then a helper it
  calls scans it again) doubles it. Fetch once and pass the result down, or use a
  targeted lookup. Do **not** cache a scan whose purpose is dedupe or a freshness
  check — correctness needs current data there; remove the redundancy, don't stale
  it.
- **Batch** where the API allows (one request for N items beats N requests);
  **de-dupe** identical concurrent calls (single-flight).
- **Events over polling**: replace tight polling with webhooks/streaming where
  available; if polling, back off and use conditional requests
  (ETag/If-None-Match/If-Modified-Since).
- **Spend governance**: enforce caps in code **before** the call — per-call,
  per-session/request, **and** a global/daily/monthly cap for scheduled or
  unattended jobs (a per-run cap alone won't stop a runaway schedule). Circuit
  breakers on 402/429; bounded retries with exponential backoff + jitter that
  honor `Retry-After`, kept to **one** layer — a custom retry loop wrapping an SDK
  that already retries multiplies requests (N × M) on every transient error.
- **The spend-safety holes** (verify each — two unrelated engagements independently
  hit them):
  - **A cap that defaults to off is not a cap.** Check the *default value* of
    every spend/row/rate cap; a per-run cap whose env var defaults to
    `0`/unlimited leaves a bare, freshly-configured run bounded only by the global
    aggregate. A paid pass with **no dry-run/apply switch at all** is the same
    gap.
  - **A ledger loader that fails open.** `try { readWholeFile } catch {
    events = [] }` on a spend/rate accumulator zeroes month-to-date on *any* read
    fault (permissions, IO, truncation) and disables the ceiling. Branch
    **ENOENT** (absent → empty is correct) vs a fault on a **present** file (fail
    closed). **Test the present-fault branch:** unreadable path (`EACCES`), path
    is a directory (`EISDIR`), truncated/invalid body — `guard` must refuse the
    paid call, not proceed as if spend were zero.
  - **`SELECT sum()` then check-then-act is not atomic.** Concurrent callers each
    read the pre-spend total and both spend. Use an atomic reservation
    (insert-the-charge-first, or a transactional decrement/lock) — and a
    reservation a crashed worker never settles must **fail closed** (keep counting
    it against the budget) until a TTL or reconciliation reclaims it, or the
    ceiling leaks upward one dead worker at a time.
  - **Inaccurate cost math silently mis-drives the gate.** If the number feeding a
    spend cap charges cache-read / cache-write tokens at the full input rate (or
    ignores each token class's real price), it overstates spend and throttles or
    degrades work early — sometimes burning budget on a fallback that then blocks
    the real result; an *understated* number lets spend run past the cap. Bill
    each token class at its documented rate.
  - **An in-process singleton guard does not hold across processes.** A
    `globalThis` "is a job running?" flag or single-flight promise is per-process;
    if a second process (scheduler, worker, replica) shares the datastore, the
    guard is an illusion — verify it against the real process model (e.g. an
    entrypoint that runs `worker &` alongside the server).
- **Calibrate before a big paid run**: dry-run a small **zero-write** sample,
  measure real cost-per-call and failure rate, then extrapolate and get sign-off
  before the full apply. Don't discover the bill after the batch.
- **LLM specifics**: `max_tokens` and `timeout` set; prompt/response sizes
  bounded — but a *size* bound is not a drop-priority: what silently gets shed when the
  assembled input overflows (often the system instructions) is governed by a correctness
  check at the context-assembly seam (`testing-ai-evals.md`), not by this cost bound; a deterministic
  fallback path for when generation fails, with a
  counter reporting how often the fallback fired; don't ask the model to do work
  a function can do (see `security-ai-agents.md`). On cost:
  - **Prompt-cache breakpoint**: put the cacheable marker on the longest *stable*
    prefix (system prompt, instructions, schema, few-shot) and keep per-call
    content after it; a marker on content that varies per call caches nothing, and
    a prefix below the provider's minimum cacheable token count is a silent no-op
    — verify the threshold against the provider's current docs.
  - **Cache TTL vs inter-call latency**: a short cache TTL can expire *between*
    reuses when slow work (another call, a tool loop, research) runs in the gap,
    wasting the cache. Match the TTL to the real gap, or reorder work so cached
    calls sit close together.
  - **Token-count round-trips**: a separate `countTokens`-style call before each
    generation adds a round-trip and another rate-limited request (usually free of
    token charges, but latency and a failure point) — justify it or drop it.

## Caching & memoization

- Correct key (includes every input that changes the result; per-user/tenant
  where results differ) and correct **invalidation** (a stale-cache bug is worse
  than no cache). No caching of sensitive/per-user data in a shared cache.
- Cache invalidation of derived entries, key cardinality, expiry stampede and refresh-on-every-read depth: `performance-latency-depth.md` — **read it when** the target has an application-level cache layer (memoize, Redis, CDN) or a 🚩 grep hit below names one of those shapes, at any scope.
- Bounded size / TTL / eviction; a cache that only grows is a leak.
- **Cache-aside write race.** Read-miss → load → set can interleave with a
  concurrent write so the cache ends up holding a value already superseded. Order
  it **write-store-then-invalidate** (not set-after-write), use versioned keys, or
  a delayed double-delete — a naive read-through caches a stale value with no
  conflict to warn.
- **Negative caching.** Caching a not-found / error masks a later create or a
  transient failure (stale 404s, cached errors); give negatives a **short,
  re-checkable TTL**, never the positive TTL.
- **Authoritative vs advisory — state which.** A cache treated as **source of
  truth** (write-only-to-cache, no durable store behind it) turns an eviction into
  **data loss**. (Identity-keyed caching as an authorization surface —
  `private`/`no-store`, per-principal keys — is `appsec-edge.md` A01.)
- **A shared cache must key on whatever varies the representation.** When a response differs by
  request header — `Accept-Language`, `Accept-Encoding`, a currency/tenant negotiated from a
  header — a shared or CDN cache that ignores it serves one visitor's variant to another
  (English to a German reader, gzip to a client that can't decode it). HTTP formalizes the key
  rule: a cache "MUST NOT use that stored response without revalidation unless all the presented
  request header fields nominated by that Vary field value match" (RFC 9111 §4.1), and `Vary: *`
  never matches. Include every representation-varying dimension in the cache key (a correct
  `Vary`, or explicit key dimensions). Distinct from the identity/authz `Vary` rule in
  `appsec-edge.md` (threat: a cross-user *auth* leak) — this is content-negotiation
  correctness.

## Concurrency, memory & payloads

- I/O-bound work is async/parallel where safe; CPU-bound work isn't blocking the
  event loop / request thread. Backpressure and timeouts on every external call.
- Handler `await` ordering (sequential independent awaits, a shared source re-read per projection, an expensive `await` above an early return): `performance-latency-depth.md` — **read it when** a request handler, page loader or resolver assembles a response from several async calls, or a 🚩 grep hit below names one of those shapes, at any scope.
- No unbounded growth: ever-growing lists/maps/caches, accumulating `defer`s,
  unclosed resources. Stream large data instead of buffering it all in memory.
- **Every append-only store on disk names a reaper — unbounded growth fills the disk, a
  total outage.** Distinct from the in-memory growth above: logs, temp/scratch files, an
  audit/event table, a dead-letter queue, a metrics/trace store, or an uploads / on-disk
  artifact directory — a filesystem path with no eviction primitive, distinct from the
  in-memory/Redis cache under *Caching & memoization* above — that only ever grows will
  eventually **fill the disk and take the whole host down** (a slow-motion, time-triggered
  outage no single request reveals; a full disk can also halt the database). For each, confirm a **retention/rotation policy with an actual
  reaper** (log rotation with a size+age cap; a TTL / partition-drop on the audit/event
  table; DLQ trimming with depth alerting; temp-file cleanup that also runs on the **crash
  path**, since a crashed process skips its own `finally`) and a **disk-headroom
  monitor/alert ahead of full** (a free-space threshold, not the outage). A store that grows
  with traffic with no bounding mechanism is the finding. (Outage consequence →
  `reliability-error-handling.md`; alert wiring → `observability.md`.)
- Payloads are reasonable; no shipping a megabyte to render a number.

**🚩 grep**: queries inside `for`/`map`/`.each`; `SELECT *`; missing `LIMIT`;
large `OFFSET`; `.all()` then filter in code; identical HTTP/LLM calls with the
same args; an external call in the render body of a `no-store`/dynamic page; the
same full-collection scan run twice in one operation; a fresh SDK/HTTP client
constructed per call; a pool checkout not returned on the error path (connections trending to max =
pool exhaustion); no `timeout=`/`AbortController` on network calls; `while
True` poll loops; `CREATE INDEX` without `CONCURRENTLY`; `ADD COLUMN … NOT NULL`
with no default; `ADD CONSTRAINT` with no `NOT VALID`; `ALTER COLUMN … TYPE` on a big table; a
`RENAME COLUMN`/`RENAME TABLE`/`RENAME TO` or ORM `rename_column` (lock-free but a
backward-incompatible break for old code still running mid-deploy); DDL with
no `lock_timeout`; a backfill loop with a fixed `sleep` and no lag/health read; a
low-cardinality or skewed NoSQL partition key (single-tenant, status enum, monotonic
timestamp prefix) concentrating traffic on one partition; unbounded in-memory caches/dicts as module globals; a write invalidating only the
entity's own cache key with no derived-key fan-out; a cache key built from raw/unbounded input; a
shared/CDN cache with no `Vary` or key dimension for `Accept-Language`/`Accept-Encoding`; `CREATE
INDEX CONCURRENTLY` inside a transaction block or a left-behind invalid index; retry loops
with no cap; a custom retry loop wrapping an auto-retrying SDK; a prompt-cache
marker on per-call-varying content (or a long static prefix with none); a
`countTokens` call before every generation; cost math charging cache-read/write
tokens at the full input rate; a per-run cap whose default is `0`/unlimited; a
`catch` that sets a spend accumulator to empty; `SELECT sum(...)` then an
app-side spend decision; a `globalThis`/in-process job guard shared across
processes; a cache read → origin recompute with no single-flight (stampede on
expiry); a cache that stores a not-found/error under the positive TTL; a
handler/loader with independent `await`s run in top-to-bottom order where none
reads an earlier call's result (accidental serialization, not a genuine
dependency); a `Promise.all`/`gather` immediately followed by a standalone `await`
whose arguments don't reference the group's results (an independent read appended
past an existing concurrent group instead of folded into it); a handler `await`ing
two helpers that each re-read the *same* source to build different projections
(fetch-per-projection instead of read-once-derive-both); an expensive `await`
(DB/API/LLM/full-collection read) placed above an early return whose returning (hot) branch
never reads its result (paid and discarded every request — move the call below the return or
make it lazy); an `await`ed single-row write (`insertOne`/`save`/`create`/multi-row
`INSERT`) inside a `for`/`map` over an *input* collection (serialized round-trips,
correctly awaited so a missing-`await` scan passes — collapse to one bulk write, not N
parallel writes).
