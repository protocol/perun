"""cost_limit_map.py evidence binds to the route: an import or use line that only names a limiter library is no evidence, and a Go limiter mounted with `Use(...)` inside a
`Route(`/`Group(` closure covers only the routes registered in that closure. Fixtures are fictional (Acme, Pine); one new file per feature."""
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, __file__.rpartition("/")[0])
from test_cost_limit_recall import EVID, MISS, repo, src  # noqa: E402


def rules(files):
    """{(file, line): rule} of the cost rows of a fresh temp repo."""
    return {(f, ln): r for f, ln, r, _ in repo(files)[1]}


PHP_USE = ["<?php", "namespace Acme;", "use Symfony\\Component\\RateLimiter\\RateLimiterFactory;", "class PineController {"]
PHP_HEAD = ["    #[Route('/api/pine/ask', methods: ['POST'])]", "    public function ask(Request $r) {"]
JS_IMP = "import rateLimit from 'express-rate-limit';"
JS_ROUTE = ["app.post('/chat', async (req, res) => {", "  res.json(await openai.chat.completions.create({ model: 'm', messages: req.body.m }));", "});"]
GO_UTIL = src("package api", "", "func limit(next http.Handler) http.Handler {", "\treturn http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {",
              "\t\tif tooBusy(r) { http.Error(w, \"slow\", http.StatusTooManyRequests); return }", "\t\tnext.ServeHTTP(w, r)", "\t})", "}")


def go_routes(*body):
    """A Go routes.go with an Acme chi router: body lines inside func routes."""
    return src("package api", "", "func routes(rt chi.Router, bearer func(http.Handler) http.Handler) {", *body, "}")


GROUP = ['\trt.Route("/a", func(g chi.Router) {', "\t\tg.Use(bearer, limit)", '\t\tg.Post("/x", func(w http.ResponseWriter, r *http.Request) { postJSON("https://api.openai.com/v1/chat/completions", "") })', "\t})"]
OUTSIDE = ['\trt.With(bearer).Post("/b", func(w http.ResponseWriter, r *http.Request) { postJSON("https://api.openai.com/v1/chat/completions", "") })']


class ImportIsNotEvidence(unittest.TestCase):
    def test_php_use_line_only_is_missing(self):
        f = src(*PHP_USE, *PHP_HEAD, "        return $this->model->chat([['role' => 'user', 'content' => $r->get('t')]]);", "    }", "}")
        self.assertEqual(rules({"src/A.php": f}), {("src/A.php", 5): MISS})

    def test_php_limiter_in_the_handler_body_is_evidence(self):
        f = src(*PHP_USE, *PHP_HEAD, "        $this->pineLimiter->create($r->getClientIp())->consume();",
                "        return $this->model->chat([['role' => 'user', 'content' => $r->get('t')]]);", "    }", "}")
        self.assertEqual(rules({"src/B.php": f}), {("src/B.php", 5): EVID})

    def test_js_import_never_used_is_missing_and_use_is_evidence(self):
        self.assertEqual(list(rules({"index.js": src(JS_IMP, "const app = require('express')();", *JS_ROUTE)}).values()), [MISS])
        used = src(JS_IMP, "const app = require('express')();", "app.use(rateLimit({ windowMs: 60000, max: 5 }));", *JS_ROUTE)
        self.assertEqual(list(rules({"index.js": used}).values()), [EVID])

    def test_js_import_statement_and_php_use_with_other_imports_are_missing(self):
        self.assertEqual(list(rules({"index.js": src(JS_IMP, "const app = require('express')();", *JS_ROUTE)}).values()), [MISS])
        f = src("<?php", "use Symfony\\Component\\RateLimiter\\RateLimiterFactory;", "use Acme\\Pine;", "class P {", *PHP_HEAD, "        return $this->model->chat([]);", "    }", "}")
        self.assertEqual(list(rules({"src/P.php": f}).values()), [MISS])

    def test_js_require_and_python_import_only_are_missing(self):
        self.assertEqual(list(rules({"index.js": src("const rateLimit = require('express-rate-limit');", "const app = require('express')();", *JS_ROUTE)}).values()), [MISS])
        py = src("from slowapi import Limiter", "import slowapi.util", "from fastapi import FastAPI", "app = FastAPI()", "", '@app.post("/chat")',
                 "async def chat(req):", "    return await client.chat.completions.create(model='m', messages=req.m)")
        self.assertEqual(list(rules({"app.py": py}).values()), [MISS])


class GroupMiddlewareBinds(unittest.TestCase):
    def test_group_use_covers_only_its_routes(self):
        r = rules({"routes.go": go_routes(*GROUP, *OUTSIDE), "util.go": GO_UTIL})
        self.assertEqual(sorted(r.values()), [EVID, MISS])
        self.assertEqual(r[("routes.go", 6)], EVID)
        self.assertEqual(r[("routes.go", 8)], MISS)

    def test_root_use_still_covers_both(self):
        r = rules({"routes.go": go_routes("\trt.Use(limit)", *GROUP[:1], *GROUP[2:], *OUTSIDE), "util.go": GO_UTIL})
        self.assertEqual(sorted(r.values()), [EVID, EVID])


