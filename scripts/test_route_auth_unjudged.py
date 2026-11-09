"""route_auth_map.py UNJUDGED rows: a Go file with state-changing routes (gorilla .Methods(http.MethodPost), net/http HandleFunc with no method = ANY)
gets one not-checked lead per file, a GET-only Go file none, a JS-only repo none, and an empty repo SKIPPED in review_checks.sh --full. Fictional fixtures."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/deep-code-review/scripts"
SCRIPT = SK / "route_auth_map.py"
RC = SK / "review_checks.sh"

GO = '''package main

import (
\t"net/http"

\t"github.com/gorilla/mux"
)

func register(r *mux.Router) {
\tr.HandleFunc("/widgets", createWidget).Methods(http.MethodPost)
\tr.HandleFunc("/widgets/{id}", updateWidget).Methods("PUT")
\tr.HandleFunc("/widgets/{id}", getWidget).Methods(http.MethodGet)
}

func plain() {
\thttp.HandleFunc("/health", health)
}
'''
GO_GET = 'package main\n\nimport "net/http"\n\nfunc register(r *mux.Router) {\n\tr.HandleFunc("/widgets/{id}", getWidget).Methods(http.MethodGet)\n}\n'
JS = {"app/api/notes/route.ts": 'export async function POST(req: Request) {\n  return Response.json({ ok: true });\n}\n'}
ENV = dict(os.environ, PATH="/usr/bin:/bin")


def write(root, files):
    for k, v in files.items():
        p = Path(root, k)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v)


def run_map(files):
    with tempfile.TemporaryDirectory() as d:
        write(d, files)
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), d], capture_output=True, text=True, env=ENV)
    lines = r.stdout.splitlines()
    return r.returncode, [x for x in lines if ": UNJUDGED: " in x], json.loads(lines[-1])


class T(unittest.TestCase):
    def test_go_state_changing_routes_get_one_row_per_file(self):
        rc, rows, js = run_map({"svc/main.go": GO})
        self.assertEqual(rc, 0)
        self.assertEqual(rows, ["svc/main.go:10: UNJUDGED: 3 route(s) accept state-changing methods here (first POST /widgets); route-auth does not judge auth for this language, read the handlers"])
        self.assertEqual((js["handlers"], js["unjudged"], js["high"]), (0, 3, 0))

    def test_django_urlconf_gets_one_row(self):
        urls = 'from django.urls import path\nfrom . import views\n\nurlpatterns = [\n    path("widgets/", views.widgets),\n]\n'
        rc, rows, js = run_map({"shop/urls.py": urls})
        self.assertEqual(rows, ["shop/urls.py:5: UNJUDGED: 1 route(s) accept state-changing methods here (first ANY /widgets); route-auth does not judge auth for this language, read the handlers"])
        self.assertEqual((js["handlers"], js["unjudged"]), (0, 1))

    def test_go_get_only_has_no_row(self):
        rc, rows, js = run_map({"svc/main.go": GO_GET})
        self.assertEqual((rows, js["unjudged"]), ([], 0))

    def test_js_only_repo_has_no_unjudged_row(self):
        rc, rows, js = run_map(JS)
        self.assertEqual((rows, js["unjudged"], js["handlers"]), ([], 0, 1))

    def test_empty_repo_is_skipped_in_review_checks(self):
        rc, rows, js = run_map({"README.md": "# Acme\n"})
        self.assertEqual((rows, js["unjudged"], js["handlers"]), ([], 0, 0))
        with tempfile.TemporaryDirectory() as t:
            g = Path(t) / "e"
            write(g, {"README.md": "# Acme\n"})
            for a in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@example.com", "-c", "user.name=Acme", "commit", "-qm", "fixture"]):
                subprocess.run(["git", "-C", str(g), *a], check=True, capture_output=True, env=ENV)
            r = subprocess.run(["bash", str(RC), "--full", "--repo", str(g)], capture_output=True, text=True, env=ENV)
        self.assertIn("route-auth (SKIPPED: no HTTP handlers)", r.stderr)
        self.assertEqual([x["message"] for x in json.loads(r.stdout) if x["tool"] == "route-auth"], ["SKIPPED: no HTTP handlers"])

    def test_options_or_head_only_go_route_has_no_row(self):
        for verbs in ('"OPTIONS"', '"GET","OPTIONS"', '"HEAD"', 'http.MethodOptions'):
            src = 'package main\n\nfunc register(r *mux.Router) {\n\tr.HandleFunc("/widgets", h).Methods(%s)\n}\n' % verbs
            rc, rows, js = run_map({"svc/main.go": src})
            self.assertEqual((rows, js["unjudged"]), ([], 0), verbs)

    def test_options_beside_post_counts_only_the_post(self):
        src = 'package main\n\nfunc register(r *mux.Router) {\n\tr.HandleFunc("/widgets", h).Methods("OPTIONS", "POST")\n}\n'
        rc, rows, js = run_map({"svc/main.go": src})
        self.assertEqual(rows, ["svc/main.go:4: UNJUDGED: 1 route(s) accept state-changing methods here (first POST /widgets); route-auth does not judge auth for this language, read the handlers"])

    def test_chained_call_before_methods_is_read(self):
        src = 'package main\n\nfunc register(r *mux.Router) {\n\tr.HandleFunc("/widgets", h).Name("x").Methods("POST")\n}\n'
        rc, rows, js = run_map({"svc/main.go": src})
        self.assertEqual(rows, ["svc/main.go:4: UNJUDGED: 1 route(s) accept state-changing methods here (first POST /widgets); route-auth does not judge auth for this language, read the handlers"])

    def test_review_checks_full_wires_go_row_as_not_checked(self):
        with tempfile.TemporaryDirectory() as t:
            g = Path(t) / "go"
            write(g, {"svc/main.go": GO})
            for a in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@example.com", "-c", "user.name=Acme", "commit", "-qm", "fixture"]):
                subprocess.run(["git", "-C", str(g), *a], check=True, capture_output=True, env=ENV)
            r = subprocess.run(["bash", str(RC), "--full", "--repo", str(g)], capture_output=True, text=True, env=ENV)
        rows = [x for x in json.loads(r.stdout) if x["tool"] == "route-auth"]
        self.assertEqual([(x["file"], x["line"], x["rule"]) for x in rows], [("svc/main.go", 10, "not-checked")])
        self.assertTrue(rows[0]["message"].startswith("3 route(s) accept state-changing methods here"), rows)
        self.assertIn("route-auth: heuristic; scanned 0 handlers", r.stderr)
        self.assertNotIn("route-auth (SKIPPED", r.stderr)


if __name__ == "__main__":
    unittest.main()
