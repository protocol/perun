"""cost_limit_map.py recall: PHP routes in the route_auth_map inventory (Symfony attribute and annotation, Laravel), a Go limiter attached to a different route is no cover, an LLM call
through a same-repo helper, and the `send` cost kind (email or SMS). Fixtures are fictional (acme, example.com); one new file per feature."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

SK = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts"
sys.path.insert(0, str(SK))
import cost_limit_map as C  # noqa: E402
import route_auth_map as R  # noqa: E402

MISS, EVID = "missing-cost-limit", "cost-limit-evidence"


def src(*lines):
    """A source file from its lines."""
    return "\n".join(lines) + "\n"


def repo(files):
    """(inventory [(METHOD, path, file, line)], cost rows [(file, line, rule, kind)], handlers) for a fresh temp repo."""
    with tempfile.TemporaryDirectory() as t:
        for rel, text in files.items():
            p = Path(t) / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        rs, n, _ = C.analyze(t)
        return R.inventory(t), [(f, ln, r, m.split(" ")[0]) for f, ln, r, m in rs], n


SYMFONY = src("<?php", "class PineController {", "    #[Route('/api/ext/pine/summarise', methods: ['POST'])]", "    public function summarise(Request $r) {",
              "        return $this->model->chat([['role' => 'user', 'content' => $r->get('t')]]);", "    }", "",
              "    #[Route('/api/ext/pine/list', methods: ['GET'])]", "    public function list() {", "        return [];", "    }", "}")
GO_ROUTES = src("package api", "", "func routes(rt chi.Router, bearer, limiter func(http.Handler) http.Handler) {",
                '\trt.With(bearer, limiter).Post("/api/x/render", func(w http.ResponseWriter, req *http.Request) {', '\t\taskModel(req.Context(), "render")', "\t})",
                '\trt.With(bearer).Post("/api/x/digest", func(w http.ResponseWriter, req *http.Request) {', '\t\taskModel(req.Context(), "digest")', "\t})",
                '\trt.With(bearer).Post("/api/x/invite", func(w http.ResponseWriter, req *http.Request) {', '\t\tpostJSON("https://mail.vendor.example.com/v1/send", nil)', "\t})",
                '\trt.With(bearer).Get("/api/x/list", func(w http.ResponseWriter, req *http.Request) {', '\t\tw.Write([]byte("[]"))', "\t})", "}", "",
                "func askModel(ctx context.Context, p string) string {", '\treturn postJSON("https://api.openai.com/v1/chat/completions", p)', "}")


class PhpRoutes(unittest.TestCase):
    def test_symfony_attribute_annotation_and_laravel_in_inventory(self):
        ann = src("<?php", "class AcmeController {", "    /**", "     * @Route(\"/api/acme/draft\", methods={\"POST\", \"PUT\"})", "     */", "    public function draft() {}", "}")
        lar = src("<?php", "Route::post('/api/acme/mail', [MailController::class, 'send']);", "Route::get('/api/acme/status', fn () => 'ok');")
        inv = repo({"src/Pine.php": SYMFONY, "src/Acme.php": ann, "routes/api.php": lar})[0]
        self.assertEqual([(m, p) for m, p, _, _ in inv], [("POST", "/api/acme/draft"), ("PUT", "/api/acme/draft"), ("POST", "/api/acme/mail"), ("GET", "/api/acme/status"),
                                                           ("GET", "/api/ext/pine/list"), ("POST", "/api/ext/pine/summarise")])

    def test_class_prefix(self):
        inv = repo({"src/A.php": src("<?php", "#[Route('/api/acme')]", "class A {", "    #[Route('/ping', methods: ['GET'])]", "    public function ping() {}", "}")})[0]
        self.assertEqual([(m, p) for m, p, _, _ in inv], [("GET", "/api/acme/ping")])

    def test_cost_limit_sees_the_php_llm_route_and_not_the_get(self):
        _, rows, n = repo({"src/Pine.php": SYMFONY})
        self.assertEqual((n, rows), (2, [("src/Pine.php", 3, MISS, "llm")]))

    def test_decoy_costly_helper_no_handler_calls(self):
        _, rows, n = repo({"src/Pine.php": src("<?php", "class P {", "    #[Route('/api/ok', methods: ['POST'])]", "    public function ok() { return 1; }", "}"),
                           "src/Helper.php": src("<?php", "class H {", "    public function ask($m) { return $this->model->chat($m); }", "}")})
        self.assertEqual((n, rows), (1, []))


class GoLimiterScope(unittest.TestCase):
    def test_limiter_on_a_different_route_is_no_cover(self):
        _, rows, _ = repo({"api/routes.go": GO_ROUTES})
        self.assertEqual([(ln, r) for _, ln, r, _ in rows], [(4, EVID), (7, MISS), (10, MISS)])

    def test_router_wide_use_still_covers(self):
        go = GO_ROUTES.replace("\trt.With(bearer).Post(\"/api/x/digest\"", "\trt.Use(limiter)\n\trt.With(bearer).Post(\"/api/x/digest\"", 1)
        self.assertTrue(all(r == EVID for _, _, r, _ in repo({"api/routes.go": go})[1]))

    def test_module_level_limiter_still_covers(self):
        go = GO_ROUTES.replace("func routes(", "var limiter = newLimiter()\n\nfunc routes(", 1).replace(", limiter func(http.Handler) http.Handler", "")
        self.assertTrue(all(r == EVID for _, _, r, _ in repo({"api/routes.go": go})[1]))

    def test_limiter_defined_in_another_file_and_only_attached_elsewhere(self):
        go = GO_ROUTES.replace(", limiter func(http.Handler) http.Handler", "")
        mw = src("package api", "", "func limiter(next http.Handler) http.Handler { return next }")
        _, rows, _ = repo({"api/routes.go": go, "api/mw.go": mw})
        self.assertEqual([(ln, r) for _, ln, r, _ in rows], [(4, EVID), (7, MISS), (10, MISS)])

    def test_other_language_limiter_is_no_cover(self):
        _, rows, _ = repo({"src/Pine.php": SYMFONY, "go/mw.go": "package x\n// limiter\nvar limiter = 1\n"})
        self.assertEqual([r for _, _, r, _ in rows], [MISS])


class WrapperAndSend(unittest.TestCase):
    def test_llm_helper_one_hop_and_send_kind(self):
        _, rows, _ = repo({"api/routes.go": GO_ROUTES.replace(", limiter func(http.Handler) http.Handler", "").replace("bearer, limiter", "bearer")})
        self.assertEqual([(ln, r, k) for _, ln, r, k in rows], [(4, MISS, "llm"), (7, MISS, "llm"), (10, MISS, "send")])

    def test_send_vendors(self):
        for body in ('await sgMail.send(m);', 'await transporter.sendMail(opts);', "const t = nodemailer.createTransport({});", '$mailer->send($m);', 'Mail::to($u)->send($m);',
                     'twilio.messages.create()', 'smtplib.SMTP("h").sendmail(a, b, c)', 'fetch("https://api.sms.vendor.example.com/send")'):
            self.assertIn("send", C.kinds(C.mask(body, True), "/x"), body)  # masked as production does: a comment word can't carry it

    def test_decoys(self):
        for body in ('res.send(data)', 'r.send(x)', 'res.json({ ok: true })', 'const sent = items.send;', 'fetch("https://api.example.com/v1/items")'):
            self.assertEqual(C.kinds(body, "/x"), [], body)
        _, rows, n = repo({"api/routes.go": src("package api", "func routes(rt chi.Router) {", '\trt.Post("/api/x/ok", func(w http.ResponseWriter, r *http.Request) {', '\t\tw.Write([]byte("ok"))', "\t})", "}", "",
                                                  "func askModel(p string) string {", '\treturn postJSON("https://api.openai.com/v1/chat/completions", p)', "}")})
        self.assertEqual((n, rows), (1, []))


class PhpPrefixScope(unittest.TestCase):
    def paths(self, *lines):
        return [(m, p) for m, p, _, _ in repo({"src/A.php": src("<?php", *lines)})[0]]

    def test_prefix_does_not_leak_to_next_class(self):
        got = self.paths("#[Route('/api')]", "class A {", "    #[Route('/x', methods: ['POST'])]", "    function x() {}", "}",
                         "class B {", "    #[Route('/y', methods: ['POST'])]", "    function y() {}", "}")
        self.assertEqual(got, [("POST", "/api/x"), ("POST", "/y")])

    def test_class_route_with_methods_is_still_a_prefix(self):
        got = self.paths("#[Route('/p', methods: ['GET'])]", "final class A {", "    #[Route('/x', methods: ['POST'])]", "    function x() {}", "}")
        self.assertEqual(got, [("POST", "/p/x")])

    def test_class_word_in_docblock_does_not_flip_a_handler(self):
        got = self.paths("class A {", "    /**", '     * @Route("/z")', "     * Not a class, a handler.", "     */", "    public function z() {}", "}")
        self.assertEqual(got, [("ANY", "/z")])
        got = self.paths("class A {", "    #[Route('/w', methods: ['GET'])]", "    #[IsGranted('x')]", "    public static function w() {}", "}", "// a class of its own")
        self.assertEqual(got, [("GET", "/w")])

    def test_class_word_in_comment_or_string_keeps_the_prefix(self):
        for mid in ("    /** Handles the class of admin requests */", "    // a class of its own", "    # a class note", "    private $s = 'the class of x';"):
            got = self.paths("#[Route('/api')]", "class A {", "    #[Route('/x', methods: ['POST'])]", "    function x() {}", mid,
                             "    #[Route('/z', methods: ['POST'])]", "    function z() {}", "}")
            self.assertEqual(got, [("POST", "/api/x"), ("POST", "/api/z")], mid)


if __name__ == "__main__":
    unittest.main()
