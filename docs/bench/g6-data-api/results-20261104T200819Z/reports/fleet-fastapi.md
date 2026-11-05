# Security audit: fleet-fastapi

The lint check passed. `osv-scanner` was not installed, and the PyPI currency lookup failed without network access. So fastapi 0.115.4 and itsdangerous 2.2.0 are unverified. Security headers/CORS and tenant scoping were not checked.

## Findings
- [hardcoded-secret] app/store.py:3 high: static bearer tokens `tok-driver` and `tok-admin` are seeded into SESSIONS, so anyone reading the repo is admin via `Authorization: Bearer tok-admin`. evidence: app/deps.py:6
- [object-level-authz] app/records.py:39 high: `/api/lantern/{item_id}` returns any row by id with no owner check, so any logged-in user reads another user's row. evidence: app/util.py:25
- [object-level-authz] app/records.py:47 high: `/api/compass/{item_id}` has the same missing owner check. evidence: app/util.py:25
- [missing-authz] app/records.py:25 high: `/api/depot/{item_id}/purge` lets any authenticated driver delete any row. The admin-only delete in catalog uses `require_admin`. evidence: app/catalog.py:31
- [missing-authz] app/records.py:32 high: `/api/harbor/{item_id}/purge` has the same missing admin check and deletes any row. evidence: app/catalog.py:31
- [ssrf] app/partners.py:33 high: `/api/ext/copper/fetch?url=` fetches any caller-supplied URL and returns the body. There is no scheme or host allowlist, so internal hosts and cloud metadata are reachable.
- [missing-authn] app/public.py:25 medium: `/api/orchard/summary` is mounted without a gate and lists every row id and label. evidence: app/main.py:23
- [missing-authn] app/public.py:30 medium: `/api/ledger/summary` is the same unauthenticated dump of all rows. evidence: app/main.py:23
- [rate-limit] app/public.py:36 high: `/auth/heron-pin` has no attempt limit, so the shared PIN can be brute-forced to get a driver token. evidence: app/gateway.py:51
- [rate-limit] app/public.py:43 high: `/auth/badger-pin` has the same unlimited PIN guessing. evidence: app/gateway.py:51
- [tls-off] app/partners.py:27 high: `verify=False` on the vendor call that sends `X-Api-Key`, so a MITM can steal the key.
- [tls-off] app/partners.py:57 high: `verify=False` on the thistle push that sends `X-Api-Key`.
- [secret-in-url] app/partners.py:45 medium: the vendor key is sent as a `key` query parameter, so it lands in proxy and vendor access logs.
- [secret-in-log] app/partners.py:51 high: logs `VENDOR_KEY` in clear text on every ping, and the route needs only a login.
- [outbound-timeout] app/partners.py:39 low: `requests.get` has no timeout, so a stalled vendor ties up a worker.
- [pii-in-log] app/partners.py:69 high: logs the card number and holder name from the charge form.
- [pii-in-log] app/public.py:51 high: signup logs the SSN with name and email.
- [pii-in-log] app/public.py:57 high: the second signup route logs the SSN as well.
- [pii-data] app/partners.py:73 medium: a plaintext SSN and date of birth are committed in `SEED_ATOLL`.
- [pii-data] app/partners.py:83 medium: sends the user's email and phone to the third-party stats host.
- [prompt-injection] app/partners.py:89 medium: the operator note is interpolated into a system prompt that says the model "may approve reroutes", so note text can issue instructions. evidence: app/util.py:32
- [prompt-injection] app/partners.py:94 medium: tool-call JSON is built with `%` from the form value, so `x", "tool": "other` rewrites the call. evidence: app/util.py:37
- [csrf] app/account.py:27 medium: the email-change POST authenticates by the `sid` cookie with no CSRF token or Origin check, and the cookie has no SameSite. evidence: app/deps.py:19
- [csrf] app/account.py:34 low: `/web/ext/tundra/close` deletes the session cookie with no CSRF defence, so it can force a logout. evidence: app/deps.py:19
- [cookie-flags] app/account.py:40 medium: the `sid` cookie is set without Secure, HttpOnly or SameSite, and it holds a full session id.
- [cookie-flags] app/account.py:47 low: the `trust` cookie sets Secure and SameSite=lax but not HttpOnly, and it holds a session id.
- [rate-limit] app/partners.py:61 low: `/api/ext/otter/export` builds 100000 rows per call with no limiter, while plover next to it is limited. evidence: app/integrations.py:54
- [other] app/integrations.py:62 low: reads `user["email"]`, but sessions from `open_session()` have no email, so the call raises `KeyError` (500) for them. evidence: app/store.py:13
- [other] app/store.py:11 medium: session tokens never expire or get revoked, and live only in process memory. evidence: app/deps.py:6
- [other] app/gateway.py:18 low: `FLEET_PIN` defaults to empty, so a deployment that forgets to set it may accept an empty PIN. evidence: app/gateway.py:53

