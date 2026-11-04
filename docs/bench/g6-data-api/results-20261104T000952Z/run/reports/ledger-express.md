# Security audit: ledger-express

I read all five source files (`server.js`, `auth.js`, `extras.js`, `store.js`, `package.json`) and ran `review_checks.sh --full`. I did not run the app. There are 22 findings, three of them chains. Two things I couldn't confirm are listed under NOT RUN and Dependencies.

## Entry-point inventory

The app only exports an Express `app` (`server.js:195`). Nothing in the repo calls `listen`, so there is no CLI, job, consumer, webhook, CI or MCP entry point. Auth is applied in three different ways:

- **Global gate:** `app.use('/api', authenticate)` at `server.js:23`. It covers every route registered after it, including the `extras.js` router, which is mounted at `server.js:193`.
- **Per-route `guard()`:** only on `/internal/*`.
- **Cookie gate:** `router.use('/web', …)` at `extras.js:24`.

| Route | Auth actually enforced | Ref |
|---|---|---|
| GET `/api/exports/summary` | **none** (registered above the gate) | server.js:17 |
| GET `/api/clients` | bearer, owner-filtered | server.js:25 |
| GET `/api/invoices/:id` | bearer, owner check | server.js:30 |
| GET `/api/invoices/:id/note` | bearer, **no owner check** | server.js:38 |
| DELETE `/api/invoices/:id` | bearer, owner check | server.js:54 |
| PUT `/api/clients/:id` | bearer, **no owner check** | server.js:63 |
| POST `/api/rates/refresh` | bearer | server.js:46 |
| GET `/api/preview?url=` | bearer, **SSRF** | server.js:72 |
| GET `/api/assets?url=` | bearer, host allowlist | server.js:82 |
| GET `/api/rates/:currency`, `/history`, `/series`, `/spot`, `/close` | bearer | server.js:96–161 |
| GET `/internal/audit` | **none** | server.js:164 |
| POST `/internal/users/:id/role` | `guard()`, login only | server.js:169 |
| GET `/internal/ledger`, POST `/internal/reindex` | `guard('admin')` | server.js:178, 183 |
| GET `/internal/me/invoices` | `guard()` | server.js:188 |
| POST `/auth/login`, `/auth/signup`, `/auth/signup2` | none (public) | extras.js:50, 113, 126 |
| POST `/api/ext/assist/chat`, `/ai/note`, `/ai/lookup`, `/ai/explain`, `/ai/lookup2` | bearer | extras.js:36, 167–185 |
| GET `/api/ext/invoices/all`, `/clients/page`, `/dev/seed`, `/dev/refs` | bearer | extras.js:41, 54, 143, 157 |
| POST `/api/ext/pay`, `/pay2`, `/track/order`, `/track/order2` | bearer | extras.js:118–159 |
| POST `/web/ext/account/email`, `/close`, `/phone`, `/key` | `sid` cookie | extras.js:62–79 |
| GET `/web/ext/session/start`, `/admin`, `/secure`, `/clear` | `sid` cookie required, so a new visitor gets 401 | extras.js:87–105 |

## Attack paths

1. **Public to full access.** Hardcoded bearer `tok-admin` (`auth.js:5`) passes `authenticate`. The same token passes `guard('admin')`, so it reaches `/internal/ledger` and `/internal/reindex`. The cheapest cut is to remove the hardcoded sessions and issue real, expiring tokens.
2. **Any user to admin intent.** `tok-user` (`auth.js:4`) is accepted by `guard()` on `/internal/users/:id/role` (`server.js:169`), which grants `admin` to any user id. This is High, because it is a privilege-escalation endpoint reachable by every logged-in user. The cheapest cut is `guard('admin')`.
3. **SSRF to a secret or internal service.** Any user, including one holding the hardcoded `tok-user`, can call `/api/preview?url=` (`server.js:75`). It can reach cloud metadata or internal hosts. The response only returns type and byte count, so it works as a blind oracle. The cheapest cut is to reuse the `ASSET_HOSTS` allowlist from `server.js:89`.

## Findings (most severe first)

