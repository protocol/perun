"""csrf_cookie_map.py round-2 fixes: an Origin compare against undefined/null is no defence, only session-named cookies give SameSite cover, two path() calls on one line
each map to their own view, a commented-out csrf disable does not count, and a dense one-line Spring class anchors the lead on the right handler. Fictional fixtures.
DCR_SCRIPTS=<dir> runs the checks against another copy of the scripts (used to prove each check fails before the fix)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_csrf_cookie_review import CHAIN, CSRF, rows, rules  # noqa: E402
import attempt_limit_map as A  # noqa: E402


class Round2(unittest.TestCase):
    def test_origin_compared_with_undefined_or_null_is_no_defence(self):
        h = "app.post('/api/pay',(req,res)=>{ %s res.json({}); });\napp.get('/api/s',(req,res)=>{ res.cookie('sid', s, opts); res.json({}); });\n"
        for bad in ("if (req.headers.origin !== undefined) ok();", "if (req.headers.origin === null) no();"):
            self.assertEqual(len(rules({"a.js": h % bad}, CSRF)), 1, bad)
        self.assertEqual(rules({"a.js": h % "if (req.headers.origin !== 'https://app.example.com') return;"}, CSRF), [])
        self.assertEqual(rules({"a.js": h % "if (!ALLOWED.includes(req.headers.origin)) return;"}, CSRF), [])

    def test_samesite_cover_needs_a_session_named_cookie(self):
        js = ("app.get('/p',(req,res)=>{ res.cookie('theme','x',{ sameSite: 'lax' }); res.json({}); });\n"
              "app.post('/api/a',(req,res)=>{ const s = req.cookies.sid; db.save(s); res.json({}); });\n")
        self.assertEqual(len(rules({"a.js": js}, CSRF)), 1)
        self.assertEqual(rules({"a.js": js.replace("'theme'", "'sid'").replace("{ sameSite: 'lax' }", "{ secure: true, httpOnly: true, sameSite: 'lax' }")}, CSRF), [])

    def test_two_path_calls_on_one_line_map_to_their_own_view(self):
        with tempfile.TemporaryDirectory() as t:
            Path(t, "urls.py").write_text("urlpatterns=[path('pay/',views.pay), path('o/',views.other)]\n")
            Path(t, "views.py").write_text("def pay(request):\n    return 1\n\ndef other(request):\n    return 2\n")
            got = {u[3]: u[0] for u in A.units(t, {}, True)["views.py"]}
        self.assertEqual(got, {"/pay": 1, "/o": 4})

    def test_commented_disable_does_not_remove_the_cover(self):
        ctrl = '@RestController class C { @PostMapping("/x") public String x(HttpSession s){ s.setAttribute("a",1); return "ok"; } }\n'
        files = {"A.java": "// http.csrf(c -> c.disable());\n" + CHAIN % "Customizer.withDefaults()", "B.java": ctrl}
        self.assertEqual(rules(files, CSRF), [])

    def test_dense_spring_class_anchors_on_the_third_handler(self):
        j = ('@RestController class C {\n'
             ' @PostMapping("/a") public String a(HttpSession s){ s.setAttribute("a",1); return http.csrf(); }\n'
             ' @PostMapping("/b") public String b(HttpSession s){ s.setAttribute("b",1); return csrfOk(); }\n'
             ' @PostMapping("/c") public String c(HttpServletRequest r){ r.getSession(); r.getHeader("Origin"); return "ok"; }\n}\n')
        with tempfile.TemporaryDirectory() as t:
            Path(t, "C.java").write_text(j)
            got = [(r[1], r[3]) for r in __import__("csrf_cookie_map").analyze(t)[0]]
        self.assertEqual([(ln, "/c" in m) for ln, m in got], [(4, True)])

    def test_multiline_annotation_with_open_brace_stays_in_its_handler(self):
        for ann, first in (('@RolesAllowed({\n    "A","B"})', 3), ('@ApiResponses(value = {\n    @ApiResponse(code = 200)\n})', 3)):
            j = ('@RestController class C {\n @PostMapping("/one") public String one(){ return "1"; }\n %s\n @PostMapping("/doc") public String doc(){ return "2"; }\n}\n') % ann
            with tempfile.TemporaryDirectory() as t:
                Path(t, "C.java").write_text(j)
                us = A.units(t, {}, True)["C.java"]
            by = {u[3]: u for u in us}
            self.assertEqual(by["/doc"][0], 3, ann)
            self.assertEqual(by["/one"][1], 2, ann)


if __name__ == "__main__":
    unittest.main()
