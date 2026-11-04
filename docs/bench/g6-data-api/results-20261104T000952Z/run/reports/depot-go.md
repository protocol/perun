# Security audit: depot-go (FULL scope)

I read all 5 Go files (about 700 lines, no dependencies) by hand. `review_checks.sh --full` ran, but its route-auth, attempt-limit and cost-limit checks all reported "no HTTP handlers", so they were no help here. The findings below come from reading the code, not from a tool. I didn't run the app, and I didn't run the report-contract linter.

## Entry-point inventory

The only entry point is `main.go:88`, a plain-HTTP listener on `:8080` with no `http.Server` timeouts. There are no CLI tools, CI workflows, jobs or consumers in the repo. Outbound calls go to the carrier, LLM and analytics vendors.

`gate` (`main.go:40`) only protects paths starting with `/api/`, and exempts `/api/open/`. Everything outside `/api/` depends on per-handler wrappers.

| Route | Auth actually enforced | Where |
|---|---|---|
| GET `/api/open/pallets` | none (gate exemption) | stock.go:23 |
| GET `/api/pallets` | bearer token | stock.go:31 |
| GET `/api/pallets/{id}` | bearer token + owner check | stock.go:42 |
| GET `/api/pallets/{id}/notes` | bearer token, **no owner check** | stock.go:52 |
| DELETE `/api/pallets/{id}` | bearer token + owner check | stock.go:62 |
| PUT `/api/pallets/{id}/label` | bearer token, **no owner or role check** | stock.go:73 |
| GET `/staff/audit` | **none** (outside `/api/`, no wrapper) | stock.go:85 |
| POST `/staff/docks/{id}/close` | login only, no role | stock.go:93 |
| GET `/staff/overview` | admin | stock.go:103 |
| POST `/staff/reindex` | admin | stock.go:107 |
| GET `/staff/me/pallets` | login | stock.go:112 |
| POST `/api/carrier/refresh` | bearer token | outbound.go:25 |
| GET `/api/preview` | bearer token | outbound.go:41 |
| GET `/api/preview/safe` | bearer token | outbound.go:52 |
| GET `/api/carrier/rates/{zone}` | bearer token | outbound.go:68 |
| GET `/api/carrier/rates/{zone}/history` | bearer token | outbound.go:85 |
| GET `/api/carrier/rates/{zone}/archive` | bearer token | outbound.go:102 |
| GET `/api/carrier/rates/{zone}/digest` | bearer token | outbound.go:118 |
| GET `/api/ext/export/all` | bearer token | extras.go:251 |
| POST `/api/ext/upload` | bearer token | extras.go:252 |
| GET `/api/ext/items` | bearer token | extras.go:254 |
| POST `/api/ext/pay` | bearer token | extras.go:264 |
| POST `/api/ext/pay2` | bearer token | extras.go:266 |
| GET `/api/ext/dev/seed` | bearer token | extras.go:267 |
| GET `/api/ext/dev/refs` | bearer token | extras.go:269 |
| POST `/api/ext/track/order` | bearer token | extras.go:268 |
| POST `/api/ext/track/order2` | bearer token | extras.go:270 |
| POST `/api/ext/ai/note` | bearer token | extras.go:271 |
| POST `/api/ext/ai/lookup` | bearer token | extras.go:272 |
| POST `/api/ext/ai/explain` | bearer token | extras.go:273 |
| POST `/api/ext/ai/lookup2` | bearer token | extras.go:274 |
| POST `/auth/login` | none (by design) | extras.go:253 |
| POST `/auth/signup` | none | extras.go:263 |
| POST `/auth/signup2` | none | extras.go:265 |
| POST `/web/ext/account/email` | cookie `sid` | extras.go:255 |
| POST `/web/ext/account/close` | cookie `sid` | extras.go:256 |
| POST `/web/ext/account/phone` | cookie `sid` + CSRF token | extras.go:257 |
| POST `/web/ext/account/key` | cookie `sid` + Origin check | extras.go:258 |
| GET `/web/ext/session/start` | cookie `sid` | extras.go:259 |
| GET `/web/ext/session/admin` | cookie `sid` | extras.go:260 |
| GET `/web/ext/session/secure` | cookie `sid` | extras.go:261 |
| GET `/web/ext/session/clear` | cookie `sid` | extras.go:262 |

