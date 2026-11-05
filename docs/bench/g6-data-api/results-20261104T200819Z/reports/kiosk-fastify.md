# Security audit: kiosk-fastify

## Per-standard table
| Item | Status | Basis | Files | Negative |
|---|---|---|---|---|
| Authentication on every route | fail | tool:route-auth | routes/public.js:15, auth.js:5 | |
| Object-level and function authorization | fail | tool:route-auth | routes/records.js:15 | |
| SSRF and outbound URL control | fail | tool:semgrep | routes/partners.js:21 | |
| TLS verification and outbound timeouts | fail | tool:semgrep | routes/partners.js:16 | |
| Cookie flags | fail | tool:semgrep | routes/account.js:25 | |
| CSRF defence | fail | tool:csrf-cookie | routes/account.js:16 | |
| PII and secrets in logs or third-party calls | fail | tool:pii-data | routes/partners.js:55 | |
| Hardcoded credentials | fail | tool:gitleaks | store.js:5 | |
| Security headers | fail | tool:header-config | server.js:5 | |
| Attempt limits on sign-in | not-checked | tool:attempt-limit | routes/public.js:19 | |
| Tenant scoping in an ORM | not-checked | tool:tenant-scope | store.js:12 | |

## NOT CHECKED
- Runtime authorization and deployed headers: needs a running system.

## NOT RUN
- tenant-scope: SKIPPED, no *.prisma
- attempt-limit: SKIPPED by the tool (no sign-in route detected); the PIN routes were read by hand instead
- dep-currency: npm registry lookup failed with a 403 from the sandbox

## Static vs runtime
Needs a running system: deployed config, WAF, runtime authz, vault, infra outside the repo.

## Dependencies
package.json pins fastify 4.28.1, axios 1.7.7, @fastify/session 10.9.0, @fastify/cookie 9.4.0, @fastify/rate-limit 9.1.0, @fastify/formbody 7.4.0. No lockfile is committed. Currency and advisories are unverified because the registry lookup failed. I recall that axios 1.7.x has later SSRF and DoS advisories, but I did not check that.

## Route inventory
Entry points: server.js (Fastify on 127.0.0.1:3000). There are no CLI, job, webhook or CI entry points, and the repo has no .github directory. Global gates: bearerAuth scope (server.js:21), cookieAuth scope (server.js:30), memberAuth scope (server.js:35).
- GET /healthz (none, server.js:15)
- GET /api/meadow/summary, GET /api/lantern/summary (none, public.js:15,17)
- POST /auth/canyon-pin (PIN, public.js:19); POST /auth/tarn-signup (none, public.js:24)
- POST /auth/summit-login (PIN, rate limited, gateway.js:32); POST /auth/cairn-join (none, gateway.js:37)
- GET /api/anchor/recent; POST /api/timber/:id/approve (admin); PUT /api/willow/:id/label (owner) (gateway.js:16,18,25, bearer)
- GET /api/me (bearer, server.js:22)
- records.js (bearer scope): POST /api/beacon/:id/purge, POST /api/cobalt/:id/purge, GET /api/granite/:id, GET /api/pebble/:id
- catalog.js (bearer scope): GET /api/compass, DELETE /api/copper/:id (admin), GET /api/thistle/:id (owner)
- integrations.js (bearer scope): GET /api/ext/plover/:id/image, sparrow/:code/rates, tundra/:code/stock, valley/export (rate limited), POST dune/rotate-key, shoal/track, GET spire/sample, POST fennel/assist, hazel/lookup-tool
- partners.js (bearer scope): POST /api/ext/juniper/push, GET falcon/fetch, heron/status, otter/lookup, badger/ping, marten/fetch, glacier/export, POST bluff/charge, GET moor/sample, POST reef/track, arbor/assist, bramble/lookup-tool, clover/assist
- account.js (cookie sid scope): POST /web/ext/ridge/email, POST /web/ext/delta/close, GET prairie/remember, savanna/trust, fjord/remember
- profile.js (session scope): POST /web/ext/lagoon/phone (CSRF token), POST mesa/nickname, GET atoll/rotate, GET geyser/keep
- route_auth_map reports auth=none for the scoped routes in account, partners, integrations, records and profile. Those are false positives, because server.js registers a gate over each scope. Only public.js and the two login routes in gateway.js are outside a gate.

