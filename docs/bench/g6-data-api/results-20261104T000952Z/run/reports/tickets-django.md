# Security audit: tickets-django

I read all 8 tracked files by hand. The tool pass did not run, and the two tool-assisted sections below say so. Line numbers are against the current tree.

## Entry-point inventory

No CLI, jobs, consumers, webhooks, CI workflows, file uploads or MCP servers exist. The only entries are the 36 routes in `desk/urls.py:5-43`. The "Gate" column says which control applies:

- **Global:** `ApiGateMiddleware` (`desk/middleware.py:14-23`) gates only paths starting with `/api/`.
- **Decorator:** a per-view decorator (`staff_required` or `role_required`).
- **None:** nothing gates the view.

| Route | View | Gate |
|---|---|---|
| `GET api/public/queues` | `views.queue_stats` | `auth_exempt` (public) |
| `GET api/tickets` | `list_tickets` | Global |
| `GET api/queues/count` | `queue_count` | Global |
| `GET api/tickets/count` | `ticket_count` | Global |
| `GET api/tickets/<id>` | `get_ticket` | Global, owner check |
| `GET api/tickets/<id>/body` | `ticket_body` | Global, no owner check |
| `POST api/tickets/<id>/delete` | `delete_ticket` | Global, owner check |
| `POST api/tickets/<id>/title` | `retitle_ticket` | Global, no owner check |
| `POST api/sla/refresh` | `sla_refresh` | Global |
| `GET api/preview` | `preview` | Global |
| `GET api/preview/safe` | `preview_safe` | Global |
| `GET api/sla/<id>` | `sla_lookup` | Global |
| `GET api/sla/<id>/history` | `sla_history` | Global |
| `GET api/sla/<id>/archive` | `sla_archive` | Global |
| `GET api/sla/<id>/digest` | `sla_digest` | Global |
| `GET api/sla/<id>/trend` | `sla_trend` | Global |
| `GET staff/audit` | `staff_audit` | None |
| `POST staff/queues/<id>/pause` | `pause_queue` | `staff_required` |
| `GET staff/overview` | `staff_overview` | `role_required("lead")` |
| `POST staff/reindex` | `staff_reindex` | `role_required("lead")` |
| `GET staff/me/tickets` | `my_tickets` | `staff_required` |
| `GET api/ext/search-tickets` | `extras.search_tickets` | Global |
| `GET api/ext/list-tickets-all` | `extras.list_tickets_all` | Global |
| `POST auth/login` | `extras.login` | None |
| `POST web/ext/change-email` | `extras.change_email` | `login_required`, `csrf_exempt` |
| `POST web/ext/close-account` | `extras.close_account` | `login_required`, `csrf_exempt` |
| `POST web/ext/change-phone` | `extras.change_phone` | `login_required` |
| `GET web/ext/start-session` | `extras.start_session` | `login_required` |
| `GET web/ext/start-admin-session` | `extras.start_admin_session` | `login_required` |
| `GET web/ext/start-secure-session` | `extras.start_secure_session` | `login_required` |
| `POST auth/signup` | `extras.signup` | None |
| `POST api/ext/pay-card` | `extras.pay_card` | Global |
| `POST auth/signup-hashed` | `extras.signup_hashed` | None |
| `POST api/ext/track-ticket` | `extras.track_ticket` | Global |
| `POST api/ext/summarize-note` | `extras.summarize_note` | Global |
| `POST api/ext/lookup-tool` | `extras.lookup_tool` | Global |
| `POST api/ext/explain-topic` | `extras.explain_topic` | Global |

**Outbound calls:**
- `sla.vendor.example.com`, using `SLA_KEY`.
- `llm.vendor.example.com` (chat and tools).
- `analytics.vendor.example.com`.
- An arbitrary user-supplied URL in `/api/preview`.

**Assets:**
- Static bearer tokens in `desk/store.py:1-4`.
- `SLA_KEY` from the environment.
- `DESK_PW` from the environment.
- `SECRET_KEY` hardcoded in `desk/settings.py:1`.
- The tickets and queues held in in-memory dicts.

## Attack paths

