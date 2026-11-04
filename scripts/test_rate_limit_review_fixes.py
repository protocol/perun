"""Regression tests for review fixes to the per-handler rate-limit pass: a decorator above the next handler does not cover this one, a status comparison is not a page-size cap, a
registration line covers only the handler it registers, `.get_data()` must be on `request`, and a bare `size` parameter is not a page size. Fixtures are fictional."""
import unittest

from test_rate_limit_handlers import A, C, at, lines

FLASK = '''from flask import Flask, request
app = Flask(__name__)

@app.route("/auth/login", methods=["POST"])
def login():
    return check(request.form["password"])

@limiter.limit("5/minute")
@app.route("/items")
def items():
    return all_items()
'''


class ReviewFixes(unittest.TestCase):
    def test_decorator_of_next_handler_does_not_cover(self):
        self.assertEqual(lines({"app.py": FLASK}, A), {("app.py", at(FLASK, "/auth/login"))})

    def test_status_comparison_is_not_a_cap(self):
        src = 'from flask import request\n@app.route("/v1/rows")\ndef rows():\n    n = int(request.args["limit"])\n    if resp.status >= 10:\n        return rows_all(n)\n    return rows_all(n)\n'
        self.assertEqual(lines({"app.py": src}, C), {("app.py", at(src, "/v1/rows"))})
        ok = src.replace("resp.status >= 10", "n > 100")
        self.assertEqual(lines({"app.py": ok}, C), set())

    def test_registration_line_covers_only_its_handler(self):
        main = 'package main\nimport "net/http"\nfunc main() {\n\tmux := http.NewServeMux()\n\tmux.HandleFunc("/v1/rows", rateLimit(listRows))\n\tmux.HandleFunc("/v1/blob", putBlob)\n}\n'
        h = 'package main\nimport ("io"; "net/http")\nfunc listRows(w http.ResponseWriter, r *http.Request) {\n\tr.FormValue("limit")\n}\nfunc putBlob(w http.ResponseWriter, r *http.Request) {\n\tio.ReadAll(r.Body)\n}\n'
        got = lines({"main.go": main, "h.go": h}, C)
        self.assertIn(("h.go", at(h, "func putBlob")), got)
        self.assertNotIn(("h.go", at(h, "func listRows")), got)

    def test_get_data_needs_request_receiver(self):
        src = 'from flask import request\n@app.route("/v1/misc")\ndef misc():\n    return cache.get_data("k")\n'
        self.assertEqual(lines({"app.py": src}, C), set())

    def test_unused_size_param_is_not_page_size(self):
        src = 'package acme\n@RestController\nclass Rows {\n    @GetMapping("/v1/rows")\n    fun list(@RequestParam size: Int): String = rows()\n}\n'
        self.assertEqual(lines({"Rows.kt": src}, C), set())

    def test_blank_comment_and_multiline_decorator_lines_stay_with_next_handler(self):
        for gap in ("\n# note\n\n", "\n"):
            src = FLASK.replace('@limiter.limit("5/minute")\n@app', '@limiter.limit("5/minute")' + gap + '@app')
            self.assertEqual(lines({"app.py": src}, A), {("app.py", at(src, "/auth/login"))})
        src = FLASK.replace('@limiter.limit("5/minute")', '@limiter.limit(\n    "5/minute",\n    key_func=who,\n)')
        self.assertEqual(lines({"app.py": src}, A), {("app.py", at(src, "/auth/login"))})

    def test_floor_check_is_not_a_cap(self):
        src = 'from flask import request\n@app.route("/v1/rows")\ndef rows():\n    n = int(request.args["limit"])\n    if n < 1:\n        n = 1\n    return rows_all(n)\n'
        self.assertEqual(lines({"app.py": src}, C), {("app.py", at(src, "/v1/rows"))})
        self.assertEqual(lines({"app.py": src.replace("n < 1", "100 < n")}, C), set())
        for floor in ("n > 0", "n >= 1", "0 < n", "1 <= n"):
            self.assertEqual(lines({"app.py": src.replace("n < 1", floor)}, C), {("app.py", at(src, "/v1/rows"))}, floor)
        for cap in ("n <= 100", "n < 100", "100 >= n", "n > 100"):
            self.assertEqual(lines({"app.py": src.replace("n < 1", cap)}, C), set(), cap)

    def test_size_param_used_in_body_is_page_size(self):
        used = 'package acme\n@RestController\nclass Rows {\n    @GetMapping("/v1/rows")\n    fun list(@RequestParam size: Int): String = rows(size)\n}\n'
        self.assertEqual(lines({"Rows.kt": used}, C), {("Rows.kt", at(used, "/v1/rows"))})
        self.assertEqual(lines({"Rows.kt": used.replace("rows(size)", "rows()")}, C), set())
        named = used.replace("@RequestParam size: Int): String = rows(size)", '@RequestParam(name = "size", defaultValue = "10") size: Int): String = rows()')
        self.assertEqual(lines({"Rows.kt": named}, C), set())
        prop = used.replace("@RequestParam size: Int): String = rows(size)", "@RequestParam size: Int = items().size): String = rows()")
        self.assertEqual(lines({"Rows.kt": prop}, C), set())


if __name__ == "__main__":
    unittest.main()
