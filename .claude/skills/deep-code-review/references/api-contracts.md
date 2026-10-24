# APIs, contracts & integrations

Read this when reviewing public HTTP/GraphQL/RPC surfaces, webhooks, message/
queue payloads, SDK boundaries, or any serialized state that must evolve without
breaking live consumers. Expands section I of `SKILL.md`. For authz/injection/
SSRF on those surfaces, load `security-appsec.md` and `security-api.md` (the OWASP API
Security Top 10 overlay); this file is **contract correctness and evolution**.

Standards (URLs + dates in `docs/standards-index.md`): OWASP API Security Top 10
(2023), Semantic Versioning.

---

## Detection procedure

1. **Inventory public operations** — routes, RPC methods, CLI commands that
   cross a trust boundary, event types published/consumed.
2. **For each: find the contract** — OpenAPI/JSON Schema/proto/zod/typebox/
   README table. Missing contract on a public surface is a finding.
3. **Trace one request** — validate at boundary → authorize → handler →
   response shape. Note silent coercion, extra fields stripped/kept, error
   envelope consistency.
4. **Find producers/consumers of persisted or queued messages** — version field?
   required-field additions? migration story?

---

## Public interface hygiene

- Minimal surface; hard to misuse (required auth, explicit content-types,
  bounded payloads). Breaking changes: SemVer **MAJOR** (or a versioned path/
  header) and a documented migration — silent response-shape changes are
  breakages even when status stays 200.
- Inputs validated at the boundary (schema); outputs match the documented
  schema. **Typed errors** with stable machine codes, in **one consistent,
  machine-readable envelope across the whole surface** — a registered structure
  (RFC 9457 `application/problem+json`: `type` / `status` / `title` / `detail` /
  `instance` plus extension members; obsoletes RFC 7807) rather than an ad-hoc
  shape per endpoint, so a consumer writes a single error-parsing path; do not
  leak upstream bodies (cross-ref B secrets/logging). The **stable machine code is
  itself part of the versioned contract** — changing or repurposing a code is a
  breaking change (below), so freeze it post-release and treat it as an extensible
  enum a consumer may not yet know.
- Pagination/filter/sort parameters are bounded; "return everything" defaults
  are a reliability and cost finding (cross-ref E). **A capped page that feeds a client-side filter must report truncation.** When the API offers only limit/cursor and no server-side filter, the client filters what it fetched; if the fetch stopped at the page cap, the result is a partial set, so return a `truncated` flag (or follow the cursor to the end under a stated bound) and never present it as complete. Finding: a client-side filter over one capped page whose output carries no truncation signal. Test: a fixture with more rows than the cap reports `truncated: true`. A cursor/page token is part
  of the versioned contract even though it looks like an implementation
  detail: keep it **opaque**, URL-safe, and never user-parseable — a client
  that can decode, edit, and re-encode it turns your pagination internals into
  public API you can no longer change without breaking those clients, and
  **base64-encoding an otherwise-transparent token is not opacity** (AIP-158,
  *Pagination*). Make it **tamper-resistant** too — signed or encrypted, not
  merely encoded — so a client can't forge or shift the cursor. A page token must never
  itself carry authorization: whatever offset/filter/tenant scope it encodes,
  the object/function check still has to run against the authenticated
  principal on every page — verify it with the BOLA/BFLA two-principal matrix
  (`security-api.md`, API1+API5) rather than trusting the token.
