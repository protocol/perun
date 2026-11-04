"""csrf_cookie_map.py review fixes: Spring csrf disable beats the security cover, Django csrf_exempt without a method check is a POST, an unchecked Origin read is no defence,
only session-named cookies make a cookie realm, csrf-named or variable-option cookies get no flags row, and an all-SameSite session cookie set covers CSRF. Fictional fixtures.
DCR_SCRIPTS=<dir> runs the same checks against another copy of the scripts (used to prove each check fails before the fix)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
SK = Path(os.environ.get("DCR_SCRIPTS") or Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts")
sys.path.insert(0, str(SK))
import csrf_cookie_map as C  # noqa: E402

CSRF, FLAGS = "missing-csrf-protection", "missing-cookie-flags"


def rows(files):
    """(file, line, rule) rows for a fresh temp repo built from {relative path: text}."""
    with tempfile.TemporaryDirectory() as t:
        for rel, text in files.items():
            p = Path(t) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        return [(f, ln, r) for f, ln, r, _ in C.analyze(t)[0]]


def rules(files, rule):
    return [r for r in rows(files) if r[2] == rule]


CTRL = '@RestController class C { @PostMapping("/x") public String x(HttpSession s){ s.setAttribute("a",1); return "ok"; } }\n'
CHAIN = "@Configuration class S { @Bean SecurityFilterChain f(HttpSecurity http) throws Exception { http.csrf(%s); return http.build(); } }\n"


class Review(unittest.TestCase):
    def test_spring_disable_lambda_and_method_ref_beat_cover_in_any_file_order(self):
        for arg in ("c -> c.disable()", "AbstractHttpConfigurer::disable"):
            for first, second in (("A.java", "B.java"), ("B.java", "A.java")):
                files = {first: CHAIN % arg, second: CTRL, "pom.xml": "<artifactId>spring-boot-starter-security</artifactId>\n"}
                self.assertEqual(len(rules(files, CSRF)), 1, (arg, first))

    def test_spring_security_without_disable_still_covers(self):
        self.assertEqual(rules({"A.java": CHAIN % "Customizer.withDefaults()", "B.java": CTRL}, CSRF), [])

    def test_pom_marker_alone_is_no_cover(self):
        self.assertEqual(len(rules({"B.java": CTRL, "pom.xml": "<artifactId>spring-boot-starter-security</artifactId>\n"}, CSRF)), 1)

    def test_django_csrf_exempt_any_method_counts_as_post(self):
        files = {"settings.py": "MIDDLEWARE=['django.middleware.csrf.CsrfViewMiddleware']\n", "urls.py": "from . import views\nurlpatterns=[path('pay/', views.pay)]\n",
                 "views.py": "@csrf_exempt\ndef pay(request):\n    request.session['a']=1\n    return None\n"}
        self.assertEqual(len(rules(files, CSRF)), 1)

    def test_origin_read_without_compare_is_flagged_and_compare_is_a_defence(self):
        head = "app.post('/api/pay',(req,res)=>{ %s res.json({}); });\napp.get('/api/s',(req,res)=>{ res.cookie('sid', s, opts); res.json({}); });\n"
        self.assertEqual(len(rules({"a.js": head % "const o=req.headers.origin;"}, CSRF)), 1)
        self.assertEqual(rules({"a.js": head % "if (req.headers.origin !== HOST) return res.sendStatus(403);"}, CSRF), [])

    def test_theme_cookie_makes_no_realm(self):
        js = "app.post('/api/prefs',(req,res)=>{ res.cookie('theme','x'); res.json({}); });\napp.post('/api/items',(req,res)=>{ db.save(req.body); res.json({}); });\n"
        self.assertEqual(rules({"a.js": js}, CSRF), [])
        self.assertEqual(len(rules({"a.js": js.replace("'theme'", "'sid'")}, CSRF)), 2)

    def test_csrf_named_and_variable_option_cookies_get_no_flags_row(self):
        js = "app.get('/c',(req,res)=>{ res.cookie('csrf-token', t); res.cookie('sid', s, opts); res.cookie('sid', s, {...base}); res.json({}); });\n"
        self.assertEqual(rules({"a.js": js}, FLAGS), [])
        self.assertEqual(len(rules({"a.js": "app.get('/c',(req,res)=>{ res.cookie('sid', s); res.json({}); });\n"}, FLAGS)), 1)

    def test_samesite_on_every_session_cookie_covers_csrf_but_one_lax_gap_does_not(self):
        h = "app.post('/api/a',(req,res)=>{ db.save(1); res.json({}); });\napp.get('/api/l',(req,res)=>{ res.cookie('sid', s, { secure: true, httpOnly: true, sameSite: 'strict' });%s res.json({}); });\n"
        self.assertEqual(rules({"a.js": h % ""}, CSRF), [])
        self.assertEqual(len(rules({"a.js": h % " res.cookie('admin_sid', s, { secure: true });"}, CSRF)), 1)


if __name__ == "__main__":
    unittest.main()
