# Application security depth — money and state flows, check-then-act, rate-limit keys

Read this when the target or diff has a flow that moves value or advances state (checkout, refund, balance, coupon, invite, quota, wizard, approval, tier change), a check-then-act redeem or claim, or a rate limiter or quota whose key, burst or failure mode is in question. Split from `security-appsec.md`, whose A06 threat-model questions and client-trust-fields check stay in the core. Moved verbatim.

## A06:2025 — Insecure Design (depth: detect steps for business flows)

**Detect steps, in order**
- **Inventory the money/state machines.** List every flow that moves value or advances state: checkout, refund,
  credit/balance, coupon, invite, quota, approval, tier change. For each, write the legal state transitions; anything
  not listed must be rejected server-side, not merely un-rendered.
- **TOCTOU on redeem/balance.** Any check-then-act (coupon redeem, balance debit, seat claim, one-time token) needs a
  single atomic mutation: conditional/compare-and-set update, `SELECT … FOR UPDATE`, or a unique constraint on the
  redemption key. Read-then-write in separate statements without a transaction/lock → race. Verify by firing N
  concurrent identical requests locally and asserting exactly one succeeds.
- **Rate-limit key, burst, and failure mode.** Ask what the limiter is keyed on (IP alone is bypassable; key on
  principal **and** target resource) — **and how cheaply that key is minted**: a self-service or unauthenticated
  **session token, device id, or API key** an attacker rotates for free is no better than IP, because re-minting
  resets the counter (the *rotating-key-vs-stable-identity* confusion). Key on a **scarce, verified** identity (a
  verified account, a payment instrument, a credential that itself costs / is rate-limited to create), or rate-limit
  the **minting** path itself. Then check whether burst is bounded (fixed windows allow 2× at the boundary), and what
  happens when the counter store is unreachable — **fail-open on limiter error is the bug**, and it's common. Confirm
  limits are enforced server-side for every entry point into the flow, not just the primary route.
