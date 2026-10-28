#!/usr/bin/env python3
"""dynamic_probe.py tests with a mocked connection layer: no socket is bound or opened (runs in any sandbox)."""
import contextlib, http.client, importlib.util, io, json, pathlib, sys

S = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/dynamic_probe.py"
spec = importlib.util.spec_from_file_location("dynamic_probe", S)
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
fails = n = 0


def check(name, cond):
    global fails, n
    n += 1
    if not cond:
        fails += 1
        print("FAIL", name)


class Resp:
    def __init__(s, status, hdr):
        s.status, s._h = status, hdr

    def read(s, k=-1):
        return b""

    def getheaders(s):
        return list(s._h.items())


def fake_conn(handler, log):
    class C:
        def __init__(s, host, port, **kw):
            log.append(("conn", host, port))

        def request(s, method, path):
            log.append(("req", path))
            s.path = path

        def getresponse(s):
            return handler(s.path)
    return C


def run_main(argv, handler=lambda p: Resp(200, {}), log=None):
    log = [] if log is None else log
    http.client.HTTPConnection = fake_conn(handler, log)
    d.rows.clear()
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = d.main(argv)
    return rc, (json.loads(out.getvalue()) if out.getvalue() else []), log


def drop(p):
    raise ConnectionResetError


def rules(rows):
    return [r["rule"] for r in rows]


# gate bypasses: all refused, and no connection is ever attempted
for bad in ("http://localhost.evil.com", "http://localhost./", "http://127.0.0.1./", "http://0.0.0.0", "http://2130706433",
            "http://127.1", "http://127.0.0.2", "http://[::1]", "http://localhost@evil.com", "http://user:p@localhost", "ftp://localhost",
            "file:///etc/passwd", "http://localhost:99999", "http://127.0.0.1.evil.com", "localhost"):
    rc, rows, log = run_main([bad])
    check(f"refuse {bad}", rc == 2 and not log)
rc, rows, log = run_main(["http://LOCALHOST:8080"])
check("uppercase LOCALHOST accepted (hostnames are case-insensitive)", rc == 0 and log[0][1] == "localhost")

# redirect is never followed: exactly the 8 redirect-probe requests plus the others, none to the Location host
rc, rows, log = run_main(["http://127.0.0.1:1"], lambda p: Resp(302, {"Location": "https://evil.example.com"}))
check("redirect not followed (every conn is localhost)", {c[1] for c in log if c[0] == "conn"} == {"127.0.0.1"})
check("open redirect found", "open-redirect" in rules(rows))

# findings from a 5xx on malformed input
rc, rows, _ = run_main(["http://127.0.0.1:1"], lambda p: Resp(500, {}) if "%zz" in p else Resp(200, {}))
check("5xx -> server-error", "server-error" in rules(rows))

# drops and timeouts are never clean
for name, exc in (("reset", ConnectionResetError), ("timeout", TimeoutError)):
    def h(p, exc=exc):
        raise exc
    rc, rows, _ = run_main(["--rate-endpoint", "/x", "--burst", "3", "http://127.0.0.1:1"], h)
    check(f"{name}: no clean row", "clean" not in rules(rows))
    check(f"{name}: not-checked rows for inputs, rate, headers, redirect", rules(rows).count("not-checked") == 4)

# a single drop among 200s in the inputs probe (oversized request reset) -> not-checked, not clean
state = {"i": 0}


def one_drop(p):
    state["i"] += 1
    if len(p) > 100000:
        raise ConnectionResetError
    return Resp(200, {})


rc, rows, _ = run_main(["http://127.0.0.1:1"], one_drop)
check("one dropped oversized input -> not-checked, no clean for inputs", any(r["rule"] == "not-checked" and "inputs" in r["message"] for r in rows) and not any(r["rule"] == "clean" and r["file"] == "/" and "inputs" in r["message"] for r in rows))

# rate: some drops with a 429 -> clean; drops without 429 -> not-checked; none dropped, no 429 -> finding
calls = {"i": 0}


def mixed(p):
    calls["i"] += 1
    if calls["i"] % 2:
        raise ConnectionResetError
    return Resp(429, {})


rate = lambda rows: [r for r in rows if r["file"] == "/x"]
d.rows.clear()
http.client.HTTPConnection = fake_conn(mixed, [])
d.probe_rate(d.urlsplit("http://127.0.0.1:1"), "/x", 4)
check("429 amid drops -> clean", rules(d.rows) == ["clean"])
d.rows.clear()
http.client.HTTPConnection = fake_conn(lambda p: Resp(200, {}), [])
d.probe_rate(d.urlsplit("http://127.0.0.1:1"), "/x", 4)
check("no 429, no drops -> no-rate-limit", rules(d.rows) == ["no-rate-limit"])

# burst validation: usage error (exit 2), never a traceback
for v in ("²", "x", "0", "-1", "٣", ""):
    rc, _, log = run_main(["--burst", v, "http://127.0.0.1:1"])
    check(f"burst {v!r} rejected", rc == 2 and not log)

print(f"dynamic_probe mock: {n - fails}/{n}")
sys.exit(1 if fails else 0)
