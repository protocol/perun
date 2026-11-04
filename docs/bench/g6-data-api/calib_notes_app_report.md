# Security audit: notes-app

The project is three files: `server.js`, `db.js` and `package.json`. I read all of them. I didn't run the app or `npm audit`.

## Routes and entry points

| Route | Auth | Handler |
|---|---|---|
| `POST /login` | none | `server.js:13` |
| `GET /admin/users` | **none** | `server.js:21` |
| `GET /notes/:id` | `auth` | `server.js:22` |
| `GET /preview?url=` | **none** | `server.js:27` |
| `GET /me` | `auth` | `server.js:30` |

- **Process entry point:** `server.js`, which calls `app.listen(3000)` at line 31. It binds all interfaces and uses plain HTTP.
- **Middleware:** `express.json()` (line 6), `cookie-parser` (line 7) and `auth` (lines 8–12).
- **Data store:** in-memory arrays in `db.js`.

## Findings

| # | Severity | Location | Issue |
|---|---|---|---|
| 1 | Critical | `server.js:21` | **Unauthenticated admin endpoint.** `GET /admin/users` has no `auth` middleware and no role check. It returns the full `users` array, including every `pw` value and every role. |
| 2 | Critical | `server.js:8-12`, `server.js:18` | **Forgeable session.** The `sid` cookie is just the user id, unsigned, and `auth` trusts it. Anyone can send `Cookie: sid=1` and become the admin without a password. Ids are guessable. |
| 3 | Critical | `server.js:27-29` | **SSRF.** `/preview` fetches any user-supplied URL with no auth and no allow-list. It can reach internal services and cloud metadata such as `169.254.169.254`, and it streams the response back. `https.get` throws synchronously on an invalid or non-https URL, and `req.query.url` can be undefined. That can crash the process, because the `.on("error")` handler doesn't catch the throw. |
| 4 | High | `server.js:28` | **TLS verification disabled.** `rejectUnauthorized:false` allows man-in-the-middle attacks on the outbound fetches. |
| 5 | High | `server.js:22-26` | **IDOR / broken access control.** `/notes/:id` checks that you're logged in but never checks `n.ownerId === req.user.id`. Any logged-in user can read note 2 ("secret") and every other note by iterating ids. |
| 6 | High | `db.js:1`, `server.js:16` | **Plaintext passwords** stored and compared directly (`pw:"x"`). The comparison isn't constant-time, and the credential is trivially weak and hardcoded. |
| 7 | High | `server.js:15` | **Credentials logged.** The email and plaintext password of every login attempt go to the logs. |
| 8 | Medium | `server.js:19` | **Cookie flags missing.** `res.cookie("sid", …)` sets no `httpOnly`, `secure` or `sameSite`. That exposes it to XSS theft and CSRF, and over HTTP to sniffing. There's no expiry or logout. |
| 9 | Medium | `server.js:13-20` | **No brute-force protection.** There's no rate limiting or lockout on `/login`, and no rate limiting anywhere else. |
| 10 | Medium | `server.js:14` | **No input validation.** If the JSON body is missing, `req.body` is `undefined`. Express 4 gives `{}` for JSON bodies, but a non-object value still causes odd behavior. Types of `email` and `password` aren't checked. |
| 11 | Low | `server.js:31` | **Plain HTTP on all interfaces.** There's no TLS or reverse-proxy assumption, and no security headers (`helmet`). |
| 12 | Low | `server.js:9` | **Data inconsistency.** Note 2 is owned by user 2, who doesn't exist in `db.js`. That's harmless now but shows the data model is a placeholder. |
| 13 | Info | `package.json:1` | **Dependencies unpinned and no lockfile.** Both use `^` ranges and no lockfile is committed. Run `npm audit` after installing. |

## Fix order

1. Add `auth` and an admin-role check to `/admin/users`, and strip the `pw` field from any output.
2. Replace the id cookie with a signed or random session token. Set `httpOnly`, `secure` and `sameSite`.
3. Hash passwords with bcrypt or argon2, and remove the password logging.
4. Check note ownership in `/notes/:id`.
5. Require auth on `/preview`. Validate the URL, allow-list hosts, block private IP ranges, and remove `rejectUnauthorized:false`. Wrap the call in try/catch.
6. Add rate limiting, `helmet` and a lockfile.