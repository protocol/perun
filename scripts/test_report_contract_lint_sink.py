#!/usr/bin/env python3
"""Tests: report_contract_lint.py rules finding-not-on-sink and class-mismatch (synthetic multi-language files)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LINT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/report_contract_lint.py"
TAIL = ("| Item | Status | Basis | Files | Negative |\n|---|---|---|---|---|\n| A | pass | tool:semgrep | app.py:1 | |\n"
        "\n## NOT CHECKED\n- none\n\n## NOT RUN\n- zap: no target\n\n## Static vs runtime\nneeds deploy.\n\n## Dependencies\nread.\n\n## Route inventory\n- GET /proxy app.py:1 auth=none rate-limit=no\n")
PAD = "x = 1\n" * 6  # keeps the route line more than 2 lines from the sink
FILES = {
    "app.py": '@app.get("/proxy")\ndef proxy(u):\n' + PAD + "    return requests.get(u, verify=False)\n",
    "app.js": "app.get('/p', h)\n" + PAD + "const r = await fetchJson(url)\n",
    "main.go": "func H(w, r) {\n" + PAD + "\tlog.Printf(\"user %s\", email)\n",
    "log.go": "func H(w, r) {\n" + PAD + "\tlog.Printf(\"token %s\", token)\n",
    "send.rb": "def h\n" + PAD + "  Net::HTTP.post(uri, email)\n",
    "c.java": "void h() {\n" + PAD + "  resp.addCookie(new Cookie(\"sid\", v));\n",
    "reset.php": "<?php\n" + PAD + "error_log('password reset for ' . $email);\n",
    "pk.rb": "def h\n" + PAD + "  logger.info(\"primary_key #{pk}\")\n",
    "kw.js": "function h() {\n" + PAD + "console.log('keyword=', kw)\n",
    "multi.rb": "def h\n" + PAD + "  logger.info(\n    Net::HTTP.post(uri, email)\n  )\n",
    "conn.java": "void h() {\n" + PAD + "  var c = url.openConnection();\n",
    "get.php": "<?php\n" + PAD + "$b = file_get_contents($u);\n",
    "tls.java": "void h() {\n" + PAD + "  b.hostnameVerifier(ALLOW_ALL);\n",
    "tls.js": "function h() {\n" + PAD + "const agent = trustAll();\n",
    "url.js": "function h() {\n" + PAD + "const u = base + '?key=' + k;\n",
    "sess.rb": "def h\n" + PAD + "  session[:id] = v\n",
    "pin.py": "def pin_login(pin):\n" + PAD + "    return check(pin)\n",
    "cat.php": "<?php\n" + PAD + "$catalog = load();\n",
}


def lint(finding):
    with tempfile.TemporaryDirectory() as d:
        for n, t in FILES.items():
            (Path(d) / n).write_text(t)
        r = Path(d) / "r.md"
        r.write_text("# Audit\n\n## Findings\n- " + finding + "\n\n## Per-standard table\n" + TAIL)
        p = subprocess.run([sys.executable, str(LINT), str(r), "--root", d], capture_output=True, text=True)
        return p.returncode, p.stdout


class Sink(unittest.TestCase):
    def bad(self, f, rule):
        rc, out = lint(f)
        self.assertEqual(rc, 1, out)
        self.assertIn(f": {rule}:", out)

    def ok(self, f):
        rc, out = lint(f)
        self.assertEqual(rc, 0, out)

    def test_route_line_is_not_a_sink(self):
        self.bad("[ssrf] app.py:1 high: proxy fetches u", "finding-not-on-sink")
        self.bad("[tls-off] app.js:1 high: x", "finding-not-on-sink")
        self.bad("[pii-in-log] main.go:1 high: x", "finding-not-on-sink")
        self.bad("[cookie-flags] c.java:1 high: x", "finding-not-on-sink")
        self.bad("[secret-in-log] log.go:1 high: x", "finding-not-on-sink")

    def test_correct_sink_and_wrapper_pass(self):
        self.ok("[ssrf] app.py:9 high: proxy fetches u")
        self.ok("[ssrf] app.js:8 high: wrapper call fetchJson(url)")
        self.ok("[pii-in-log] main.go:8 high: email logged")
        self.ok("[secret-in-log] log.go:8 high: token logged")
        self.ok("[cookie-flags] c.java:8 high: no flags")
        self.ok("[xss] app.py:1 high: unrelated classes are not sink-checked")

    def test_class_mismatch(self):
        self.bad("[pii-in-log] log.go:8 high: x", "class-mismatch")  # credential logged
        self.bad("[pii-in-log] send.rb:8 high: x", "class-mismatch")  # outbound, not a log

    def test_credential_mismatch_needs_credential_without_pii(self):
        self.ok("[pii-in-log] reset.php:8 high: password reset for an email")
        self.ok("[pii-in-log] pk.rb:8 high: primary_key is not a credential")
        self.ok("[pii-in-log] kw.js:8 high: keyword is not a credential")

    def test_log_in_window_not_only_cited_line(self):
        self.ok("[pii-in-log] multi.rb:9 high: email in multi-line log args")

    def test_more_sinks(self):
        self.ok("[ssrf] conn.java:8 high: openConnection")
        self.ok("[ssrf] get.php:8 high: file_get_contents")
        self.ok("[tls-off] tls.java:8 high: hostname verifier")
        self.ok("[tls-off] tls.js:8 high: trust all")
        self.ok("[secret-in-url] url.js:8 high: key in query")
        self.ok("[cookie-flags] sess.rb:8 high: session cookie")

    def test_login_and_catalog_are_not_log_calls(self):
        self.bad("[secret-in-log] pin.py:1 high: x", "finding-not-on-sink")
        self.bad("[pii-in-log] cat.php:8 high: x", "finding-not-on-sink")


if __name__ == "__main__":
    unittest.main()
