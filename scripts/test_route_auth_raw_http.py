"""route_auth_map.py raw-dispatch handlers: node:http / fetch-handler `pathname` + method branches. Fictional fixtures only (Acme, example.com)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/route_auth_map.py"

SERVER = '''import http from "node:http";
import { requireAuth } from "./auth.js";
const NOTES = "/notes";
http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://example.com");
  if (url.pathname === "/widgets" && req.method === "POST") { res.end("ok"); }
  if (req.method == "DELETE" && "/gadgets" == url.pathname) { res.end("x"); }
  if (url.pathname === NOTES) {
    if (req.method !== "PUT") return;
    res.end("n");
  }
  if (url.pathname === "/safe" && req.method === "POST") {
    requireAuth(req);
    res.end("ok");
  }
  if (url.pathname === "/list" && req.method === "GET") res.end("l");
  switch (url.pathname) {
    case "/sw":
      if (req.method === "PATCH") { res.end("p"); }
      break;
    default: break;
  }
}).listen(1);
'''
GATED = '''export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const user = await requireAuth(request);
    const { pathname } = new URL(request.url);
    if (request.method === "POST" && pathname === "/orders") { return new Response("ok"); }
    return new Response("nf", { status: 404 });
  },
};
'''
NOSERVER = '''export function route(pathname, method) {
  if (pathname === "/widgets" && method === "POST") return 1;
  return 0;
}
'''
DO = '''export class Room {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "POST" && url.pathname === "/x") { return new Response("ok"); }
    return new Response("nf");
  }
}
'''
ENTRY = '''import { WorkerEntrypoint } from "cloudflare:workers";
export default class extends WorkerEntrypoint {
  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "POST" && url.pathname === "/x") { return new Response("ok"); }
    return new Response("nf");
  }
}
'''


def run(files):
    with tempfile.TemporaryDirectory() as d:
        for n, t in files.items(): (Path(d) / n).write_text(t)
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), d], capture_output=True, text=True)
    rows = [l.split(": ", 1)[1] for l in r.stdout.splitlines()[:-1]]
    return rows, json.loads(r.stdout.splitlines()[-1])


class RawHttp(unittest.TestCase):
    def test_server_branches(self):
        rows, j = run({"s.js": SERVER})
        self.assertEqual(rows, ["HIGH: POST /widgets auth=none", "HIGH: DELETE /gadgets auth=none", "HIGH: PUT /notes auth=none",
                                "INFO: POST /safe auth=requireAuth", "INFO: GET /list auth=none", "HIGH: PATCH /sw auth=none"])
        self.assertEqual(j["high"], 4)

    def test_gate_before_dispatch_is_not_high(self):
        rows, j = run({"w.ts": GATED})
        self.assertEqual(rows, ["INFO: POST /orders auth=requireAuth"])
        self.assertEqual(j["high"], 0)

    def test_sibling_auth_does_not_leak(self):
        rows, _ = run({"s.js": SERVER})
        self.assertIn("HIGH: PATCH /sw auth=none", rows)  # /safe's requireAuth sits in an earlier branch

    def test_non_server_file_has_no_handler(self):
        rows, j = run({"r.js": NOSERVER})
        self.assertEqual((rows, j["handlers"]), ([], 0))

    def test_durable_object_class_fetch_is_internal(self):
        self.assertEqual(run({"r.ts": DO})[0], [])

    def test_default_exported_entrypoint_class_stays_public(self):
        self.assertEqual(run({"e.ts": ENTRY})[0], ["HIGH: POST /x auth=none"])

    def test_branch_without_method_is_skipped(self):
        rows, _ = run({"s.js": 'http.createServer((req, res) => {\n  if (req.url === "/x") { res.end(); }\n});\n'})
        self.assertEqual(rows, [])

    def test_prefix_guard_in_unmatched_if_does_not_leak(self):
        src = 'http.createServer((req, res) => {\n  if (pathname.startsWith("/admin")) { requireAuth(req); }\n  if (pathname === "/open" && req.method === "POST") { res.end(); }\n});\n'
        rows, j = run({"s.js": src})
        self.assertEqual((rows, j["high"]), (["HIGH: POST /open auth=none"], 1))

    def test_guard_in_enclosing_if_counts(self):
        src = 'http.createServer((req, res) => {\n  if (pathname.startsWith("/admin")) {\n    requireAuth(req);\n    if (pathname === "/admin/x" && req.method === "POST") { res.end(); }\n  }\n});\n'
        self.assertEqual(run({"s.js": src})[0], ["INFO: POST /admin/x auth=requireAuth"])

    def test_negated_enclosing_method_is_not_a_method(self):
        src = 'http.createServer((req, res) => {\n  if (req.method !== "POST") { if (pathname === "/z") { res.end(); } }\n});\n'
        self.assertEqual(run({"s.js": src})[0], [])

    def test_positive_enclosing_method_still_counts(self):
        src = 'http.createServer((req, res) => {\n  if (req.method === "PUT") { if (isOk) { if (pathname === "/z") { res.end(); } } }\n});\n'
        self.assertEqual(run({"s.js": src})[0], ["HIGH: PUT /z auth=none"])

    def test_non_pathname_variable_is_not_a_route(self):
        src = 'http.createServer((req, res) => {\n  if (filePath === "/etc/x" && req.method === "GET") { res.end(); }\n  if (url.path === "/p" && req.method === "GET") { res.end(); }\n});\n'
        self.assertEqual(run({"s.js": src})[0], ["INFO: GET /p auth=none"])

    def test_unclosed_switch_keeps_span_in_range(self):
        src = 'http.createServer((req, res) => {\n  switch (pathname) {\n    case "/a": ok = req.method === "POST"'
        self.assertEqual(run({"s.js": src})[0], ["HIGH: POST /a auth=none"])

    def test_auth_in_dispatch_condition_counts(self):
        src = 'http.createServer((req, res) => {\n  if (isAuthenticated(req) && pathname === "/x" && req.method === "POST") { res.end(); }\n});\n'
        self.assertEqual(run({"s.js": src})[0], ["INFO: POST /x auth=isAuthenticated"])


if __name__ == "__main__":
    unittest.main()