## Assets

- **Secrets:**
  - `CARRIER_KEY` (env var).
  - `DEPOT_PW` (env var).
  - The hardcoded bearer tokens at `main.go:18-21`.
  - The hardcoded session ID `sess-demo` at `extras.go:41`.
- **Data:** pallets (in memory), seeded customer PII with SSNs, vault references, and card numbers in transit.
- **Crown jewels:** the carrier API key, customer PII and card data, and the admin token.

## Attack paths

1. **Hardcoded credentials give full access with no secrets.** `tok-admin` and `tok-picker` are in the source (`main.go:19-20`), so anyone with repo access holds a valid admin token. `sess-demo` (`extras.go:41`) opens every `/web/*` route. Cheapest cut: remove the static tokens and `sess-demo`, and use real, expiring sessions.
2. **Any logged-in user can steal the carrier key.**
   - Any token can call `/api/preview` (`outbound.go:41`) and fetch cloud metadata or internal hosts through the SSRF.
   - `/api/carrier/refresh` (`outbound.go:28`) skips TLS verification while sending `X-Api-Key`, so a network attacker can read the key.
   - The digest route logs the key (`outbound.go:124`).
   - Cheapest cut: validate the preview URL against an allowlist, as `/api/preview/safe` already does.

## Findings (ranked)

**High**
1. `extras.go:41,47`: the hardcoded session ID `sess-demo` is valid for every `/web/*` route. Sending `Cookie: sid=sess-demo` bypasses authentication.
2. `main.go:18-21`: static, non-expiring bearer tokens are committed in source, including an admin token.
3. `extras.go:55`: if `DEPOT_PW` is unset, `os.Getenv` returns `""`. Then `POST /auth/login` with any `user` and an empty `pass` passes the check. The comparison is also not constant-time.
4. `stock.go:85`: `/staff/audit` has no auth. The gate skips non-`/api/` paths and the handler has no wrapper, so it lists all pallet IDs and owner IDs to anonymous callers.
5. `stock.go:52`: `/api/pallets/{id}/notes` has no owner check. A picker token reads another user's pallet notes with `/api/pallets/2/notes` (an IDOR).
6. `stock.go:73`: `PUT /api/pallets/{id}/label` has no owner or role check. Any logged-in user can overwrite any pallet's label.
7. `outbound.go:42`: `/api/preview` is an SSRF. It fetches any user-supplied URL, follows redirects, and returns the body. Example: `?url=http://169.254.169.254/latest/meta-data/`.
8. `outbound.go:48`: `/api/preview` copies the upstream `Content-Type` back to the caller. A page served as `text/html` runs in the app's origin (XSS).
9. `outbound.go:28`: `InsecureSkipVerify: true` on a request that carries `X-Api-Key`. A man-in-the-middle can capture the carrier key.
10. `extras.go:161` and `extras.go:167`: `signup` logs the SSN and `payCard` logs the full card number (PAN). This is a PCI and privacy violation.
11. `extras.go:190-195`: `/api/ext/dev/seed` serves real-looking SSNs and dates of birth to any token holder. The dev route is registered in the production mux. `/api/ext/dev/refs` (`extras.go:211`) exposes vault references the same way (Medium).
12. `extras.go:135,140,148`: session IDs are `sha(RemoteAddr)` or `sha(UserAgent)` truncated to 8 bytes. They are predictable, so an attacker can forge or guess them. `sha` is at `extras.go:57`.
13. `extras.go:223`: `/api/ext/ai/note` puts user text into the system prompt next to "You may approve refunds". That is prompt injection with an implied privilege, and the model output is returned to the caller.

