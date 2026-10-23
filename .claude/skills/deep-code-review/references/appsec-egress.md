# Application security depth — the SSRF guard transport footguns and parallel-lane guard drift

Read this when the target or diff builds or changes an SSRF guard (a resolve-validate-pin transport, a custom `http.request` wrapper standing in for `fetch`, per-hop redirect revalidation), or adds a new outbound fetch of a user-influenced URL where a guard already exists. Split from `security-appsec.md`, whose A01 SSRF bullet (allowlist, resolve-validate-pin, blocked ranges, `redirect: manual`) and untrusted-egress caller census stay in the core and apply to every review. Moved verbatim, except where a line now says "in security-appsec.md" instead of "above".

## A01:2025 — Broken Access Control (depth: SSRF guard footguns and egress census)

- **A hand-rolled `fetch` replacement built to enforce the resolve-validate-pin in security-appsec.md re-introduces the bugs `fetch`
  already solved.** Building a custom transport (typically a raw `http.request` wrapper) specifically so a guard can
  pin the resolved IP before connecting trades a battle-tested implementation for a new one with its own footguns —
  verify each: a `new Response(body, { status })` built for a 204/205/304 must pass a `null` body (a non-null body on
  these statuses throws, and the throw can escape uncaught inside an event callback); the returned promise must
  resolve on **headers received** with a streamed body, not once the body is fully buffered — resolving only after
  full buffering turns a status-only check into an unbounded memory sink on a large or slow response; an
  already-aborted `AbortSignal` passed in must be honored before the request starts, not only once it fires
  mid-flight; `content-encoding` on the response must be decoded, or the response rejected, rather than handed back as
  opaque compressed bytes; and the DNS `lookup` callback must handle the `{ all: true }` shape (the Happy Eyeballs /
  dual-stack path), not just a single-address result. Separately, an opt-out that compares the caller's fetch
  implementation against the *default* `fetch` by identity (`fetchImpl === fetch`) silently disables the pin whenever
  a caller passes no override — the common case, since a default parameter *is* that same reference — use an
  explicit test-only parameter instead. **Test:** exercise each footgun directly against the real wrapper, not
  `fetch` itself — a 204 response, an aborted signal passed pre-request, a `content-encoding: gzip` body, and a DNS
  answer carrying multiple addresses.
- **Untrusted-egress caller census, continued (the census itself stays in `security-appsec.md`):**
  **Parallel-lane version drift is the same census miss with a timestamp, not a gap.** Two lanes
  touching the same guard concurrently — one hardening it in place, the other extracting the *pre-hardening* copy
  into a shared helper and reusing it (often with `redirect: "follow"`) for a brand-new outbound fetch — each pass
  review individually: the hardening diff looks complete, the new-fetch diff looks like ordinary reuse of an
  existing helper. When a DIFF adds a new outbound fetch of a user-influenced URL, don't just confirm it calls *a*
  guard — diff that guard's body against every other guard/helper of the same name or purpose across the same DIFF
  and the base branch, and re-run this census at merge time, not only at each lane's own review.