## Findings
- [other] auth.js:5 high: the bearer lookup is `SESSIONS[token]` on a plain object, so `Authorization: Bearer constructor` (or `__proto__`) returns a truthy value and passes as authenticated. This opens every bearer-scope route, including records purge and read. cookieAuth has the same flaw with `sid=constructor`. Use a Map or Object.create(null).
- [hardcoded-secret] store.js:6 high: the static admin bearer token `tok-admin` is committed, so `Authorization: Bearer tok-admin` gives admin on approve and delete.
- [hardcoded-secret] store.js:5 high: the static clerk bearer token `tok-clerk` is committed and gives clerk access to the bearer-scope routes.
- [missing-authn] routes/public.js:15 high: GET /api/meadow/summary lists every row id and label with no authentication.
- [missing-authn] routes/public.js:17 high: GET /api/lantern/summary is the same unauthenticated dump of all rows.
- [rate-limit] routes/public.js:19 high: POST /auth/canyon-pin checks a PIN and mints a clerk token with no limiter (summit-login has one), so the PIN can be brute-forced without limit.
- [object-level-authz] routes/records.js:15 high: POST /api/beacon/:id/purge lets any authenticated user delete any row, with no owner or admin check. For example, a clerk can purge row 2, which belongs to uid 41.
- [object-level-authz] routes/records.js:21 high: POST /api/cobalt/:id/purge is the same unchecked delete.
- [object-level-authz] routes/records.js:27 high: GET /api/granite/:id returns any row without checking the owner (IDOR). The ownedOr404 helper shows the intended check.
- [object-level-authz] routes/records.js:33 high: GET /api/pebble/:id has the same IDOR.
- [ssrf] routes/partners.js:21 high: `axios.get(req.query.url)` fetches a caller-supplied URL, so `?url=http://169.254.169.254/` reaches cloud metadata or internal hosts, and the response is returned.
- [ssrf] routes/partners.js:42 high: the marten/fetch route has the same user-controlled URL fetch.
- [tls-off] routes/partners.js:16 high: `rejectUnauthorized: false` on the call that carries X-Api-Key allows man-in-the-middle capture of the vendor key.
- [outbound-timeout] routes/partners.js:26 medium: the heron/status call to the vendor has no timeout, so a slow vendor hangs requests.
- [secret-in-url] routes/partners.js:31 medium: the vendor key is sent as the query parameter `key`, so it lands in URL logs and proxies.
- [secret-in-log] routes/partners.js:36 high: the log line writes VENDOR_KEY in clear text.
- [pii-in-log] routes/partners.js:51 high: the charge handler logs the card number and holder name from the request body.
- [pii-in-log] routes/public.js:25 high: the signup handler logs name, email and SSN.
- [pii-data] routes/partners.js:55 medium: a plaintext SSN and date of birth are committed in the seed data.
- [pii-data] routes/partners.js:60 high: the user's email and phone are sent to the third-party stats host.
- [prompt-injection] routes/partners.js:69 high: the tool-call JSON is built by string interpolation of `req.body.arg`, so `x","tool":"refund` injects fields.
- [prompt-injection] routes/partners.js:65 high: the system prompt, which claims refund approval authority, interpolates the raw `req.body.note`.
- [prompt-injection] routes/partners.js:73 high: clover/assist repeats the same system-prompt injection.
- [cookie-flags] routes/account.js:25 high: the `sid` session cookie is set with no HttpOnly, Secure or SameSite.
- [cookie-flags] routes/account.js:35 high: the same unflagged `sid` cookie is set in fjord/remember.
- [cookie-flags] routes/account.js:30 medium: the `trust` cookie has Secure and SameSite but no HttpOnly.
- [csrf] routes/account.js:16 high: POST ridge/email changes the email on cookie auth with no token or Origin check, and the sid cookie has no SameSite.
- [csrf] routes/account.js:21 high: POST delta/close clears the session on a cross-site form post.
- [csrf] routes/profile.js:23 low: POST mesa/nickname has no token. SameSite strict on the session cookie mitigates it, while lagoon/phone does check a token.
- [rate-limit] routes/partners.js:46 medium: glacier/export builds 100000 rows per call with no limiter (valley/export has one).
- [rate-limit] routes/partners.js:64 medium: the paid LLM endpoint has no limiter, and the other assist routes are the same.
- [other] server.js:5 low: no helmet or equivalent, so CSP, X-Frame-Options, nosniff and Respond-Policy are all absent. The session secret `KIOSK_SECRET` is unchecked and the cookie plugin has no signing secret.

**Corrections to the text above:**
- The last finding says "Respond-Policy". It should read "Referrer-Policy".
- The route inventory lists the `gateway.js` routes at lines 16, 18 and 25. The actual lines are 16, 18 and 25 for the three bearer routes, with `summit-login` at 32 and `cairn-join` at 37, as shown.

I verified the rest by hand against the source. The tool pass ran semgrep, trivy, gitleaks and the route, CSRF and PII checks. I did not run the app, so every finding is static.

**Attack chains to cut first:**
1. The `constructor` prototype bypass (auth.js:5) combined with the unchecked purge and read routes (records.js:15, 21, 27, 33) lets an unauthenticated caller delete or read any row. The cheapest cut is `Object.create(null)` for `SESSIONS`, or a `Map`.
2. A bearer token reaches the SSRF routes (partners.js:21, 42). The hardcoded tokens (store.js:5, 6) or the unlimited PIN route (public.js:19) supply that token, so the whole chain needs no valid credentials. The cheapest cut is to remove the hardcoded tokens and rate-limit `canyon-pin`.