**Medium**
14. `extras.go:73-80`: login does not check that `RemoteAddr` is per-client. It includes the source port, so the rate-limit key changes with each new connection and the limit is easy to bypass. The counter never resets and the `hits` map grows without bound.
15. `extras.go:78-80`: a successful login returns 200 and sets no session.
16. `stock.go:93`: `/staff/docks/{id}/close` needs only a login, so a picker can close docks. It likely should be admin-only.
17. `extras.go:93,104`: cookie-authenticated state changes (email change, account close) have no CSRF token. The `sid` cookie is set with no `SameSite` attribute (`extras.go:135`), so cross-site POSTs can carry it.
18. `extras.go:135,140`: the cookies lack `Secure`, `HttpOnly` or `SameSite`. `sid` has none of them and `admin_sid` lacks `Secure` and `SameSite`.
19. `extras.go:117`: the CSRF check passes when the `csrf` cookie and the `X-CSRF-Token` header are both empty. That is a weak double-submit check.
20. `outbound.go:108`: the carrier key is sent in the URL query string (`?key=`), where it can end up in logs.
21. `outbound.go:124`: the digest route writes the carrier key to the log.
22. `outbound.go:76`: `http.DefaultClient` has no timeout, so a slow upstream can hang request goroutines.
23. `extras.go:199`: `trackOrder` sends raw email and phone to a third-party analytics vendor. The `trackOrderHashed` variant at `extras.go:214` does not.
24. `extras.go:228`: `lookupTool` builds JSON by string concatenation, so a `sku` containing `"` can inject extra JSON fields. `lookupToolSafe` at `extras.go:245` is the fixed version.
25. `extras.go:65`: `uploadBlob` reads an unbounded body, and `exportAll` (`extras.go:59`) has no auth beyond a login. Neither has `http.MaxBytesReader` or a size cap (DoS).
26. `stock.go:69,99` and `main.go:18`: the shared maps (`pallets`, `docks`) are written from handlers with no mutex. Concurrent requests can crash the process with "concurrent map writes".
27. `stock.go:26`: the unauthenticated `/api/open/pallets` exposes owner user IDs. This is probably more than a partner endpoint needs.
28. `main.go:88`: the server speaks plain HTTP only, with no `ReadHeaderTimeout` (slowloris exposure) and no security headers.

**Low**
29. `extras.go:37`: `askLLM` reads the vendor response with `io.ReadAll`, which is unbounded. Errors are swallowed.
30. `extras.go:263,265`: signup has no rate limit.
31. `outbound.go:65`: `/api/preview/safe` is a sound allowlist with redirects disabled. It still returns the body without size limits or a content-type check.

## Per-standard table
| Item | Status | Basis | Files | Negative |
|---|---|---|---|---|
| Authn on all routes | fail | manual read | main.go:42, stock.go:85, extras.go:41 | n/a |
| Object-level authorization | fail | manual read | stock.go:52, stock.go:73 | `p.OwnerID != userFrom(r).UserID` (present only on stock.go:45,65) |
| SSRF | fail | manual read | outbound.go:42 | `!sheetHosts[u.Hostname()]` (only on `/preview/safe`, outbound.go:54) |
| Secrets and logging | fail | manual read | outbound.go:124, extras.go:161,167 | n/a |
| TLS | fail | manual read | outbound.go:28 | n/a |
| Session and cookies | fail | manual read | extras.go:135,140 | n/a |
| Injection | fail | manual read | extras.go:223,228 | n/a |
| SQL injection | not-checked | no database in repo | n/a | n/a |

## NOT CHECKED
- SQL injection and tenant scope: the repo has no database.
- Frontend and XSS: there are no templates or static assets.
- Deployed config, TLS termination, WAF and reverse-proxy headers: they live outside the repo.
- Runtime authorization behaviour: I didn't run the app.

## NOT RUN
- gosec: unparseable output.
- route-auth: skipped with "no HTTP handlers". The check doesn't recognise Go 1.22 `mux.HandleFunc("METHOD /path")` patterns, so I did this by hand.
- attempt-limit: skipped with "no credential check or sign-in route", although `extras.go:73` is one.
- header-config: no supported web app.
- cost-limit: skipped with "no HTTP handler".
- tenant-scope: no `*.prisma` files.
- dep-currency: the endoflife.date lookup was blocked.

## Static vs runtime
All findings are from reading the code. Deployed config, the reverse proxy, secret values and whether `DEPOT_PW` is set all need a running system.

## Dependencies
There are no third-party dependencies and no lockfile. `go.mod` declares `go 1.22`, which I haven't checked against current support status, so I don't know whether it is still supported.