#!/usr/bin/env python3
"""Tests for dynamic_probe.py against a stub localhost http.server (never a real host)."""
import http.server, json, pathlib, subprocess, sys, threading

S = str(pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/dynamic_probe.py")
hits = {"n": 0}


class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        code, hdr = 200, {}
        if "%zz" in self.path:
            code = 500
        elif self.path.startswith("/limited"):
            hits["n"] += 1
            code = 429 if hits["n"] > 5 else 200
        elif "next=" in self.path:
            code, hdr = 302, {"Location": self.path.split("next=")[1]}
        self.send_response(code)
        for k, v in hdr.items():
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *a):
        pass


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}"
fails = n = 0


def check(name, cond):
    global fails, n
    n += 1
    if not cond:
        fails += 1
        print("FAIL", name)


def run(*a):
    p = subprocess.run([sys.executable, S, *a], capture_output=True, text=True)
    return p.returncode, (json.loads(p.stdout) if p.stdout else [])


rc, rows = run("--rate-endpoint", "/open", "--burst", "10", base)
rules = [r["rule"] for r in rows]
check("exit 0", rc == 0)
check("5xx on malformed percent", "server-error" in rules)
check("no rate limit found", "no-rate-limit" in rules)
check("missing headers found", rules.count("missing-header") >= 3)
check("open redirect found", "open-redirect" in rules)
check("row shape", all({"file", "line", "rule", "message", "text", "tool"} <= set(r) for r in rows))
rc, rows = run("--rate-endpoint", "/limited", base)
check("429 -> clean rate row", any(r["file"] == "/limited" and r["rule"] == "clean" for r in rows))
rc, rows = run(base)
check("no endpoint -> not-checked", any(r["rule"] == "not-checked" for r in rows))
rc, rows = run("--rate-endpoint", "/x", "http://127.0.0.1:1")
check("unreachable -> not-checked, no finding", rc == 0 and any(r["rule"] == "not-checked" for r in rows) and not any(r["rule"] == "no-rate-limit" for r in rows))
for bad in ("http://example.com", "http://127.0.0.1.evil.com", "https://localhost@evil.com", "ftp://localhost", "http://10.0.0.1:80", "http://[::1]:80"):
    check(f"refuse {bad}", run(bad)[0] == 2)
check("refuse bad burst", run("--burst", "x", base)[0] == 2)
srv.shutdown()
print(f"dynamic_probe: {n - fails}/{n}")
sys.exit(1 if fails else 0)