class DeclarationIsNotApplication(unittest.TestCase):
    def test_php_injected_limiter_covers_only_the_handler_that_uses_it(self):
        f = src("<?php", "use Symfony\\Component\\RateLimiter\\RateLimiterFactory;", "class PineController {",
                "    public function __construct(private RateLimiterFactory $pineLimiter, private $model) {}",
                "    #[Route('/api/pine/a', methods: ['POST'])]", "    public function a(Request $r) {", "        $this->pineLimiter->create($r->getClientIp())->consume();",
                "        return $this->model->chat([['role' => 'user', 'content' => $r->get('t')]]);", "    }",
                "    #[Route('/api/pine/b', methods: ['POST'])]", "    public function b(Request $r) {",
                "        return $this->model->chat([['role' => 'user', 'content' => $r->get('t')]]);", "    }", "}")
        self.assertEqual(rules({"src/C.php": f}), {("src/C.php", 5): EVID, ("src/C.php", 10): MISS})

    def test_php_rate_limit_attribute_on_the_handler_is_evidence(self):
        f = src("<?php", "class PineController {", "    #[Route('/api/pine/a', methods: ['POST'])]", "    #[RateLimit('pine')]", "    public function a(Request $r) {",
                "        return $this->model->chat([['role' => 'user', 'content' => $r->get('t')]]);", "    }", "}")
        self.assertEqual(list(rules({"src/D.php": f}).values()), [EVID])


THROTTLE = src("package api", "", "func throttle(w *window) func(http.Handler) http.Handler {", "	return func(next http.Handler) http.Handler {",
               "		return http.HandlerFunc(func(rw http.ResponseWriter, r *http.Request) {", '			if w.full() { http.Error(rw, "too many requests", http.StatusTooManyRequests); return }',
               "			next.ServeHTTP(rw, r)", "		})", "	}", "}", "", "var limit = throttle(newWindow(60, time.Minute))")


class AliasHop(unittest.TestCase):
    def test_alias_of_a_limiter_func_binds_to_the_group(self):
        r = rules({"routes.go": go_routes(*GROUP, *OUTSIDE), "util.go": THROTTLE})
        self.assertEqual((r[("routes.go", 6)], r[("routes.go", 8)]), (EVID, MISS))

    def test_root_use_of_the_alias_covers_both(self):
        r = rules({"routes.go": go_routes("\trt.Use(limit)", *GROUP[:1], *GROUP[2:], *OUTSIDE), "util.go": THROTTLE})
        self.assertEqual(sorted(r.values()), [EVID, EVID])


VARBLOCK = THROTTLE.rsplit("\n\n", 1)[0] + "\n\nvar (\n\tlimit = throttle(newWindow(60, time.Minute))\n\tloginLimit = throttle(newWindow(8, 10*time.Minute))\n)\n"
AUTH = ['\trt.With(loginLimit).Post("/auth/x", func(w http.ResponseWriter, r *http.Request) { postJSON("https://api.openai.com/v1/chat/completions", "") })']


class OnlyScopedUses(unittest.TestCase):
    def test_var_block_aliases_each_bind_to_their_own_routes(self):
        r = rules({"routes.go": go_routes(*GROUP, *AUTH, *OUTSIDE), "util.go": VARBLOCK})
        self.assertEqual([r[("routes.go", n)] for n in (6, 8, 9)], [EVID, EVID, MISS])

    def test_root_use_makes_all_three_covered(self):
        r = rules({"routes.go": go_routes("\trt.Use(limit)", *GROUP[:1], *GROUP[2:], *AUTH, *OUTSIDE), "util.go": VARBLOCK})
        self.assertEqual(sorted(r.values()), [EVID, EVID, EVID])


LLMCALL = 'postJSON("https://api.openai.com/v1/chat/completions", "")'
LIMITER = src("package api", "", "func limiter() gin.HandlerFunc {", "\treturn func(c *gin.Context) { if busy(c) { c.AbortWithStatus(http.StatusTooManyRequests) } }", "}")


def gin_routes(*body):
    """A Go routes.go with an Acme gin engine: body lines inside func routes."""
    return src("package api", "", "func routes(r *gin.Engine) {", *body, "}")


GIN_GROUP = ["\tv1 := r.Group(\"/v1\")", "\tv1.Use(limiter())", '\tv1.POST("/chat", func(c *gin.Context) { %s })' % LLMCALL]
GIN_SUB = ["\tv1 := r.Group(\"/v1\")", "\tv1.Use(limiter())", "\tv2 := v1.Group(\"/x\")", '\tv2.POST("/chat", func(c *gin.Context) { %s })' % LLMCALL]
GIN_ROOT = ['\tr.POST("/pine/upload", func(c *gin.Context) { %s })' % LLMCALL]


class VariableGroups(unittest.TestCase):
    def test_gin_group_variable_use_covers_only_its_routes(self):
        r = rules({"routes.go": gin_routes(*GIN_GROUP, *GIN_ROOT), "util.go": LIMITER})
        self.assertEqual([r[("routes.go", 6)], r[("routes.go", 7)]], [EVID, MISS])

    def test_sub_group_is_covered_and_root_use_covers_all(self):
        r = rules({"routes.go": gin_routes(*GIN_SUB, *GIN_ROOT), "util.go": LIMITER})
        self.assertEqual([r[("routes.go", 7)], r[("routes.go", 8)]], [EVID, MISS])
        r = rules({"routes.go": gin_routes("\tr.Use(limiter())", *GIN_GROUP[:1], *GIN_GROUP[2:], *GIN_ROOT), "util.go": LIMITER})
        self.assertEqual(sorted(r.values()), [EVID, EVID])


if __name__ == "__main__":
    unittest.main()