- A **throttled response carries a back-off signal**: when the API returns `429 Too Many
  Requests` (or a `503` under load), emit **`Retry-After`** so clients back off by
  instruction, not by guess — HTTP's `Retry-After` tells a client how long to wait before
  retrying, and in a `429` it is the throttle duration. Better still, emit a
  machine-readable rate-limit budget (see the IETF *RateLimit header fields for HTTP* draft
  for the current field set — the draft is actively revised, so cite it by name, not a
  pinned field list) so a well-behaved client self-paces **before** it trips the limit. A
  `429`/`503` with no `Retry-After` leaves every client to hammer immediately or back off
  blindly; "the docs say retry with backoff" is not a substitute for the on-the-wire signal
  (docs can't say how long *this* throttle lasts). This is the provider's *outbound*
  obligation — distinct from a caller *honoring* `Retry-After` on its own retries
  (`performance-db-cost.md`) and from the async-job poll cadence below.

---

## Long-running operations — an async job is its own contract

An endpoint that can't finish its work inside the request's synchronous budget must
not fake synchrony (block the caller, or return a fake `200` before the work is
done). It returns **202 Accepted** plus a second, independently-versioned
**operation / job resource**: a **stable id**; an explicit **status enum with real
terminal states** (`succeeded` / `failed` / `canceled`, never a bare boolean that
conflates "not done" with "failed" — the make-impossible-states-unrepresentable rule,
`reliability-error-handling.md`); an **error payload only on the failed state** and a
**result only on succeeded**; and a documented way to discover and poll it (a
`Location` header — or a vendor `Operation-Location`-style header — or a documented
poll URL, with `Retry-After`). A polling client must **distinguish poll-transport failure from
operation failure** — the poll `GET` returning `500` is not the same as it returning
`200` with `status: failed` (the async cousin of "check status before reading the
body", cross-ref `reliability-error-handling.md`).

- **The start call needs provider-side idempotency.** If the client retries the
  start request because the `202` was lost in transit, an **idempotency key on the
  start call** (enforced server-side; reject a reused key carrying a **differing
  body** with a `4xx` + the RFC 9457 envelope above) must fold an identical retry
  into the **same** operation — without it, a lost `202`
  silently spawns a **second** operation and the work runs twice. This is the
  provider half of the caller-side idempotency rule in
  `reliability-error-handling.md`; the job's own internal durability / compensation
  is domain W (`domain-w.md`).

---

## Breaking-change discipline for public APIs & SDK exports

The **SemVer MAJOR for a breaking change** rule above needs a *recognition taxonomy* and a
*mechanical* check — most breaks are not a removed field — and it applies to a **library / SDK's
exported symbols** exactly as to an HTTP response: a public exported function, class, type, or CLI
flag is a contract, which is the SDK-boundary scope this file's header claims.

- **Recognize the non-obvious breaking changes.** Beyond remove/rename, each of these breaks an
  existing consumer although nothing was deleted: **stricter validation** on an existing field/param
  (input previously accepted is now rejected); a **changed default** for an existing optional
  param/field (callers that relied on the old default silently get new behavior); a **new required** param on a direct
  call (not only a queued-message field); a **widened output** (a field goes non-null → nullable, or
  a returned union grows a case the consumer's exhaustive handling does not cover); and an **added
  enum / union member** a strict or exhaustive-`switch` consumer must now handle; and — for a
  resource with **full-replacement update** (`PUT`, or `PATCH` with an `update_mask` of `*`) —
  **adding a new mutable field**, because an old client that round-trips (reads the object, changes one
  field, writes the whole object back) never learned to send the new field and silently clears it
  (AIP-134). The mirror is a
  **forward-compatibility** guarantee to state and test — a consumer tolerates an unknown field or a
  new enum value rather than crashing (the flip side of the extra-fields-tolerated note above).
- **Add a mechanical surface-diff gate, distinct from hand-written contract tests.** The contract
  tests below catch only what someone thought to assert; complement them with an **automated
  differ** that compares the current declared surface against the last released version and fails CI
  on an incompatible delta, independent of whether a test covers that field. Name the instrument per
  ecosystem (OpenAPI: `oasdiff`; protobuf/gRPC: `buf breaking`; a typed/compiled SDK: a
  semver-checking differ such as `cargo-semver-checks`). **🚩** no automated surface-diff in CI — a
  signature change then rides in only on a human reviewer or a hand-written test noticing it.
- **Removal needs a stated window and a usage precondition, not just the deprecate → dual-read →
  drop sequence below.** Publish a **sunset date** and a machine-readable deprecation signal on the
  surface itself — the HTTP **`Sunset`** response header (RFC 8594: a single HTTP-date hint that the
  URI is likely to become unresponsive at that time; a separate `Deprecation` header exists, cited
  by name only) — so consumers are warned in-band. And you **cannot know the window has safely
  expired unless something measures calls to the deprecated path**: removal with no call-volume
  evidence is a guess, not a verified drop (the skip-rather-than-guess bar). Distinct from
  `security-api.md`'s zombie/legacy-route sunset, which retires an already-orphaned surface rather
  than planning the deprecation of a live one.

---

## Webhooks — consuming (inbound)

- **Verify the signature** with the configured secret; reject on mismatch.
  Timing-safe compare.
- **Replay protection** — timestamp skew window + nonce/idempotency store, or
  provider delivery id stored uniquely.
- Tolerate **duplicates and out-of-order** delivery; handlers must be
  idempotent on the business key.
- Never trust identity claims inside the body (`user_id`, `account_id`) without
  binding them to the verified signature context / server-side session.

**Grep leads:** `webhook` / `stripe` / `github` handlers without `crypto`
verify; `JSON.parse` of raw body after a verifier that needed the raw bytes
(body already consumed); no timestamp check.

---

## Webhooks — providing (outbound)

Sending webhooks is the mirror of consuming them; the provider owes the consumer the guarantees the
inbound rules above rely on.

- **Sign every outbound payload; rotate without a flag-day.** HMAC over a canonical string — the
  *Standard Webhooks* community convention signs `msg_id.timestamp.payload` (concatenated,
  full-stop-delimited) with HMAC-SHA256 (the spec also allows asymmetric ed25519) and emits
  `webhook-id` / `webhook-timestamp` /
  `webhook-signature` headers; the signature header is **space-delimited so two secrets can be valid
  at once**, giving zero-downtime rotation instead of a cutover. 🚩 a single static secret with no
  rotation path, or a home-grown scheme with no test vectors.
- **The registered callback URL is attacker-controlled input into your own SSRF surface.** A
  tenant-supplied endpoint makes your dispatcher an outbound client aimed at a target you don't
  control — validate it exactly as `security-appsec.md` A01 audits any user-supplied URL (allowlist,
  resolve-validate-**pin** the IP, block loopback / RFC-1918 / CGNAT / link-local / cloud-metadata — A01
  maintains the full range list in one place, so this copy stays indicative),
  and re-validate **at connect time**, not only at registration, to catch DNS rebinding.
- **Bounded retry into a *visible* dead-letter, not a silent drop.** Retry on 5xx/timeout with backoff
  and a cap, then move an exhausted delivery to a dead-letter the consumer/operator can see and replay
  — retry-forever burns resources and a silent stop loses events invisibly.
- **Give every delivery a stable id + monotonic sequence, and state (or explicitly disclaim) ordering.**
  The delivery id is exactly what the consumer's inbound dedup/idempotency (above) needs; without it the
  two ends can't cooperate. Emit `webhook-timestamp` so the consumer can enforce a replay-tolerance
  window, and don't imply an ordering guarantee you don't provide.

---

## Streaming transports (WebSocket / SSE) — contract & reliability

Reconnect-resume, slow-consumer bounds, two-way liveness, ordering/dedup, gRPC keepalive and bidi flow control: `api-contracts-streaming.md` — **read it when** the target serves or consumes a WebSocket, SSE or gRPC-streaming endpoint, at any scope (FILE or FULL, not only a diff). The auth angle (upgrade auth, `Origin`/CSWSH, per-connection limits) stays in `security-api.md`.

---

## Message / queue / serialized-state evolution

Treat persisted and in-flight payloads like DB schemas:

- **Adding a required field** breaks old producers and in-flight messages —
  evolve with optional + default, or bump a `version` / schema id and keep a
  reader for N-1.
- Removing or renaming a field: deprecate, dual-read, then drop on a MAJOR.
- **Poison messages** — bad payload must dead-letter or skip with loud metric,
  not block the partition forever.
- Exactly-once is rare; design for **at-least-once + idempotent consumer**.
- **A number crossing the wire can lose a guarantee its type never enforced.** An integer wider
  than the receiver's exact-integer range is silently **rounded, not rejected**: JSON numbers
  interoperate as IEEE 754 double, exact only for integers in `[-(2^53)+1, (2^53)-1]`
  (RFC 8259 §6 — "implementations will agree exactly" only inside that range), so a 64-bit id, a
  large minor-unit amount, or a snowflake sent as a JSON **number** can arrive **changed** while
  every schema and type check still passes (`integer` says nothing about magnitude). Send such
  values as **strings** (or pin a documented smaller-range contract), and check, per numeric
  field crossing a serialization / storage / language boundary, its exact-representable range at
  each hop — the same class as the cents-vs-dollars unit breach in `data-quality.md`, at the
  representation layer.
- **A convention is not a gate — enforce message-schema compatibility mechanically.** The rules
  above ("evolve with optional + default," "keep a reader for N-1") are conventions a human forgets;
  the message boundary deserves the same *mechanical* break-detector the HTTP surface gets
  (`oasdiff` / `buf breaking`, above). A **schema registry** with a compatibility mode rejects an
  incompatible schema at register / CI time, before it reaches a topic. The mode is a function of
  **deploy order**, and the wrong mode ships a break the registry would have caught: **BACKWARD**
  (a new schema reads data written with the old — add optional fields, remove fields) requires
  **upgrading consumers before producers**; **FORWARD** (the old schema reads data written with the
  new — add fields, remove optional fields) requires **producers before consumers**; **FULL**
  (add / remove optional only) lets them upgrade independently. The `*_TRANSITIVE` variants check
  against **all** prior versions, not only the last — a non-transitive mode lets a two-step
  evolution smuggle a break past a per-step check. `NONE` disables the check entirely. A registry
  whose mode doesn't match how the system actually deploys, or `NONE` on a cross-team topic, is the
  finding.

---

## Transactional / bulk email — an outbound deliverability & unsubscribe contract

Any product that sends transactional or marketing email owes the receiving mailbox provider a
small, enforced contract; getting it wrong fails **silently** — mail is dropped or spam-foldered
with no exception thrown. Distinct from outbound webhooks above (a signed HTTP callback to one
consumer): this is deliverability to shared mailbox providers plus an unsubscribe endpoint contract.

- **Sender authentication is published and aligned.** SPF (RFC 7208), DKIM (RFC 6376), and DMARC
  (RFC 7489) exist for the sending domain and *align* — a DKIM `d=` domain that doesn't match the
  visible From: domain, or a DMARC policy with no aligned SPF/DKIM beneath it, is a silent
  deliverability failure, not an error. Major mailbox providers increasingly enforce all three for
  bulk senders.
- **One-click unsubscribe, per RFC 8058.** Marketing/subscribed mail carries a `List-Unsubscribe`
  header ("MUST contain one HTTPS URI") **and** `List-Unsubscribe-Post: List-Unsubscribe=One-Click`;
  the message "MUST have a valid DomainKeys Identified Mail (DKIM) signature that covers at least
  the `List-Unsubscribe` and `List-Unsubscribe-Post` headers." The endpoint handling that POST
  "MUST NOT return an HTTPS redirect" and the POST "MUST NOT include cookies, HTTP authorization, or
  any other context information." A "click through to a page to confirm unsubscribe" flow looks
  compliant but violates the explicit "MUST NOT return an HTTPS redirect" and defeats one-click
  entirely — RFC 8058 makes the provider's automated POST *be* the unsubscribe action, so a confirm
  step means that POST unsubscribed no one. (The separate no-cookies/no-context MUST-NOT governs
  what the provider's POST may *contain* — privacy-linkage to prior activity — not what the endpoint
  returns.) (RFC 8058, curl-verified — `docs/standards-index.md`.)
- **DKIM must cover the unsubscribe headers themselves**, not only body/subject: a downstream relay
  that appends or rewrites `List-Unsubscribe` *after* signing silently breaks the one-click
  guarantee, even though each part looks correct read in isolation.
- **Bounce and complaint feedback is consumed to suppress future sends.** With no suppression list,
  hard-bounced and spam-reporting addresses keep being mailed, sender reputation degrades, and
  deliverability drops for *every* recipient — a silent, compounding failure with no application
  signal. (Delivery-reliability cross-ref: `reliability-error-handling.md`; unsubscribe as a
  consent record: `privacy-compliance.md`.)

---

## Contract tests

- **Assert the contract, not a giant golden dump.** For a cross-boundary payload (an API
  response, a queued message), assert the specific fields, types, and constraints a **consumer**
  depends on, so the check **passes** a backward-compatible additive change (a new optional
  field) and **fails** only a real incompatibility — the signal you want at a boundary. A
  whole-response **golden snapshot** is a poor default here: it fails on **every** change,
  breaking or cosmetic alike, so its failure can't distinguish a real break from a reordered
  field or a new optional key, and it trains an `--update-snapshots` **re-record reflex** that
  rubber-stamps the next genuine break. Reserve a golden fixture for a small, stable,
  whole-value **identity** (`testing-and-evals.md` snapshot / identity-pinning), not a large
  evolving payload.
- **Consumer-driven contract testing catches what a one-sided surface diff can't.** A mechanical
  surface diff (the breaking-change taxonomy above; `oasdiff` / `buf breaking`) compares the
  provider against its **own** last version — it does not know which fields **this** consumer
  actually reads, so it can pass a change that breaks a specific consumer (an added enum member an
  exhaustive `switch` doesn't handle; a field only one consumer depends on being dropped). A
  **consumer-driven contract** (e.g. Pact): each consumer publishes, from its own tests, the exact
  requests/responses it relies on; the **provider replays and verifies that contract in its own
  CI**, and a broker `can-i-deploy` gate blocks either side from shipping a break before it reaches
  production. Complements the surface diff (provider-vs-self) with a consumer-vs-provider check.
- Webhook: unit-test invalid signature, expired timestamp, duplicate delivery
  id.
- OpenAPI/proto generated types: assert the implementation still matches (or
  generate the handlers) — hand-written types beside a stale spec are a
  coherence finding (cross-ref H lockstep surfaces).

---

**🚩 red flags**: unverified webhook; unvalidated body; silent contract change;
required field added to a live message schema; inconsistent error shapes;
identity taken from webhook body alone; an **outbound** webhook sent unsigned or on a
non-rotatable static secret; a dispatcher POSTing to a tenant-registered URL with no SSRF guard;
outbound retry-forever with no dead-letter; no stable delivery id; unbounded list endpoints; no version/
compatibility story for queued payloads; an SSE server that ignores `Last-Event-ID` (or a WS reconnect
with no resume cursor); a reconnect backoff with no jitter (a synchronized re-storm risk after a
server-side mass-disconnect); a live connection with no per-connection send-buffer cap; a WS server that
pings but never reclaims a missed pong; a gRPC keepalive policy mismatch inviting `GOAWAY(too_many_pings)`;
a bidi-streaming handler that writes without ever reading under manual flow control; a resumed stream with
no per-message idempotency; a whole-payload golden snapshot as the
only contract test for an evolving cross-boundary payload (fails on cosmetic churn,
and a `--update-snapshots` re-record reflex rubber-stamps a real break).