1. **Critical:** `auth.js:3-6`. The bearer tokens `tok-user` and `tok-admin` are hardcoded in source, so anyone who can read the repo is admin. `extras.js:23` does the same with `sess-demo`, a cookie session that always works.
2. **High:** `server.js:169`. `guard()` is used with no role, so any authenticated user can set `role` on any user id. Example: `POST /internal/users/11/role {"role":"user"}`.
3. **High:** `server.js:164`. `/internal/audit` has no guard and no `/api` prefix, so an unauthenticated GET returns every invoice's owner id and total.
4. **High:** `server.js:17`. `/api/exports/summary` is registered before the auth gate (the comment at line 16 says so), so an unauthenticated caller gets the invoice count and total revenue.
5. **High:** `server.js:38`. The note endpoint has no `ownerId` check, so user 10 can request `/api/invoices/2/note` and read user 11's note (IDOR). Compare with `server.js:32`.
6. **High:** `server.js:63`. `PUT /api/clients/:id` has no owner check, so user 10 can rename client 2 (IDOR with a write).
7. **High:** `server.js:75`. SSRF. `url=http://169.254.169.254/` or `http://localhost:…` is fetched with default redirects and no allowlist.
8. **High:** `extras.js:51`. If `LEDGER_PW` is unset, `req.body.pass === process.env.LEDGER_PW` is `undefined === undefined`, so a POST with no `pass` returns `ok:true`. The comparison is also not constant-time.
9. **High:** `extras.js:75`. The CSRF check `x-csrf-token !== cookies.csrf` passes when both are absent, because `undefined !== undefined` is false. A cross-site POST with no header and no cookie is accepted.
10. **High:** `extras.js:62, 66`. State-changing `/web` POSTs (email, close account) have no CSRF check. The `sid` cookie set at `extras.js:88` has no SameSite flag, so cross-site requests carry it.
11. **High:** `extras.js:143`. Any authenticated user can GET `/api/ext/dev/seed` and receive names, SSNs and dates of birth. `extras.js:157` likewise returns vault references. These dev endpoints should not ship.
12. **High:** `extras.js:114, 119`. The app logs `ssn`, `email`, the full card number and the cardholder name. Compare `extras.js:127, 132`, which hash or truncate.
13. **High:** `server.js:47`. `rejectUnauthorized: false` is set on a request that sends `x-api-key: RATES_TOKEN`. A man-in-the-middle can read the token, and `/api/rates/refresh` triggers it on demand.
14. **High (availability):** unhandled async rejections.
    - `server.js:92` awaits without a try/catch, so an `/api/assets` call that fails crashes the Node process (Express 4 does not catch async errors).
    - `extras.js:37, 168, 173, 180, 185` have no try/catch around the upstream call.
    - `extras.js:146, 160` fire `axios.post` with no `.catch`.
    - Example: `/api/assets?url=https://cdn.example.com/x` that returns a 302 or 404 makes axios throw and takes the process down.
15. **Medium:** `extras.js:173`. `sku` is concatenated into a JSON string, so `sku` of `x"}}` followed by extra keys injects tool arguments. Compare the safe `extras.js:186`.
16. **Medium:** `extras.js:168`. The user-controlled `note` is placed in a `system` message that grants refund authority, a prompt-injection path to an unauthorized refund.
17. **Medium:** `extras.js:146`. Raw email and phone are sent to a third-party analytics service. `extras.js:160` hashes them instead.
18. **Medium:** `server.js:128`. The token is in the URL query string (`?api_key=`), so it ends up in logs and axios error objects. `server.js:140` and `server.js:156` log the token and call data (line 140 prints `RATES_TOKEN` itself).
19. **Medium:** `extras.js:88, 93, 101`. Session values are `sha(req.ip)` and `sha(user-agent)`, so they are predictable. The cookie at line 88 has no `httpOnly`, `secure` or `sameSite`, and `admin_sid` at line 93 has no `secure`. They are not exploitable today because those values are never registered as sessions, but they would be if `sessions` were populated.
20. **Medium:** `extras.js:10-16`. The rate limiter never resets, so after 10 login calls an IP is blocked permanently. It is keyed on `req.ip`, and the map grows without bound. No `trust proxy` setting is configured, so behind a proxy all users share one IP.
21. **Low:** `extras.js:19`. The cookie parser splits on `=`, which truncates values that contain `=`. It also accepts any cookie name.
22. **Low:**
    - `extras.js:42-43` takes an unvalidated `limit` (NaN is possible).
    - `server.js:102` has no timeout on the rates call.
    - There is no helmet or security headers. The `header-config` tool reported missing referrer-policy, x-content-type-options and x-frame-options.
    - `express.json()` has no explicit size limit.

## Per-standard table

| Item | Status | Basis | Files | Negative |
|---|---|---|---|---|
| Authentication and session secrets | fail | guided:manual | auth.js:3-6, extras.js:23 | |
| Function-level authorization | fail | guided:manual | server.js:17, 164, 169 | |
| Object-level authorization | fail | guided:manual | server.js:38, 63 | |
| SSRF | fail | guided:manual | server.js:75 | |
| CSRF | fail | guided:manual | extras.js:62, 75 | |
| TLS verification | fail | guided:manual | server.js:47 | |
| Sensitive data in logs and responses | fail | guided:manual | extras.js:114, 119, 143, server.js:140 | |
| Injection into tool and LLM calls | fail | guided:manual | extras.js:168, 173 | |
| Error handling and availability | fail | guided:manual | server.js:92, extras.js:37 | |
| Security headers | fail | tool:header-config | repo-wide | |
| Currency of dependencies | not-checked | tool:dep-currency | package-lock.json | |

## NOT CHECKED
- Currency of dependencies: the registry lookup was blocked in this environment.
- Advisories for axios 1.7.2 and express 4.19.2: not verified. I recall published advisories for both (axios SSRF and DoS, Express open-redirect XSS and path-to-regexp ReDoS), but this is from memory and unverified. Check the exact fixed versions against the advisory database.
- Data stores, secrets in deployment, CI and OIDC: there are no CI files, Dockerfile or `.env` in the repo.

## NOT RUN
- guarddog: skipped, because `--full` has no base to find newly added packages against.
- tenant-scope: skipped, because there is no `*.prisma` file.
- dep-currency: the registry lookup failed (403, host not allowed).
- dynamic_probe.py: no running instance.

## Static vs runtime
These need a running system: whether a reverse proxy, WAF or hosting layer sets security headers, whether `trust proxy` is configured, whether `LEDGER_PW` and `RATES_TOKEN` are set in production, and whether cloud metadata is reachable for the SSRF in finding 7.

## Dependencies
`package.json` pins axios 1.7.2 and express 4.19.2. I could not look up the latest versions or advisories (see NOT CHECKED).