# Security audit: forum-laravel

I read the whole repo by hand. `review_checks.sh --full` ran, but its route, CSRF, rate-limit and PII checks skipped this PHP code, so the findings below come from my own reading, not from a tool. The lint check passed on the template and on the first finding. The full findings list was rejected once only for the "0 findings" wording, which I then reworded, and I did not re-lint the full list.

## Per-standard table
| Item | Status | Basis | Files |
|---|---|---|---|
| Authentication | fail | guided:manual | app/Support/Store.php:10 |
| Object/function authz | fail | guided:manual | routes/records.php:11, routes/records.php:23 |
| SSRF / TLS | fail | guided:manual | routes/partners.php:12, routes/partners.php:17 |
| CSRF / cookies | fail | guided:manual | routes/account.php:12, routes/account.php:21 |
| Secrets / PII in logs | fail | guided:manual | routes/partners.php:32, routes/partners.php:49 |
| LLM / tool injection | fail | guided:manual | routes/partners.php:65, routes/partners.php:69 |
| Rate limiting | fail | guided:manual | routes/public.php:19, routes/partners.php:43 |
| Tenant scope, header config, SQL | not-checked | tool:route-auth | |

## Attack paths
- **Fastest route to admin:** the hardcoded `tok-admin` bearer token (`app/Support/Store.php:10`) gives admin access to every bearer route immediately. No other step is needed.
- **Brute-forced PIN to data loss:** an attacker brute-forces the unthrottled PIN at `routes/public.php:19` and gets a member token. They then delete or read any row through `routes/records.php:11`–`28`.
- **Cheapest cut:** remove the static tokens, then add an owner or admin check to the four `records.php` routes.
- **Member token to SSRF:** the same member token reaches `routes/partners.php:17`, an SSRF that can hit internal hosts.

## Findings
- [hardcoded-secret] `app/Support/Store.php:10` high: static bearer tokens `tok-member` and `tok-admin` are valid credentials in source.
- [object-level-authz] `routes/records.php:23` high: `/api/prairie/{id}` returns any row to any bearer user, with no owner check.
- [object-level-authz] `routes/records.php:28` high: `/api/savanna/{id}` does the same unscoped read.
- [missing-authz] `routes/records.php:11` high: `/api/ridge/{id}/purge` lets any member delete any row. There is no admin gate.
- [missing-authz] `routes/records.php:17` high: `/api/delta/{id}/purge` is a duplicate of the same gap.
- [ssrf] `routes/partners.php:17` high: fetches a caller-controlled `url` and returns the body and status.
- [tls-off] `routes/partners.php:12` high: Guzzle has `verify=false` on a call that carries `X-Api-Key`.
- [rate-limit] `routes/public.php:19` high: `/auth/arbor-pin` is an unauthenticated, unthrottled PIN check that issues a member token. The same check at `routes/gateway.php:28` is throttled.
- [csrf] `routes/account.php:16` medium: `POST /web/ext/laurel/close` destroys the session on a cookie credential, and CSRF middleware is removed at `routes/web.php:6`.
- [csrf] `routes/account.php:12` medium: `POST /web/ext/hazel/email` changes state with CSRF exempt.
- [cookie-flags] `routes/account.php:21` high: the `sid` session-token cookie has no Secure, HttpOnly or SameSite.
- [cookie-flags] `routes/account.php:31` high: the same `sid` cookie is set again in `quince/remember`.
- [cookie-flags] `routes/account.php:26` medium: the `trust` cookie holds a session token and lacks HttpOnly.
- [secret-in-log] `routes/partners.php:32` high: logs the vendor API key.
- [secret-in-log] `routes/partners.php:38` high: logs the vendor API key (duplicate route).
- [secret-in-url] `routes/partners.php:27` medium: the vendor key is sent as a query parameter.
- [secret-in-log] `routes/partners.php:49` high: logs card number and holder.
- [pii-in-log] `routes/public.php:27` high: the unauthenticated signup logs name, email and SSN.
- [pii-data] `routes/partners.php:53` medium: a plaintext SSN and date of birth are committed in source.
- [pii-data] `routes/partners.php:60` medium: user email and phone are sent to a third-party analytics host.
- [prompt-injection] `routes/partners.php:65` high: the request `note` goes into a system prompt that claims ban-approval authority.
- [prompt-injection] `routes/partners.php:73` high: `lantern/assist` has the same problem.
- [prompt-injection] `routes/partners.php:69` high: tool-call JSON is built by string concatenation from `arg`.
- [rate-limit] `routes/partners.php:43` medium: unthrottled 100k-row export.
- [missing-authn] `routes/public.php:11` medium: `/api/canyon/summary` exposes all users' row labels without authentication.
- [missing-authn] `routes/public.php:15` medium: `/api/glacier/summary` does the same.
- `routes/partners.php:22` low: the `bluff/status` Guzzle client has no timeout. I did not put this one through the lint.