1. **Repository to staff action.**
   - The tokens `tok-agent` and `tok-lead` are committed in `desk/store.py:2-3`, so anyone with repo access holds working credentials.
   - Using `tok-agent` on `staff/queues/<id>/pause` (`desk/views.py:158`) pauses a queue, because `staff_required` accepts any role.
   - Using `tok-lead` reaches the lead-only routes.
   - Cheapest cut: stop shipping static tokens.
2. **Ticket data without credentials.**
   - `/api/public/queues` (`desk/views.py:19-25`) and `/staff/audit` (`:152-155`) list every ticket's `owner_id` with no auth.
   - Those IDs are the keys for targeting other users.
   - Any valid token then reads other users' ticket bodies (`:42-47`) and rewrites their titles (`:76-82`).
   - Cheapest cut: add an owner check to the body and title views.
3. **SSRF to secrets.**
   - `/api/preview` (`desk/views.py:88`) fetches any URL, including cloud metadata and internal hosts, with no auth beyond any valid token.
   - Only the content type and byte count are returned, so exfiltration is blind or limited.
   - Cheapest cut: reuse the allow-list check from `preview_safe`.

## Findings

### High
1. **`desk/extras.py:45`** – the login check passes when both values are `None`. If `DESK_PW` is unset and the request omits `pass`, `None == None` returns `{"ok": true}`. The comparison is also not constant-time, and the view never establishes a session.
2. **`desk/views.py:152-155`** – `staff_audit` has no gate. The route is outside `/api/` and the view has no decorator, so anonymous callers get every ticket ID and owner ID.
3. **`desk/views.py:42-47`** – IDOR on `ticket_body`. It never compares `owner_id`, so `GET /api/tickets/2/body` with `tok-agent` returns ticket 2's body, which belongs to user 21.
4. **`desk/views.py:76-82`** – IDOR with write on `retitle_ticket`. Any token can change any ticket's title.
5. **`desk/views.py:158-165`** – `pause_queue` uses `staff_required`, which checks only that a session exists. Any role, including `agent`, can pause queues, while the other staff views require `lead`.
6. **`desk/store.py:1-4`** and **`desk/settings.py:1`** – hardcoded, non-expiring bearer tokens and a hardcoded `SECRET_KEY`.
7. **`desk/views.py:85-89`** – SSRF in `preview`. `url=http://169.254.169.254/...` is fetched server-side, and redirects are followed. `preview_safe` (`:92-98`) is the safe pattern.
8. **`desk/extras.py:96`** and **`:101`** – the SSN is logged in `signup` and the full card number in `pay_card`. These go to log storage in clear text, which is a PCI and privacy violation.

### Medium
9. **`desk/extras.py:48-58`** – `change_email` and `close_account` are `csrf_exempt` and cookie-authenticated (`login_required`). A cross-site POST from another origin can change a logged-in user's email or close their account.
10. **`desk/extras.py:73`**, **`:80`**, **`:88`** – session cookie values are `sha(REMOTE_ADDR)` or `sha(User-Agent)`, truncated to 16 hex characters. They are predictable and not random.
    - `:73` also sets no `HttpOnly`, `Secure` or `SameSite`.
    - `:80` sets no `Secure` or `SameSite`.
    - `:88` has good flags but a predictable value.
11. **`desk/extras.py:139`** – prompt injection in `summarize_note`. The untrusted note is concatenated into the **system** prompt, which also states "You may close tickets".
    - The LLM's reply is returned as the response body, so injected output goes straight to the client.
    - Because `HttpResponse` defaults to `text/html`, this allows reflected XSS (`:139`, `:144`, `:154`).
12. **`desk/extras.py:143`** – JSON injection in `lookup_tool`. `ticket=x"}}` breaks out of the string and lets the caller craft arbitrary tool arguments to the vendor.
13. **`desk/views.py:56`** – `verify=False` on the call that carries `X-Api-Key`, so a man-in-the-middle can read the SLA key and tamper with the response.
14. **`desk/views.py:121`** – the API key is placed in the URL query string (`?key=`), where it lands in proxy and server logs.
15. **`desk/views.py:130`** – `log.info` writes the `SLA_KEY` to the logs.
16. **`desk/extras.py:123`** – `track_ticket` forwards the requester's email and phone to a third-party analytics host with no consent or minimisation.
17. **`desk/extras.py:16-18`** and **`:43`** – the rate limiter is an in-process dict that never resets.
    - After 10 attempts an IP is locked out forever, which is a self-DoS.
    - The dict grows without bound.
    - It does not work across workers.
    - `REMOTE_ADDR` is trivially rotated by an attacker behind proxies.
    - `login` is the only route using it.
