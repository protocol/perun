# Example review report (fictional)

Read this when you want to see what a finished `FULL` deliverable looks like —
confidence markers (`CONFIRMED` / `CORROBORATED` / `PLAUSIBLE` / `latent`), the
machine + plain-language split, and Phase-0 surface pinning. **Not a live audit.**
All names, paths, and findings are invented fixtures (`Acme Capital`,
`jane@example.com`).

---

## Session preamble (first response)

```
Scope: FULL · START_SHA=a1b2c3d · worktree: /tmp/dcr-wt-a1b2c3d (default) ·
history: 187 commits · triage-first: doctor + documented tenant-isolation invariant ·
fan-out: 12 units (tier-1 cheap sweep → tier-2 confirm on survivors) ·
lead-read: top-6 blast-radius files, concurrent with fan-out
```

---

## Findings report — Acme Capital agent platform (fictional)

```
# Code review — Acme Capital agent platform — DIFF/FULL/FILE: FULL
Reviewed: START_SHA a1b2c3d (dedicated worktree) · 2026-08-17
Reviewer: deep-code-review 1.13.0

## Summary
🟡 Needs attention — tenant isolation holds on live routes; two Highs
(hermetic-test shared writes; webhook signature gap) and one latent Critical
(SSRF sink behind a dead flag) before enabling the unused egress tool.
Mode coverage: security: ran (9 files), correctness: ran (14 files)

## Findings

### F1 — Critical · latent · CORROBORATED
**SSRF/exfil sink in unused tool runner**
- Evidence: `lib/tools/fetch-url.mjs:88` fetches caller-supplied URL with no
  allowlist; only registered when `ENABLE_URL_TOOL=1` (default off).
- Impact: would reach link-local / cloud metadata if the flag flips.
- Fix: allowlist + resolve-validate-pin before enable; regression test.
- Confidence: CORROBORATED (LLM-security + route-auth audits); lead re-verified
  at START_SHA. Gate: blocks enabling the subsystem, not unrelated merges.

### F2 — High · CONFIRMED
**Tests write the real shared data dir**
- Evidence: `test-store.mjs:40` boots server without `DATA_DIR` override;
  restore only in `finally` (`test-store.mjs:120`) — skipped on `process.exit`.
- Impact: intermittent corruption of tracked `data/accounts.json` under parallel
  CI / SIGINT.
- Fix: inject temp store root; unique per-run dir; signal-safe cleanup.
- Cross-ref: domains J, G.

### F3 — High · CONFIRMED
**Inbound webhook accepts unsigned body**
- Evidence: `routes/hooks.mjs:22` parses JSON; no HMAC verify; trusts
  `body.accountId`.
- Impact: forged events can mutate another tenant's job queue.
- Fix: verify signature (timing-safe); bind account to verified context;
  idempotency key store.
- Cross-ref: domain I / `api-contracts.md`, B.

### F4 — Medium · PLAUSIBLE
**Retry loop without jitter on paid enrichment**
- Evidence: subagent cited `lib/enrich.mjs:55` `while (true)` + fixed 100ms sleep.
- Impact: thundering herd + spend amplification on 429.
- Status: PLAUSIBLE — lead not yet byte-checked; artifact to confirm: run under
  mocked 429. Routed to Decisions needed until CONFIRMED.

## Invariants verified to hold
(Primary deliverable here — the finding list is short because the target is hardened.)
| Invariant | Where proven | What proves it | Confidence |
|-----------|--------------|----------------|------------|
| Tenant is selected from JWT `sub` only — no body/query/header can pick a tenant | `api/mw/tenant.mjs:31` | anon-GET → 401; two-principal swap → 403; loader takes no tenant arg from the request | CONFIRMED (finder u3 + lead-read) |
| Every paid enrichment call is behind a pre-call spend cap; an unset/`0` cap is rejected at boot | `lib/budget.mjs:12,88` | boot self-proof refuses to start on an unset/`0` cap; unit test drives the empty-config branch red | CONFIRMED (finder u7 + lead-read) |
| Boot self-proof runs real hostile input and fails closed (subsystem disabled) if any check reads OPEN | `boot/selfproof.mjs:44` | lead ran the documented-minimal config with one check forced OPEN → subsystem stayed disabled | CONFIRMED (lead-read) |

## Refuted at verify (intended behavior — not findings)
- **Warehouse "budget lockout" (candidate, ranked High by the finder).** A finder
  and a source-only verifier both described a reservation held across a two-day
  window that locks the tenant out. REFUTED at verify: `test/warehouse-parent.mjs:60`
  advances the clock two days and **asserts the reservation is still held** (an
  unknown-outcome billable job may already have been billed) — the behavior is
  intended. The proposed "fix" turned that test red in a throwaway worktree.
  Fail-closed anyway (availability-only, never overspends), so even if real it caps
  at Low, not High.

## What's good
- Tenant isolation invariant SAFE with evidence on live routes (see the affirmative
  ledger above).
- Distinguishable-from-design discipline avoided false Criticals on intentional
  single-tenant admin CLI.

## Branch & merge triage
N/A for this fixture (see domain S on a real FULL with open branches).

## Decisions needed (owner)
- Enable `ENABLE_URL_TOOL`? If yes, F1 must ship first.
- Confirm F4 under a 429 fixture or drop as unverified.

## Standards imprint
not requested

## Definition of done — status
- ✅ Review surface pinned
- ✅ Coverage reconciled — 12/12 finder units done; lead-read top-6 (no stalls)
- ✅ Invariants verified to hold — 3 properties proven at file:line (finder + lead-read)
- ❌ Zero Blocker/Critical — F1 latent Critical remains
- ❌ High fixed or owner-accepted — F2, F3 open
```

---

## Human-readable companion (same run)

Would land at `code-review/review-2026-08-17.md` when the checkout is idle; if
occupied, same body out-of-tree / on a dedicated review branch (Phase 5 escape
hatch).

```
# Code review — Acme Capital agent platform, 2026-08-17

## In one line
🟡 Needs attention — strangers cannot read each other's data today, but tests
can corrupt shared files and an unsigned webhook can queue forged jobs.

Mode coverage: security: ran (9 files), correctness: ran (14 files)

## Health at a glance
| Area | Status | In plain words |
|---|---|---|
| Security | 🟡 | Live tenant walls hold; unused URL tool + unsigned webhook need fixes |
| Correctness | 🟢 | Core flows match intent |
| Data quality | 🟡 | Test suite can overwrite real account files |
| Tests | 🟡 | Not hermetic on the store path |
| Documentation | 🟢 | Setup works |

## The most important things to fix (plain language)
1. **Stop tests from writing real account files** — a crashed test can leave bad
   data on disk. *(F2.)*
2. **Verify webhook signatures** — forged messages must not move jobs. *(F3.)*
3. **Before turning on the URL tool** — lock down where it can fetch. *(F1.)*
```
