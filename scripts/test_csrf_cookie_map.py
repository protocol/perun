"""csrf_cookie_map.py (cookie-session handlers with no CSRF defence; session cookies without Secure/HttpOnly/SameSite): Express, Go (wrapped handler), Flask, Spring and Django
positives, defended and fully flagged negatives, the cookie-realm rule, the usage contract and the review_checks.sh --full wiring. Fictional fixtures; one new file per feature."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/deep-code-review/scripts"
sys.path.insert(0, str(SK))
import csrf_cookie_map as C  # noqa: E402

CSRF, FLAGS = "missing-csrf-protection", "missing-cookie-flags"


def rows(files):
    """(file, line, rule) rows from analyze() for a fresh temp repo built from {relative path: lines}."""
    with tempfile.TemporaryDirectory() as t:
        for rel, lines in files.items():
            p = Path(t) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return [(f, ln, r) for f, ln, r, _ in C.analyze(t)[0]]


EXPRESS = [
    "const router = require('express').Router();",
    "router.get('/web/session/start', (req, res) => {",
    "  res.cookie('sid', 'x', { path: '/' });",
    "  res.sendStatus(204);",
    "});",
    "router.post('/web/account/email', (req, res) => {",
    "  save(req.body.email);",
    "  res.sendStatus(204);",
    "});",
    "router.post('/web/account/phone', (req, res) => {",
    "  if (req.get('x-csrf-token') !== req.cookies.csrf) return res.sendStatus(403);",
    "  res.sendStatus(204);",
    "});",
    "router.post('/api/pay', (req, res) => {",
    "  res.sendStatus(202);",
    "});",
    "router.get('/web/session/ok', (req, res) => {",
    "  res.cookie('sid', 'x', { secure: true, httpOnly: true, sameSite: 'strict' });",
    "  res.sendStatus(204);",
    "});",
    "router.get('/web/session/admin', (req, res) => {",
    "  res.cookie('admin_sid', 'x', { httpOnly: true });",
    "  res.sendStatus(204);",
    "});",
]


class CsrfCookieMap(unittest.TestCase):
    def test_express(self):
        got = rows({"app.js": EXPRESS})
        self.assertIn(("app.js", 8, CSRF), got)  # state change, reported at its last statement
        self.assertNotIn(("app.js", 12, CSRF), got)  # token compared in the handler
        self.assertFalse([r for r in got if r[1] in (14, 15)])  # /api realm sets no cookie
        self.assertIn(("app.js", 3, FLAGS), got)
        self.assertIn(("app.js", 22, FLAGS), got)  # httpOnly alone still lacks secure and sameSite
        self.assertFalse([r for r in got if r[1] in (18, 19)])  # every flag set

    def test_go_wrapped_handler_is_followed_to_the_inner_function(self):
        go = ["package main", "", "func requireCookie(h http.HandlerFunc) http.HandlerFunc {",
              "\treturn func(w http.ResponseWriter, r *http.Request) {", "\t\tif _, err := r.Cookie(\"sid\"); err != nil {", "\t\t\treturn", "\t\t}",
              "\t\th(w, r)", "\t}", "}", "", "func changeEmail(w http.ResponseWriter, r *http.Request) {", "\t_ = r.FormValue(\"email\")", "\tw.Write(nil)", "}", "",
              "func start(w http.ResponseWriter, r *http.Request) {",
              "\thttp.SetCookie(w, &http.Cookie{Name: \"sid\", Value: \"x\", Path: \"/\", HttpOnly: true})", "}", "",
              "func routes(mux *http.ServeMux) {", "\tmux.HandleFunc(\"POST /web/account/email\", requireCookie(changeEmail))", "\tmux.HandleFunc(\"GET /web/session/start\", start)", "}"]
        got = rows({"main.go": go})
        self.assertIn(("main.go", 14, CSRF), got)
        self.assertIn(("main.go", 18, FLAGS), got)

    def test_flask_and_django(self):
        py = ["from flask import Blueprint, make_response", "bp = Blueprint('x', __name__)", "@bp.get('/web/start')", "def start():",
              "    resp = make_response('', 204)", "    resp.set_cookie('sid', 'x')", "    return resp", "@bp.post('/web/email')", "def email():", "    return '', 204"]
        self.assertEqual([("a.py", 6, FLAGS), ("a.py", 10, CSRF)], rows({"a.py": py}))
        dj = ["from django.views.decorators.csrf import csrf_exempt", "from django.views.decorators.http import require_http_methods", "def start(request):",
              "    r = HttpResponse()", "    r.set_cookie('sid', 'x', secure=True, httponly=True, samesite='Lax')", "    return r", "@csrf_exempt",
              "@require_http_methods(['POST'])", "def change(request):", "    return HttpResponse(status=204)", "@require_http_methods(['POST'])", "def ok(request):", "    return HttpResponse(status=204)"]
        urls = ["from django.urls import path", "from . import v", "urlpatterns = [\n    path('web/start', v.start),\n    path('web/change', v.change),\n    path('web/ok', v.ok),\n]"]
        got = rows({"v.py": dj, "urls.py": urls, "settings.py": ["MIDDLEWARE = ['django.middleware.csrf.CsrfViewMiddleware']"]})
        self.assertEqual([("v.py", 10, CSRF)], got)  # exempt: flagged despite the middleware; the other POST is covered; every cookie flag is set

    def test_spring_cookie_var_and_header(self):
        j = ["class C {", "    @GetMapping(\"/web/start\")", "    void start(HttpServletResponse resp) {", "        Cookie c = new Cookie(\"sid\", \"x\");", "        resp.addCookie(c);",
             "    }", "    @GetMapping(\"/web/ok\")", "    void ok(HttpServletResponse resp) {", "        Cookie c = new Cookie(\"sid\", \"x\");", "        c.setSecure(true);",
             "        c.setHttpOnly(true);", "        resp.addHeader(\"Set-Cookie\", c.getName() + \"=\" + c.getValue() + \"; Secure; HttpOnly; SameSite=Strict\");", "    }", "}"]
        self.assertEqual([("C.java", 5, FLAGS)], rows({"C.java": j}))

    def test_global_csrf_layer_and_public_routes_are_skipped(self):
        lib = ["const csurf = require('csurf');"]
        login = EXPRESS[:5] + ["router.post('/web/login', (req, res) => {", "  res.sendStatus(204);", "});"]
        self.assertEqual([("app.js", 3, FLAGS)], rows({"app.js": login}))
        self.assertFalse([r for r in rows({"app.js": EXPRESS, "lib.js": lib}) if r[2] == CSRF])

    def test_usage_and_wiring(self):
        p = subprocess.run([sys.executable, "-I", str(SK / "csrf_cookie_map.py")], capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stderr), (2, "usage: csrf_cookie_map.py DIR\n"))
        env = dict(os.environ, PATH="/usr/bin:/bin")
        with tempfile.TemporaryDirectory() as t:
            def repo(name, text):
                g = Path(t) / name
                g.mkdir()
                (g / "app.js").write_text(text, encoding="utf-8")
                for a in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@example.com", "-c", "user.name=Acme", "commit", "-qm", "fixture"]):
                    subprocess.run(["git", "-C", str(g), *a], check=True, capture_output=True, env=env)
                return g

            rc = SK / "review_checks.sh"
            r = subprocess.run(["bash", str(rc), "--full", "--repo", str(repo("g", "\n".join(EXPRESS) + "\n"))], capture_output=True, text=True, env=env)
            got = [(x["file"], x["line"], x["rule"]) for x in json.loads(r.stdout) if x["tool"] == "csrf-cookie"]
            self.assertEqual([("app.js", 3, FLAGS), ("app.js", 8, CSRF), ("app.js", 22, FLAGS)], sorted(got, key=lambda g: g[1]))
            r = subprocess.run(["bash", str(rc), "--full", "--repo", str(repo("g2", "export const a = 1;\n"))], capture_output=True, text=True, env=env)
            self.assertIn("csrf-cookie (SKIPPED: no HTTP handler or cookie)", r.stderr)


if __name__ == "__main__":
    unittest.main()