18. **`desk/extras.py:25-27`** – `ask_llm` has no auth or quota of its own and carries no per-user limit. An authenticated user can run up LLM cost.

### Low
19. **`desk/views.py:105`** – `sla_lookup` calls `requests.get` with no timeout, so a slow vendor hangs the worker.
20. **`desk/extras.py:35`** – `int(request.GET["limit"])` raises `ValueError` on non-numeric input, which returns a 500. Negative values are accepted with no cap.
21. **`desk/extras.py:108-109`** – unsalted truncated SHA-256 of an email is pseudonymous, easily reversed by dictionary, and not anonymous.
22. **`desk/extras.py:114-119`** – the `Requester` class carries `ssn`, `email` and `dob` as plaintext fields. It is not a Django model today, but if it becomes one it needs encryption.
23. **`desk/views.py:15`** – `os.environ["SLA_KEY"]` raises `KeyError` at import, so the app fails to start when it is unset (availability only).
24. **`desk/settings.py:1-9`** – no `ALLOWED_HOSTS`, no `SecurityMiddleware` (no HSTS or SSL redirect), no `X-Frame-Options` middleware, no session or CSRF cookie hardening. `DEBUG` is left at its default of `False`.
25. **`desk/middleware.py:15`** – the gate is path-prefix based and opt-out by decorator. Any new route outside `/api/` is ungated by default. That is the root cause of finding 2.

## Per-standard table

| Item | Status | Basis | Files | Negative |
|---|---|---|---|---|
| Authentication on all non-public routes | fail | guided:manual-read | desk/views.py:152 | |
| Object-level authorization | fail | guided:manual-read | desk/views.py:42, desk/views.py:76 | |
| Function-level authorization (role) | fail | guided:manual-read | desk/views.py:158 | |
| SSRF | fail | guided:manual-read | desk/views.py:88 | |
| TLS verification | fail | guided:manual-read | desk/views.py:56 | |
| Secrets in code and logs | fail | guided:manual-read | desk/store.py:2, desk/settings.py:1, desk/views.py:130, desk/views.py:121 | |
| PII and card data in logs | fail | guided:manual-read | desk/extras.py:96, desk/extras.py:101 | |
| CSRF | fail | guided:manual-read | desk/extras.py:48, desk/extras.py:54 | |
| Session and cookie security | fail | guided:manual-read | desk/extras.py:73, desk/extras.py:80 | |
| LLM and prompt injection | fail | guided:manual-read | desk/extras.py:139, desk/extras.py:143 | |
| Allow-listed LLM prompt input | pass | guided:manual-read | desk/extras.py:146-154 | `prompt = TOPICS.get(request.POST.get("topic"))` |
| Allow-listed outbound fetch (`preview_safe`) | pass | guided:manual-read | desk/views.py:92-98 | `target.hostname not in PREVIEW_HOSTS` |
| Ownership check on get and delete | pass | guided:manual-read | desk/views.py:37, desk/views.py:70 | `ticket["owner_id"] != request.user_info["id"]` |
| Injection (SQL and command) | not-checked | | | |

## NOT CHECKED
- Injection (SQL and command): there is no database or shell use in the code, so I had nothing to run a check against.
- Runtime authz, deployed config, WAF and TLS termination: they are not in the repo.
- Real `DESK_PW`, `SLA_KEY` and deployment secrets: not available.

## NOT RUN
- review_checks.sh --full: the sandbox refused to run the script, so the tool pass (including secret scan and static analysis) did not run.

## Static vs runtime
Needs a running system: deployed config, `DESK_PW` being set, proxy headers (`REMOTE_ADDR`), cloud metadata exposure for the SSRF, vendor-side behaviour, and log retention.

## Dependencies
- `requirements.txt` has no lockfile, so transitive pins are unknown.
- `Django==5.0.6` and `requests==2.32.3` could not be checked against current advisories, EOL dates or the CISA KEV list (no network lookup or tool was run). Both are `unverified`.
- From recall, 5.0.x was a non-LTS release that has since reached end of life, and `requests` 2.32.3 predates later fixes. Treat both as likely-stale and confirm before relying on this.