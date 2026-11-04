"""route_auth_map.py --all edge cases (synthetic, fictional): Spring per-class prefix and constants, Go scoped groups / chains / outbound calls, Django nested groups and include cycles."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/route_auth_map.py"


def routes(files):
    with tempfile.TemporaryDirectory() as t:
        for rel, txt in files.items():
            p = Path(t, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(txt)
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--all", t], capture_output=True, text=True)
    return {" ".join(l.split()[:2]) for l in r.stdout.splitlines()}


class Edge(unittest.TestCase):
    def test_spring_prefix_resets_per_class(self):
        got = routes({"A.java": '''@RequestMapping("/api")
class A { @GetMapping("/a") String a() {} }
class D { @GetMapping("/d") String d() {} }'''})
        self.assertEqual(got, {"GET /api/a", "GET /d"})

    def test_spring_name_and_constants(self):
        got = routes({"B.java": '''class B {
  @GetMapping(name = "listing", value = "/n") String a() {}
  @GetMapping(value = BASE + "/k") String b() {}
  @PostMapping(PATH) String c() {}
}'''})
        self.assertEqual(got, {"GET /n", "GET /{?}/k", "POST /{?}"})

    def test_go_group_scoped_per_func(self):
        got = routes({"a.go": '''package a
func one(g *gin.Engine) {
	v := g.Group("/one")
	v.GET("/x", h)
}
func two(g *gin.Engine) {
	v := g.Group("/two")
	v.GET("/y", h)
}
func three(v *gin.Engine) {
	v.GET("/z", h)
}'''})
        self.assertEqual(got, {"GET /one/x", "GET /two/y", "GET /z"})

    def test_go_chains_clients_mount(self):
        got = routes({"b.go": '''package b
func f(r chi.Router, g *gin.Engine, client *resty.Client) {
	r.With(mw).Get("/with", h)
	g.Group("/inline").POST("/p", h)
	client.Post("/outbound", "application/json", body)
	httpc.Get("/also-outbound")
	r.Mount("/m", func(r chi.Router) {
		r.Put("/inner", h)
	})
}'''})
        self.assertEqual(got, {"GET /with", "POST /inline/p", "PUT /m/inner"})

    def test_django_nested_group_and_cycle(self):
        got = routes({
            "p/urls.py": 'urlpatterns = [re_path(r"^id/(?P<id>(\\d+))/$", v.a), path("b/", include("p.q.urls"))]',
            "p/q/urls.py": 'urlpatterns = [path("x/", v.x), path("back/", include("p.q.urls2"))]',
            "p/q/urls2.py": 'urlpatterns = [path("y/", v.y), path("loop/", include("p.q.urls"))]',
            "p/other.py": 'x = 1',
        })
        self.assertEqual(got, {"ANY /id/:id", "ANY /b/x", "ANY /b/back/y"})

    def test_django_pure_cycle_still_read(self):
        got = routes({"a/urls.py": 'urlpatterns = [path("a/", v.a), path("n/", include("b.urls"))]',
                      "b/urls.py": 'urlpatterns = [path("b/", v.b), path("n/", include("a.urls"))]'})
        self.assertIn("ANY /a", got)
        self.assertTrue(any(g.endswith("/b") for g in got))

    def test_kotlin_tests_skipped(self):
        self.assertEqual(routes({"CTest.kt": '@GetMapping("/t") fun t() {}', "CTests.kt": '@GetMapping("/t2") fun t() {}'}), set())

    def test_spring_quoted_arrays_and_braces(self):
        got = routes({"C.kt": '''class C {
  @GetMapping(path = ["/a", "/b"]) fun a() {}
  @GetMapping(value = {"/x/{id}", "/y"}) String b() {}
  @GetMapping("/z/{id:\\\\d{1,3}}") String c() {}
}'''})
        self.assertEqual({g for g in got if "{?}" in g}, set())
        self.assertTrue({"GET /a", "GET /b", "GET /x/:id", "GET /y"} <= got)

    def test_go_gorilla_methods(self):
        self.assertEqual(routes({"g.go": 'package g\nfunc f(r *mux.Router) {\n\tr.PathPrefix("/p").Subrouter().HandleFunc("/m", h).Methods("POST")\n}'}), {"POST /p/m"})

    def test_go_router_named_like_client(self):
        self.assertEqual(routes({"h.go": 'package h\nfunc f(httpRouter *gin.Engine) {\n\thttpRouter.GET("/r", h)\n}'}), {"GET /r"})


if __name__ == "__main__":
    unittest.main()
