"""cost_limit_map.py / attempt_limit_map.py per-handler pass on Go, Spring, Django and Next re-exports: costly or sign-in handlers with no limiter of their own flagged, limited and
clamped ones silent, a limiter on another route no cover, a module-level one a cover, plus a held-out probe in fresh idioms (Go gin, Kotlin Spring). Fixtures are fictional (acme, example.com)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/deep-code-review/scripts"
sys.path.insert(0, str(SK))
import attempt_limit_map as A  # noqa: E402
import cost_limit_map as C  # noqa: E402


def lines(files, tool):
    """{(file, line)} of the missing-* rows `tool` (A or C) reports for a fresh temp repo of files {path: text}."""
    with tempfile.TemporaryDirectory() as t:
        for rel, text in files.items():
            p = Path(t) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        return {(f, ln) for f, ln, r, _ in tool.analyze(t)[0] if r.startswith("missing") or r == "unbounded-body"}


def at(text, needle):
    """1-based line of the first line of text that contains needle."""
    return next(i for i, x in enumerate(text.split("\n"), 1) if needle in x)


GO_MAIN = 'package main\nimport "net/http"\nfunc main() {\n\tmux := http.NewServeMux()\n\tmux.HandleFunc("/v1/ledger/export", exportLedger)\n\tmux.HandleFunc("/v1/blob", putBlob)\n\tmux.HandleFunc("/v1/rows", listRows)\n\tmux.HandleFunc("/auth/login", signIn)\n\tmux.HandleFunc("/auth/login-slow", signInSlow)\n}\n'
GO_H = '''package main

import ("io"; "net/http"; "strconv")

func exportLedger(w http.ResponseWriter, r *http.Request) {
	w.Write(dump())
}

func putBlob(w http.ResponseWriter, r *http.Request) {
	b, _ := io.ReadAll(r.Body)
	w.Write(b)
}

func listRows(w http.ResponseWriter, r *http.Request) {
	n, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if n > 50 {
		n = 50
	}
	w.Write(rows(n))
}

func signIn(w http.ResponseWriter, r *http.Request) {
	if r.FormValue("pass") != "x" {
		http.Error(w, "no", 401)
	}
}

func signInSlow(w http.ResponseWriter, r *http.Request) {
	if !allow(r.RemoteAddr) {
		http.Error(w, "slow", http.StatusTooManyRequests)
		return
	}
	_ = r.FormValue("pass")
}
'''
SPRING = '''package com.acme;

@RestController
class AcmeController {
    @GetMapping("/api/acme/orders/export")
    public String dump() { return all(); }

    @GetMapping("/api/acme/orders")
    public String page(@RequestParam int pageSize) { return rows(pageSize); }

    @GetMapping("/api/acme/orders/capped")
    public String capped(@RequestParam int pageSize) { return rows(Math.min(pageSize, 50)); }

    @PostMapping("/auth/login")
    public String login(@RequestParam String pass) { return pass; }

    @PostMapping("/auth/login-slow")
    public Object slow(@RequestParam String pass) {
        if (!allow(pass)) return ResponseEntity.status(429).build();
        return pass;
    }
}
'''
DJ_URLS = 'from django.urls import path\nfrom . import views\n\nurlpatterns = [\n    path("search-orders", views.find_orders),\n    path("orders-all", views.orders_all),\n    path("login", views.sign_in),\n    path("other", views.other),\n]\n'
DJ_VIEWS = '''from django.http import JsonResponse

def find_orders(request):
    return JsonResponse({})

def orders_all(request):
    return JsonResponse({"n": int(request.GET.get("limit", 0))})

def sign_in(request):
    return JsonResponse({"ok": request.POST.get("password") == "x"})

def other(request):
    if too_many(request):
        return JsonResponse({}, status=429)
'''
NEXT_ROUTE = "import { signIn } from '../../../lib/auth';\n\nexport const POST = signIn;\n"
NEXT_SLOW = "import { slow } from '../../../lib/auth';\n\nexport const POST = slow;\n"
NEXT_LIB = "export async function signIn(req: Request) {\n  const { password } = await req.json();\n  return Response.json({ ok: password === 'x' });\n}\n\nexport async function slow(req: Request) {\n  return new Response('no', { status: 429 });\n}\n"
EXPRESS_HELPER = '''const express = require('express');
const router = express.Router();
function throttle(max) {
  return (req, res, next) => (over(req, max) ? res.status(429).end() : next());
}
router.get('/all', (req, res) => { res.json({ take: Number(req.query.limit) }); });
router.post('/login', throttle(5), (req, res) => { res.json({ ok: req.body.password === 'x' }); });
'''
EXPRESS_GLOBAL = EXPRESS_HELPER.replace("const router = express.Router();", "const router = express.Router();\nrouter.use(throttle(100));")
GIN = '''package main

import "github.com/gin-gonic/gin"

func routes(r *gin.Engine, h *Handler) {
	r.POST("/api/v1/chat", h.Chat)
	r.GET("/api/v1/search", h.Find)
}

func (h *Handler) Chat(c *gin.Context) {
	c.JSON(200, h.llm.Ask(c.PostForm("prompt")))
}

func (h *Handler) Find(c *gin.Context) {
	c.JSON(200, h.db.Query(c.Query("q")))
}
'''
KOTLIN = '''package com.acme

@RestController
class StatsController {
    @GetMapping("/stats/export")
    fun csv(): String = dump()

    @GetMapping("/stats/list")
    fun list(@RequestParam pageSize: Int): String = rows(pageSize)

    @GetMapping("/stats/top")
    fun top(@RequestParam pageSize: Int): String = rows(minOf(pageSize, 20).coerceAtMost(20))
}
'''


class RateLimitHandlers(unittest.TestCase):
    def test_go(self):
        f = {"main.go": GO_MAIN, "handlers.go": GO_H}
        self.assertEqual(lines(f, C), {("handlers.go", at(GO_H, "func exportLedger")), ("handlers.go", at(GO_H, "func putBlob"))})
        self.assertEqual(lines(f, A), {("handlers.go", at(GO_H, "func signIn("))})

    def test_spring(self):
        f = {"src/AcmeController.java": SPRING}
        self.assertEqual({ln for _, ln in lines(f, C)}, {at(SPRING, '"/api/acme/orders/export"'), at(SPRING, '"/api/acme/orders")')})
        self.assertEqual({ln for _, ln in lines(f, A)}, {at(SPRING, '"/auth/login")')})

    def test_django(self):
        f = {"shop/urls.py": DJ_URLS, "shop/views.py": DJ_VIEWS}
        self.assertEqual(lines(f, C), {("shop/views.py", at(DJ_VIEWS, "def find_orders")), ("shop/views.py", at(DJ_VIEWS, "def orders_all"))})
        self.assertEqual(lines(f, A), {("shop/views.py", at(DJ_VIEWS, "def sign_in"))})

    def test_next_reexport_is_followed_to_the_function(self):
        f = {"app/auth/login-now/route.ts": NEXT_ROUTE, "app/auth/login-slow/route.ts": NEXT_SLOW, "lib/auth.ts": NEXT_LIB}
        self.assertEqual(lines(f, A), {("lib/auth.ts", at(NEXT_LIB, "function signIn"))})

    def test_helper_limiter_covers_only_the_routes_that_use_it(self):
        self.assertEqual({ln for _, ln in lines({"r.js": EXPRESS_HELPER}, C)}, {at(EXPRESS_HELPER, "'/all'")})
        self.assertEqual(lines({"r.js": EXPRESS_HELPER}, A), set())
        self.assertEqual(lines({"r.js": EXPRESS_GLOBAL}, C), set(), "a router-wide limiter covers every route")

    def test_held_out_probe_gin_and_kotlin(self):
        self.assertEqual({ln for _, ln in lines({"api.go": GIN}, C)}, {at(GIN, "func (h *Handler) Chat"), at(GIN, "func (h *Handler) Find")})
        self.assertEqual({ln for _, ln in lines({"src/Stats.kt": KOTLIN}, C)}, {at(KOTLIN, '"/stats/export"'), at(KOTLIN, '"/stats/list"')})


if __name__ == "__main__":
    unittest.main()
