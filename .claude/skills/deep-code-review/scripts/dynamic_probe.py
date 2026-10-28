#!/usr/bin/env python3
"""dynamic_probe.py [--rate-endpoint PATH] [--burst N] BASE_URL — opt-in dynamic probes of a LOCAL running app.

Refuses (exit 2) any host but localhost / 127.0.0.1, userinfo, or a non-http(s) scheme. Never follows redirects.
Probes: malformed percent-encoding and oversized inputs (any 5xx is a finding), missing rate limiting (burst on
--rate-endpoint; without it that probe is not-checked), security headers, open redirect.
Prints a JSON array in the review_checks.sh row shape: {file,line,rule,message,text,tool}; rule is a finding id,
`clean` or `not-checked`. A clean row proves only what was probed. Read references/dynamic-probe.md before use.
"""
import http.client, json, ssl, sys
from urllib.parse import urlsplit

TOOL = "dynamic_probe"
rows = []


def row(path, rule, msg):
    rows.append({"file": path, "line": 0, "rule": rule, "message": msg, "text": f"{rule}: {msg}", "tool": TOOL})


def req(base, path):
    """GET raw path (no normalisation, no redirects) -> (status, headers) or None when the connection fails."""
    https = base.scheme == "https"
    cls = http.client.HTTPSConnection if https else http.client.HTTPConnection
    kw = {"context": ssl._create_unverified_context()} if https else {}  # localhost self-signed certs
    try:
        c = cls(base.hostname, base.port, timeout=5, **kw)
        c.request("GET", path)
        r = c.getresponse()
        r.read(1024)
        return r.status, {k.lower(): v for k, v in r.getheaders()}
    except (OSError, http.client.HTTPException):
        return None


def probe_inputs(b):
    cases = ["/%", "/%zz", "/%E0%A4%A", "/?q=%", "/?q=%zz", "/?q=%C0%AF", "/" + "a" * 10000, "/?q=" + "a" * 100000]
    bad = dropped = 0
    for p in cases:
        r = req(b, p)
        if r is None:
            dropped += 1
        elif r[0] >= 500:
            bad += 1
            row(p[:60], "server-error", f"GET returned {r[0]} for malformed or oversized input")
    if dropped:
        row("/", "not-checked", f"malformed/oversized inputs: {dropped} of {len(cases)} requests dropped, reset or timed out")
    elif bad == 0:
        row("/", "clean", f"no 5xx across {len(cases)} malformed/oversized inputs")


def probe_rate(b, ep, n):
    if not ep:
        return row("", "not-checked", "rate limit: pass --rate-endpoint PATH")
    res = [req(b, ep) for _ in range(n)]
    codes = [r[0] for r in res if r]
    dropped = res.count(None)
    if 429 in codes:
        row(ep, "clean", f"429 seen within {n} requests")
    elif dropped:
        row(ep, "not-checked", f"rate limit: {dropped} of {n} requests dropped, reset or timed out, no 429")
    else:
        row(ep, "no-rate-limit", f"{n} rapid requests, no 429 (statuses seen: {sorted(set(codes))})")


def probe_headers(b):
    r = req(b, "/")
    if not r:
        return row("/", "not-checked", "security headers: / unreachable")
    h = r[1]
    want = ["content-security-policy", "x-content-type-options", "referrer-policy"]
    if "frame-ancestors" not in h.get("content-security-policy", ""):
        want.append("x-frame-options")
    if b.scheme == "https":
        want.append("strict-transport-security")
    miss = [w for w in want if w not in h]
    for m in miss:
        row("/", "missing-header", f"{m} absent")
    if not miss:
        row("/", "clean", "expected security headers present")


def probe_redirect(b):
    evil, hit, dropped = "https://evil.example.com", 0, 0
    for k in ("next", "url", "redirect", "redirect_uri", "return", "returnTo", "dest", "continue"):
        r = req(b, f"/?{k}={evil}")
        dropped += r is None
        loc = r[1].get("location", "") if r and 300 <= r[0] < 400 else ""
        if loc.startswith((evil, "//evil.example.com")):
            hit += 1
            row(f"/?{k}=", "open-redirect", f"{r[0]} Location echoes attacker URL")
    if dropped:
        row("/", "not-checked", f"open redirect: {dropped} requests dropped, reset or timed out")
    elif not hit:
        row("/", "clean", "no redirect to an off-site URL via common params (only / probed)")


def main(argv):
    ep, n, args = "", 30, list(argv)
    while len(args) > 1 and args[0] in ("--rate-endpoint", "--burst"):
        flag, val = args[0], args[1]
        args = args[2:]
        if flag == "--rate-endpoint":
            ep = val
        else:
            try:
                n = int(val)
                assert n > 0 and val.isascii()
            except (ValueError, AssertionError):
                print("usage: --burst needs a positive ASCII integer", file=sys.stderr)
                return 2
            n = min(n, 500)
    if len(args) != 1:
        print("usage: dynamic_probe.py [--rate-endpoint PATH] [--burst N] BASE_URL", file=sys.stderr)
        return 2
    try:
        b = urlsplit(args[0])
        b.port
    except ValueError:
        print("REFUSED: bad URL", file=sys.stderr)
        return 2
    if b.scheme not in ("http", "https") or b.username or b.password or b.hostname not in ("localhost", "127.0.0.1"):
        print("REFUSED: base URL must be http(s)://localhost or 127.0.0.1, no userinfo", file=sys.stderr)
        return 2
    if ep and not ep.startswith("/"):
        print("REFUSED: --rate-endpoint must start with /", file=sys.stderr)
        return 2
    probe_inputs(b), probe_rate(b, ep, n), probe_headers(b), probe_redirect(b)
    print(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