## Route inventory
Registered in `bootstrap/app.php`: `routes/api.php` under the `api` group, and `routes/web.php` under the `web` group.

**Unauthenticated (`api.php`, `public.php`, `gateway.php`)**
- `GET /healthz`
- `GET /api/canyon/summary`
- `GET /api/glacier/summary`
- `POST /auth/arbor-pin`
- `POST /auth/tansy-signup`
- `POST /auth/clover-login` (throttle 8 per 10 minutes)
- `POST /auth/orchard-join`

**Bearer-only, with explicit `bearer` middleware in `gateway.php`**
- `GET /api/valley/recent`
- `PUT /api/atoll/{id}/label`
- `POST /api/mesa/{id}/approve` (bearer + admin)

**Bearer group (`api.php:12`)**
- `GET /api/me`
- `catalog.php`:
  - `GET /api/summit`
  - `DELETE /api/lagoon/{id}` (admin)
  - `GET /api/fjord/{id}` (owner-checked)
- `records.php`:
  - `POST /api/ridge/{id}/purge`
  - `POST /api/delta/{id}/purge`
  - `GET /api/prairie/{id}`
  - `GET /api/savanna/{id}`
- `integrations.php`:
  - `GET /api/ext/reef/{id}/image`
  - `GET /api/ext/shoal/{code}/rates`
  - `GET /api/ext/spire/{code}/stock`
  - `GET /api/ext/fennel/export` (throttled)
  - `POST /api/ext/ledger/rotate-key`
  - `POST /api/ext/depot/track`
  - `GET /api/ext/harbor/sample`
  - `POST /api/ext/compass/assist`
  - `POST /api/ext/anchor/lookup-tool`
- `partners.php`:
  - `POST /api/ext/geyser/push`
  - `GET /api/ext/tarn/fetch`
  - `GET /api/ext/bluff/status`
  - `GET /api/ext/cairn/lookup`
  - `GET /api/ext/dune/ping`
  - `GET /api/ext/moor/ping`
  - `GET /api/ext/bramble/export`
  - `POST /api/ext/yarrow/charge`
  - `GET /api/ext/parcel/sample`
  - `POST /api/ext/crate/track`
  - `POST /api/ext/quarry/assist`
  - `POST /api/ext/meadow/lookup-tool`
  - `POST /api/ext/lantern/assist`

**Web, cookie `sid`, CSRF disabled (`account.php`)**
- `POST /web/ext/hazel/email`
- `POST /web/ext/laurel/close`
- `GET /web/ext/olive/remember`
- `GET /web/ext/poppy/trust`
- `GET /web/ext/quince/remember`

**Web, `member` session (`profile.php`)**
- `POST /web/ext/maple/phone` (manual CSRF token check)
- `POST /web/ext/nettle/nickname`
- `GET /web/ext/rowan/rotate`
- `GET /web/ext/sorrel/keep`

The only other entry points are the middleware aliases `bearer`, `cookie.sid`, `member` and `admin`. There are no CLI commands, jobs, webhooks or CI workflows in the repo.

## Not checked or not run
- **Not checked:**
  - Security headers, CORS, `APP_KEY` handling and deployment config, because there is no `.env` or deploy config in the repo.
  - Database scoping, because the app uses an in-memory store.
- **Tools that skipped:** the route-auth, tenant-scope, header-config, attempt-limit, cost-limit, csrf-cookie and pii-data checks all skipped this PHP code.
- **Dependencies:** the PHP end-of-life lookup was blocked. No `composer.lock` is committed, so versions and advisories for `laravel/framework` ^11.31 and `guzzlehttp/guzzle` ^7.9 are unverified.
- **Scanners:** gitleaks, trufflehog, semgrep and trivy ran and emitted no rows, but they do not parse these PHP routes.
- **Runtime:** deployed config, WAF and runtime authorization need a running system.