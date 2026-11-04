# Security audit: scoreboard-flask (FULL scope)

The code is four files: `app.py`, `extras.py`, `store.py` and `requirements.txt`. I read all of it and ran `review_checks.sh --full`. I did not run the app, so every finding is from reading the code and tool output.

The attack path that matters most is the first one below, then the two findings after it.

## Attack paths

1. **Hardcoded admin token leads to SSRF.**
   - `store.py:2-3` commits the bearer tokens `tok-user` and `tok-admin`. They are static, guessable and in git.
   - `app.py:24-33` is the global gate. It accepts any token in that dict.
   - `app.py:132-136` fetches an arbitrary URL, including internal addresses and cloud metadata.
   - Result: anyone who reads the repo gets admin access and internal network reach.
   - Cheapest cut: replace the static token dict with real credentials loaded from a secret store.
2. **Unauthenticated login bypass.**
   - `extras.py:48` compares `request.json.get("pass")` to `os.environ.get("SCORE_PW")`.
   - If `SCORE_PW` is unset, sending `{}` or `{"pass": null}` makes `None == None` true, so the endpoint returns `ok: true`.
   - Cheapest cut: refuse to start without `SCORE_PW`, and use `hmac.compare_digest`.
3. **Any member can change flags, rename teams and read other users' notes.**
   - This takes `tok-user` plus the missing authorization checks in findings 4, 5 and 6 below.

## Findings (most severe first)

1. **High, `store.py:1-4`: hardcoded static bearer tokens.** Admin `tok-admin` (id 11) is in source control. Sending `Authorization: Bearer tok-admin` authenticates as admin. `app.py:20` also accepts the raw token without the `Bearer ` prefix.
2. **High, `extras.py:44-48`: login auth bypass and a broken limiter.**
   - The `None == None` bypass is described above.
   - The comparison is not constant-time.
   - The endpoint returns a boolean and never sets `session["user"]`, so it is not a working login.
   - `HITS` (`extras.py:10, 20-22`) is never reset. After 10 attempts in total from one IP, that IP is blocked until restart.
   - The counter is per process and keyed on `remote_addr`, so clients behind a proxy share one bucket.
3. **High, `app.py:132-136`: SSRF in `/api/badge`.**
   - The URL comes from `?url=` with no scheme or host check.
   - Failing input: `?url=http://169.254.169.254/latest/meta-data/`.
   - The response reveals content-type and byte count, which works as an internal port scanner.
   - `/api/badge/safe` (`app.py:139-145`) does this correctly with an HTTPS-only host allowlist and `allow_redirects=False`.
4. **High, `app.py:123-129`: broken object-level authorization on `PUT /api/teams/<id>`.**
   - There is no `owner_id` check, unlike `delete_team` at `app.py:117`.
   - Failing input: with `tok-user` (id 10), `PUT /api/teams/2` with `{"name":"x"}` renames the team owned by id 11.
   - `request.get_json()` returns `None` for a non-JSON body, which raises and returns a 500.
   - The name is stored with no length or content validation.
5. **High, `app.py:205-211`: `/admin/flags/<name>` uses `@login_required` instead of `require_role("admin")`.** Any member can flip `betting_odds` and `live_scores`. `bool(...get("on"))` also turns the string `"false"` into `True`.
6. **High, `app.py:199-202`: `/admin/audit` has no authentication.** It is outside `/api/`, so the global gate skips it, and it has no decorator. It returns every match id with its `owner_id` to anonymous callers.
7. **High, `app.py:98-103`: `verify=False` on the call that sends `X-Api-Key`.** A network-position attacker can read `FEED_KEY`. Any member can trigger this call through `POST /api/feed/refresh`.
8. **Medium, `app.py:88-93`: `match_notes` has no owner check.** `get_match` at `app.py:83` has one. Failing input: `GET /api/matches/2/notes` as `tok-user` returns the other owner's notes.
9. **Medium, `FEED_KEY` is leaked in three places.**
   - `app.py:168` puts the key in the URL query string, so it lands in vendor, proxy and access logs.
   - `app.py:177` logs the key itself.
   - `app.py:152` has no timeout, so a slow upstream hangs a worker.