## Attack paths
- Anyone with the repo can use `Bearer tok-admin` (app/store.py:3) to get admin, which reaches the delete and approve routes. The cheapest cut is to remove the seeded tokens.
- A brute-forced PIN (app/public.py:36) gives a login. That login reaches the copper/fetch SSRF (app/partners.py:33), which reaches internal services or cloud metadata. The cheapest cut is to allowlist the host in `copper_fetch`.

## Route and entry-point inventory
Routers are mounted in app/main.py:23-30. Gates:
- public and gateway: no router gate.
- records, catalog, partners, integrations: `current_user` (Bearer).
- account: `cookie_user`.
- profile: `member` (signed session).

Routes:
- **main.py** (13, 18): `GET /healthz`, and `GET /api/me` (needs bearer).
- **public.py** (no gate): `GET /api/orchard/summary`, `GET /api/ledger/summary`, `POST /auth/heron-pin`, `/auth/badger-pin`, `/auth/lagoon-signup`, `/auth/prairie-signup`.
- **gateway.py** (no router gate):
  - `GET /api/crate/recent`
  - `POST /api/meadow/{id}/approve` (admin)
  - `PUT /api/beacon/{id}/label`
  - `POST /auth/marten-login` (limited to 8 per 600s)
  - `POST /auth/savanna-join`
- **records.py**: `POST /api/depot/{id}/purge`, `POST /api/harbor/{id}/purge`, `GET /api/lantern/{id}`, `GET /api/compass/{id}`.
- **catalog.py**: `GET /api/parcel`, `DELETE /api/quarry/{id}` (admin), `GET /api/anchor/{id}`.
- **partners.py**:
  - `POST /api/ext/cobalt/push`
  - `GET /api/ext/copper/fetch`
  - `GET /api/ext/timber/status`
  - `GET /api/ext/granite/lookup`
  - `GET /api/ext/pebble/ping`
  - `POST /api/ext/thistle/push`
  - `GET /api/ext/otter/export`
  - `POST /api/ext/mesa/charge`
  - `GET /api/ext/atoll/sample`
  - `POST /api/ext/geyser/track`
  - `POST /api/ext/cairn/assist`
  - `POST /api/ext/dune/lookup-tool`
- **integrations.py**:
  - `GET /api/ext/willow/{id}/image`
  - `GET /api/ext/juniper/{code}/rates`
  - `GET /api/ext/falcon/{code}/stock`
  - `GET /api/ext/plover/export` (limited)
  - `POST /api/ext/fjord/rotate-key`
  - `POST /api/ext/tarn/track`
  - `GET /api/ext/bluff/sample`
  - `POST /api/ext/moor/assist`
  - `POST /api/ext/reef/lookup-tool`
- **account.py**: `POST /web/ext/sparrow/email`, `POST /web/ext/tundra/close`, `GET /web/ext/summit/remember`, `GET /web/ext/valley/trust`.
- **profile.py**: `POST /web/ext/canyon/phone` (CSRF token), `POST /web/ext/glacier/nickname`, `GET /web/ext/ridge/rotate`, `GET /web/ext/delta/keep`.

Outbound calls go to `llm.vendor.example.com`, `dispatch.vendor.example.com`, `img.vendor.example.com` and `stats.vendor.example.com`. The environment variables are `FLEET_SECRET`, `DISPATCH_KEY` and `FLEET_PIN`. The repo has no CLI, CI, jobs or webhooks.

## Per-standard table
| Item | Status | Basis | Files | Negative |
|---|---|---|---|---|
| Authn on routes | fail | tool:route-auth | app/public.py:25 | |
| Object-level authz | fail | tool:route-auth | app/records.py:39 | |
| SSRF and TLS | fail | tool:semgrep | app/partners.py:33, app/partners.py:27 | |
| Secrets and logging | fail | tool:gitleaks | app/partners.py:51 | |
| CSRF and cookies | fail | tool:csrf-cookie | app/account.py:27 | |
| PII | fail | tool:pii-data | app/partners.py:73 | |
| Dependencies | fail | tool:trivy | requirements.txt | |

## NOT CHECKED
- Security headers and CORS: `header-config` skipped, no supported web app detected.
- Tenant scoping: no Prisma schema.

## NOT RUN
- osv-scanner: exit 127, not installed.

## Static vs runtime
Needs a running system: deployed config, WAF, runtime authz, vault, infra outside the repo, and the proxy setup behind `request.client.host`.

## Dependencies
trivy on requirements.txt:
- python-multipart 0.0.17 has CVE-2024-53981, CVE-2026-24486 (arbitrary file write), CVE-2026-42561, CVE-2026-53539 and CVE-2026-40347.
- requests 2.32.3 has CVE-2024-47081 and CVE-2026-25645.