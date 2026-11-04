"""route_auth_map.py --all / --paths route inventory for Go, Spring and Django (synthetic, fictional snippets). One file per feature."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/route_auth_map.py"

FILES = {
    "go/main.go": '''package main
func routes(mux *http.ServeMux, r chi.Router, g *gin.Engine, gr *mux.Router) {
	mux.HandleFunc("GET /api/widgets/{id}", h)
	mux.HandleFunc("POST /api/widgets", h)
	http.HandleFunc("/healthz", h)
	// mux.HandleFunc("GET /commented", h)
	r.Get("/chi/items", h)
	r.Route("/v1", func(r chi.Router) {
		r.Post("/orders", h)
	})
	v := g.Group("/grp")
	v.DELETE("/things/:id", h)
	g.Any("/any", h)
	g.Handle("PUT", "/put-me", h)
	gr.HandleFunc("/gorilla/{k}", h).Methods("GET", "POST")
	resp, _ := client.Get("https://example.com/x")
}''',
    "go/main_test.go": 'mux.HandleFunc("GET /only-in-test", h)',
    "java/Shop.java": '''@RestController
@RequestMapping("/api/shop")
public class Shop {
    @GetMapping("/items/{id}") String a() {}
    @PostMapping(value = {"/x", "/y"}, produces = "text/plain") String b() {}
    @RequestMapping(path = "/old", method = RequestMethod.PUT) String c() {}
    @RequestMapping("/any") String d() { return ""; }
    @DeleteMapping String e() {}
}''',
    "dj/root/urls.py": '''from django.urls import path, include, re_path
urlpatterns = [
    path("home/", v.home),
    path("api/<int:pk>/detail", v.detail),
    path("blog/", include("dj.blog.urls")),
    re_path(r"^legacy/(?P<slug>[a-z]+)/$", v.legacy),
]''',
    "dj/blog/urls.py": '''urlpatterns = [
    path("posts/", v.posts),
    # path("dead/", v.dead),
]''',
    "js/app.js": 'const app = express();\napp.get("/js/ping", h);\napp.post("/js/save", h);\n',
}

WANT = {
    "GET /api/widgets/:id go/main.go:3", "POST /api/widgets go/main.go:4", "ANY /healthz go/main.go:5",
    "GET /chi/items go/main.go:7", "POST /v1/orders go/main.go:9", "DELETE /grp/things/:id go/main.go:12",
    "ANY /any go/main.go:13", "PUT /put-me go/main.go:14", "GET /gorilla/:k go/main.go:15", "POST /gorilla/:k go/main.go:15",
    "GET /api/shop/items/:id java/Shop.java:4", "POST /api/shop/x java/Shop.java:5", "POST /api/shop/y java/Shop.java:5",
    "PUT /api/shop/old java/Shop.java:6", "ANY /api/shop/any java/Shop.java:7", "DELETE /api/shop java/Shop.java:8",
    "ANY /home dj/root/urls.py:3", "ANY /api/:pk/detail dj/root/urls.py:4", "ANY /blog/posts dj/blog/urls.py:2",
    "ANY /legacy/:slug dj/root/urls.py:6", "GET /js/ping js/app.js:2", "POST /js/save js/app.js:3",
}


def run(root, flag):
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), flag, root], capture_output=True, text=True)
    return r.returncode, r.stdout.splitlines()


class RouteInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = tempfile.TemporaryDirectory()
        for rel, txt in FILES.items():
            p = Path(cls.t.name, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(txt)

    @classmethod
    def tearDownClass(cls):
        cls.t.cleanup()

    def test_all_lists_every_route(self):
        rc, out = run(self.t.name, "--all")
        self.assertEqual(rc, 0)
        self.assertEqual(set(out), WANT)
        self.assertEqual(len(out), len(WANT))  # no duplicates

    def test_paths_lists_get_and_any(self):
        rc, out = run(self.t.name, "--paths")
        self.assertEqual(rc, 0)
        want = sorted({l.split()[1] for l in WANT if l.split()[0] in ("GET", "ANY")})
        self.assertEqual(out, want)
        self.assertNotIn("/v1/orders", out)

    def test_flags_exclusive(self):
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), "--all", "--paths", self.t.name], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