10. **Medium, `extras.py:66`: the CSRF check passes when the token is absent.**
    - A request with neither the `X-CSRF-Token` header nor the `csrf` cookie compares `None != None`, which is false, so the check is skipped.
    - This is a double-submit check with an unsigned cookie, and nothing in the code sets that cookie.
    - `extras.py:52-58` (`/web/ext/account/email` and `/account/close`) have no CSRF check at all. They are state-changing POSTs authenticated by a cookie session.
11. **Medium, `extras.py:71-89`: predictable cookie values and weak flags.**
    - `sid` is `sha(remote_addr)` and `admin_sid` is `sha(user_agent)`. Both are guessable and neither is random.
    - `extras.py:74` has no `Secure`, `HttpOnly` or `SameSite` flags. `extras.py:80` has `HttpOnly` only.
    - `extras.py:88` has good flags but the same predictable value.
    - Nothing in the code reads these cookies back, so they are not an exploitable bypass today. They become one if they are later used for auth.
12. **Medium, `extras.py:96` and `extras.py:101`: sensitive data written to logs.** Signup logs the email and SSN, and the pay route logs the full card number. `extras.py:107-110` hashes the email instead, which is the pattern to follow.
13. **Medium, `extras.py:116-119`: real-looking PII in source.** Names, SSNs and dates of birth are committed. `extras.py:130-133` holds vault references.
14. **Medium, `extras.py:121-124`: email and phone are forwarded to a third-party analytics service** with no consent check.
15. **Medium, LLM routes in `extras.py`:**
    - Line 139 puts user text into the system prompt next to "You may approve refunds". That is prompt injection with an agency claim.
    - Line 143 builds JSON by string concatenation. A `sku` of `x"}},"..."` can change the tool name or arguments.
    - Line 35 passes the raw JSON body. A non-dict body such as `[]` raises and returns a 500.
    - These endpoints have no per-user rate limit or spend cap. The `cost-limit` tool reported 0 costly handlers, but its heuristic missed LLM calls.
    - `/api/ext/ai/explain` (`extras.py:149-154`) uses an allowlist and has no injection path.
16. **Medium, `extras.py:37-40`: unbounded upload.** `request.get_data()` reads the whole body, and no `MAX_CONTENT_LENGTH` is set. A large POST exhausts memory.
17. **Medium, `app.py:148-188`: feed proxy routes check that the team exists but not that the caller owns it.** Any member can read any team's feed data.
18. **Medium, `app.py:65-71`: `/api/open/standings` is public and exposes `owner_id`.** The gate bypass is a bare prefix match at `app.py:27`, so any future route under `/api/open/` is public by default.
19. **Low, `app.py:159-161, 152, 186`: upstream errors are not handled.** `resp.json()` is called without `raise_for_status`, so a non-JSON vendor reply returns a 500.
20. **Low, `app.py:234-236`: `SESSION_KEY` is read after the extras import and crashes if unset.** `app.py:15` does the same for `FEED_KEY`. Failing early is fine, but there is no key-strength check.
21. **Low: no security headers and no `MAX_CONTENT_LENGTH`.** `header-config` could not run on this project.

## Route and entry-point inventory

The global gate is `app.before_request` (`app.py:24-33`). It requires a bearer token on every `/api/` path except `/api/open/`. It also covers the blueprint's `/api/ext/*` routes, so the `route-auth` "auth=none" output for those is a heuristic false positive. The blueprint's `/web/` gate (`extras.py:13-17`) needs `session["user"]`, but no code ever sets that key.

