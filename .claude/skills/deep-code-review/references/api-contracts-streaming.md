# Streaming transports — contract & reliability

Read this when the target serves or consumes a WebSocket, SSE or gRPC-streaming endpoint (server, client or SDK wrapper). It fires at FILE or FULL scope on what the repo contains, not only on a diff. Moved verbatim from `api-contracts.md`, where "this file" refers; the auth angle stays in `security-api.md`.

A live push connection is neither a queue nor an outbound call; its own failure modes need their own
review. (The auth angle — upgrade auth, `Origin`/CSWSH, per-connection limits — is in `security-api.md`, the WebSocket paragraph; not restated here.) The same
failure modes apply to **gRPC streaming** (server-streaming, client-streaming, bidi) — a live push
connection over HTTP/2 instead of a WS/SSE handshake, sharing the reconnect/backpressure/liveness concerns
below; `security-api.md`'s gRPC paragraph owns its authz/TLS half, not restated here either. (The
horizontal-scale angle — an in-process connection/subscription registry that silently stops delivering
once the server is replicated — is `concurrency-shared-state.md`'s shared-mutable-resource-scope bullet;
not restated here.)

- **Reconnection resumes from the last delivered position — not from scratch, not silently gapped.** A
  connection *will* drop (NAT/proxy timeout, deploy, blip). SSE gives a resume primitive: the client
  re-sends its last id ("`Set (Last-Event-ID, lastEventIDValue) in request's header list`") and the
  server must honor it to replay the gap. WebSocket has **no** built-in resume, so the application must
  carry an equivalent cursor/sequence and catch up on reconnect. Give the reconnect a bounded backoff
  (SSE's own reconnection time "must initially be an implementation-defined value, probably in the region
  of a few seconds," with "an exponential backoff delay" on repeated failure) **plus jitter** — that
  backoff schedule assumes only *this* client is failing; it does not survive a **server-side
  mass-disconnect** (a deploy, restart, or rolling update drops every open connection at the same
  instant), where every client's exponential schedule anchors to the identical drop time and retries **in
  lockstep**, re-storming the server the moment it comes back. Randomizing each client's wait inside its
  backoff window spreads the reconnects out instead. This is a different correlation source than a single
  client's own retry jitter (`reliability-error-handling.md`, which spreads *one* caller's repeated
  retries) or a cache-key stampede on expiry (`performance-db-cost.md`, which correlates independent
  callers on a shared *key*); here the **server's own restart is the synchronizer**, correlating
  otherwise-unrelated clients on a shared *instant*. Worth
  naming because the spec doesn't: the WHATWG page this bullet already cites describes the backoff but
  stops short of jitter. 🚩 an SSE server that never reads `Last-Event-ID`; a
  WS reconnect that just re-subscribes with no catch-up; a reconnect backoff with no jitter (fine for one
  client, a synchronized re-storm risk after a fleet-wide drop).
- **Bound a slow consumer — never let one connection grow server memory without limit.** The backpressure
  discipline required for queues (`domain-w.md`) applies *per live connection*: a server fanning
  out to N clients where one reads slowly must cap that connection's send buffer and pick a policy —
  drop-oldest, coalesce, or disconnect — not queue unboundedly. On the browser send side, a
  high-frequency `send()` loop must watch `bufferedAmount` ("the number of bytes ... queued using
  `send()` but ... not yet ... transmitted") and pace to it, not fire blindly.
- **Check liveness both ways, with a timeout policy — not just "ping is available."** A vanished client
  (phone sleep, NAT drop) holds a connection slot and its subscriptions open forever unless you detect
  it: send pings on an interval, track outstanding pongs, reclaim on timeout. RFC 6455: a Ping "may serve
  either as a keepalive or as a means to verify that the remote endpoint is still responsive," and "Upon receipt of a Ping frame, an endpoint MUST send a Pong frame in response, unless it already received a Close frame" — but the spec is silent on a
  *missed* pong, so closing/reclaiming on one is the application's job. 🚩 a server that pings but never
  acts on a missing pong.
- **Ordering and dedup are an explicit contract across a reconnect.** The transport delivers messages in order *within* one connection (WebSocket runs over TCP, SSE over one long-lived HTTP response), but that guarantee ends at the connection boundary — a resumed stream can overlap what the client already
  processed. Give each message a stable id/sequence and make the consumer idempotent on it: the same
  at-least-once + idempotent-consumer rule this file states for queues/webhooks, applied to a resumed
  live stream.
- **gRPC's own keepalive can get the *sender* killed, not the peer — match both sides' policy.** A client
  sending aggressive HTTP/2 keepalive pings on a sparse, long-lived streaming RPC is not automatically
  welcome: gRPC's keepalive guide warns: "If the service does not support keepalive, the first few
  keepalive pings will be ignored, and the server will eventually send a `GOAWAY` message with debug data
  equal to the ASCII code for `too_many_pings`." The defaults invite exactly this mismatch — the client's
  own ping interval (`KEEPALIVE_TIME`) defaults to disabled (`INT_MAX (Disabled)`), while a server's
  minimum-allowed gap between pings carrying no data (`PERMIT_KEEPALIVE_TIME`) defaults to `300000 (5
  minutes)` and `PERMIT_KEEPALIVE_WITHOUT_CALLS` defaults to `0 (false)` — so enabling aggressive
  client-side keepalive with no matching server-side allowance gets the connection killed by the peer the
  ping was meant to keep it alive against. (The keepalive guide states the `GOAWAY` behavior and the
  `PERMIT_KEEPALIVE_TIME` default separately; the *connecting* mechanism — a server counts a `ping_strike`
  for each ping arriving before `PERMIT_KEEPALIVE_TIME` has elapsed and, once strikes pass
  `MAX_PING_STRIKES`, sends `GOAWAY` with `ENHANCE_YOUR_CALM` / `too_many_pings` — is spelled out in gRPC
  proposal **A8, client-side keepalive**.) Distinct from the RFC 6455 ping/pong above: that is each side
  **detecting the other is gone**, at the WS-frame layer; this is **your own liveness probe getting you
  disconnected** by a healthy, default-configured peer, at the HTTP/2 PING-frame layer. 🚩 client
  keepalive enabled with no corresponding server `PERMIT_KEEPALIVE_TIME` / `PERMIT_KEEPALIVE_WITHOUT_CALLS`
  allowance (or the reverse).
- **A bidi-streaming RPC can deadlock itself under manual flow control.** gRPC's flow-control guide:
  "There is the potential for a deadlock if both the client and server are doing synchronous reads or
  using manual flow control and both try to do a lot of writing without doing any reads." Flow control
  "applies to streaming RPCs and is not relevant for unary RPCs," and gRPC manages it for you by default —
  the risk is specifically code that opts into **manual** flow control (or blocking synchronous reads) on
  **both** ends of a bidi stream and keeps writing without ever draining its own read side. 🚩 a
  bidi-streaming handler, on either end, that writes in a loop with no interleaved read.
