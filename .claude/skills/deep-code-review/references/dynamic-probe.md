Read this when static scanners came back clean (or are unavailable) and the target app runs locally: it probes for crash-on-bad-input, missing rate limiting, missing security headers and open redirects that source scanners miss. Opt-in; sibling of `app-pentest.md`.

## Run it

`python3 scripts/dynamic_probe.py [--rate-endpoint PATH] [--burst N] http://127.0.0.1:PORT` (beside the skill's other scripts). Only `localhost` and `127.0.0.1` are accepted (exit 2 otherwise; no allowlist override, unlike `app_pentest.sh`). Redirects are never followed. Use a disposable instance: the burst sends up to `--burst` (default 30, max 500) GETs to the named endpoint.

## Output

A JSON array in the `review_checks.sh` row shape (`file`, `line`, `rule`, `message`, `text`, `tool`). `rule` is a finding id, `clean` or `not-checked`:

- `server-error`: any 5xx on malformed percent-encoding (`/%`, `/%zz`, truncated UTF-8) or an oversized path or query. Typical root cause: an unhandled `URIError` / decode exception returning 500 instead of 400.
- `no-rate-limit`: no 429 within the burst on `--rate-endpoint`. Name the error or auth endpoint you care about; without the flag the row is `not-checked`.
- `missing-header`: CSP, `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options` (unless CSP `frame-ancestors`), and HSTS on https.
- `open-redirect`: a 3xx whose `Location` echoes an attacker URL passed via a common redirect parameter, on `/` only.
- `not-checked`: the endpoint was unreachable or not named. Never read it as clean.

## After the run

Findings are leads: reproduce by hand and apply `appsec-verify.md` section 1. `clean` covers only the inputs probed; a limiter keyed per IP or a redirect on another route is not seen. Say so; do not write "no vulnerabilities found". A burst can trip a limiter that exists but sits above `--burst`: raise it before filing `no-rate-limit`.