| Route | Method | Auth in effect | Notes |
|---|---|---|---|
| `/api/open/standings` | GET | none (intended) | Leaks `owner_id` (finding 18) |
| `/api/teams` | GET | bearer | Filtered by owner |
| `/api/teams/count` | GET | bearer | Filtered by owner |
| `/api/teams/<id>` | DELETE | bearer | Owner-checked |
| `/api/teams/<id>` | PUT | bearer | No owner check (finding 4) |
| `/api/matches` | GET | bearer | Filtered by owner |
| `/api/matches/<id>` | GET | bearer | Owner-checked |
| `/api/matches/<id>/notes` | GET | bearer | No owner check (finding 8) |
| `/api/feed/refresh` | POST | bearer | `verify=False` (finding 7) |
| `/api/feed/teams/<id>` and `/form`, `/history`, `/odds`, `/roster` | GET | bearer | No owner check (finding 17) |
| `/api/badge` | GET | bearer | SSRF (finding 3) |
| `/api/badge/safe` | GET | bearer | Host allowlist |
| `/admin/audit` | GET | none | Finding 6 |
| `/admin/flags/<name>` | POST | login only | Finding 5 |
| `/admin/overview` | GET | admin role | |
| `/admin/recount` | POST | admin role | |
| `/admin/me/matches` | GET | login | Filtered by owner |
| `/api/ext/assist/chat` | POST | bearer | LLM call |
| `/api/ext/upload` | POST | bearer | Unbounded body |
| `/api/ext/pay` | POST | bearer | Logs card number |
| `/api/ext/track/order` | POST | bearer | PII sent to analytics |
| `/api/ext/ai/note`, `/lookup`, `/explain` | POST | bearer | LLM and tool calls |
| `/auth/login` | POST | none | Finding 2 |
| `/auth/signup`, `/auth/signup2` | POST | none | `signup` logs the SSN |
| `/web/ext/account/email`, `/close`, `/phone` | POST | session | Finding 10 |
| `/web/ext/session/start`, `/admin`, `/secure` | GET | session | Finding 11 |

**Other entry points:**
- There are no CLI scripts, CI workflows, jobs, consumers or webhooks in the repo.
- Outbound calls go to `feed.vendor.example.com`, `llm.vendor.example.com`, `analytics.vendor.example.com` and whatever URL `/api/badge` is given.
- The secrets are the `FEED_KEY`, `SESSION_KEY` and `SCORE_PW` environment variables, plus the hardcoded tokens in `store.py`.
- All data lives in in-memory dicts in `store.py`, so it resets on restart and is per process.

## Per-standard table

| Item | Status | Basis | Files | Negative |
|---|---|---|---|---|
| Broken authentication and secrets in code | fail | guided:manual-read | store.py:1-4, extras.py:48 | |
| Object-level authorization | fail | tool:route-auth | app.py:88, app.py:123, app.py:199, app.py:205 | |
| SSRF | fail | tool:semgrep | app.py:135 | |
| TLS verification | fail | tool:bandit | app.py:102 | |
| Cookie flags and session IDs | fail | tool:semgrep | extras.py:74, extras.py:80 | |
| CSRF | fail | guided:manual-read | extras.py:52, extras.py:66 | |
| Sensitive data in logs | fail | guided:manual-read | extras.py:96, extras.py:101, app.py:177 | |
| LLM prompt and tool injection | fail | guided:manual-read | extras.py:139, extras.py:143 | |
| Resource limits | fail | tool:cost-limit | extras.py:37, app.py:152 | |
| Dependency advisories | fail | tool:trivy | requirements.txt | |
| Tenant scope, security headers, osv advisories | not-checked | | | |

## NOT CHECKED
- Security headers and CORS: the `header-config` tool found no supported web app, and no CORS configuration is present in the code.
- Tenant scope: there is no Prisma schema, so that check did not apply.
- Currency of Flask 3.0.3 and requests 2.32.3: the PyPI lookup was blocked in this sandbox, so currency is unverified.
- Whether the `/web/` session flow works end to end, because nothing sets `session["user"]`.

## NOT RUN
- osv-scanner: exit 127, not installed.
- tenant-scope: skipped, no `*.prisma` file.
- header-config: skipped, no supported web app.

## Static vs runtime
Everything here is static. These items need a running system or deployment context:
- Reverse-proxy and TLS setup, and whether `remote_addr` is the real client address.
- Network egress controls and cloud metadata protection, which decide how bad the SSRF is.
- How `FEED_KEY`, `SESSION_KEY` and `SCORE_PW` are provisioned.
- Whether `SCORE_PW` is set in production.
- Log retention, which decides how long the card and SSN data persists.

## Dependencies
- trivy reports two advisories on `requests==2.32.3`:
  - CVE-2024-47081, a `.netrc` credential leak via crafted URLs. It is relevant because `/api/badge` fetches user-supplied URLs.
  - CVE-2026-25645, predictable temporary file creation.
  - I did not verify the fixed versions, so check them before upgrading.
- Flask 3.0.3: trivy reported no advisory. Currency is unverified.
- There is no lockfile, so versions are not hash-pinned.

I did not apply any fixes.