"""cost_limit_map.py rule unbounded-body (CWE-770): a handler that reads the whole request body (Next/Hono/Express/FastAPI/Flask), a Content-Length-only cap,
and a body-parser call with a huge or infinite limit; negatives are a streamed byte count, framework body limits and the default 100kb. Fixtures are fictional
(acme, example.com); one new file per feature."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/deep-code-review/scripts"
sys.path.insert(0, str(SK))
import cost_limit_map as C  # noqa: E402

UB = "unbounded-body"


def src(*lines):
    """A source file from its lines."""
    return "\n".join(lines) + "\n"


def ub(files):
    """The (file, line, kind) unbounded-body rows for a fresh temp repo; kind is the message's text before the first colon."""
    with tempfile.TemporaryDirectory() as t:
        for rel, text in files.items():
            p = Path(t, rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        return [(f, ln, m.split(":")[0]) for f, ln, r, m in C.analyze(t)[0] if r == UB]


NEXT = src("export async function POST(req) {", "  const body = await req.formData();", "  return Response.json(body);", "}")
EXPRESS = src("const app = require('express')();", "app.post('/note', async (req, res) => {", "  const t = await req.text();", "  res.send(t);", "});")
FAST = src("from fastapi import FastAPI, UploadFile", "app = FastAPI()", '@app.post("/up")', "async def up(f: UploadFile):", "    data = await f.read()", "    return len(data)")
FLASK = src("from flask import Flask, request", "app = Flask(__name__)", '@app.route("/doc", methods=["POST"])', "def doc():", "    return str(len(request.get_data()))")


class UnboundedBody(unittest.TestCase):
    def test_whole_body_reads(self):
        self.assertEqual(ub({"app/api/n/route.ts": NEXT}), [("app/api/n/route.ts", 1, "whole request body read")])
        self.assertEqual(ub({"s.js": EXPRESS}), [("s.js", 2, "whole request body read")])
        self.assertEqual(ub({"m.py": FAST}), [("m.py", 3, "whole request body read")])
        self.assertEqual(ub({"a.py": FLASK}), [("a.py", 3, "whole request body read")])
        hono = src("import { Hono } from 'hono';", "const app = new Hono();", "app.post('/x', async (c) => {", "  const b = await c.req.arrayBuffer();", "  return c.text('ok');", "});")
        self.assertEqual(len(ub({"h.ts": hono})), 1)

    def test_json_is_never_flagged(self):
        j = NEXT.replace("formData", "json")
        self.assertEqual(ub({"app/api/n/route.ts": j}), [])
        self.assertEqual(ub({"s.js": EXPRESS.replace("req.text()", "req.json()")}), [])
        self.assertEqual(ub({"m.py": src("from fastapi import FastAPI, Request", "app = FastAPI()", '@app.post("/e")', "async def e(request: Request):", "    return await request.json()")}), [])

    def test_read_receivers(self):
        fs = src("const app = require('express')();", "const fs = require('fs');", "app.get('/cfg', (req, res) => {", "  const t = fs.createReadStream('a').read();", "  res.send(t);", "});")
        self.assertEqual(ub({"s.js": fs}), [])
        py = src("from fastapi import FastAPI", "app = FastAPI()", '@app.get("/cfg")', "def cfg():", "    with open('a.txt') as h:", "        return h.read()")
        self.assertEqual(ub({"m.py": py}), [])
        up = FAST.replace("f: UploadFile", "doc: UploadFile").replace("f.read()", "doc.read()")
        self.assertEqual(len(ub({"m.py": up})), 1)
        self.assertEqual(len(ub({"m.py": FAST.replace("await f.read()", "await f.read() + open('z').read()")})), 1)

    def test_limit_scoped_to_package(self):
        files = {"a/package.json": "{}", "a/route.js": EXPRESS, "b/package.json": "{}", "b/cfg.js": "const f = Fastify({ bodyLimit: 1048576 });\n", "cfg.js": "const g = { bodyLimit: 1 };\n"}
        self.assertEqual([r[0] for r in ub(files)], ["a/route.js"], "a limit in a sibling package or at the root does not cover package a")
        files["a/cfg.js"] = "const f = Fastify({ bodyLimit: 1048576 });\n"
        self.assertEqual(ub(files), [])

    def test_last_handler_ends_at_next_declaration(self):
        js = EXPRESS + "\nfunction helper(res) {\n  return res.text().length;\n}\nconst r = request.formData();\n"
        js = js.replace("await req.text()", "'x'")
        self.assertEqual(ub({"s.js": js}), [])
        py = src("from fastapi import FastAPI", "app = FastAPI()", '@app.get("/a")', "def a():", "    return 1", "", "def other(request):", "    return request.get_data()")
        self.assertEqual(ub({"m.py": py}), [])

    def test_content_length_only(self):
        cl = NEXT.replace("  const body", "  if (Number(req.headers.get('content-length')) > 1e6) return new Response('big', { status: 413 });\n  const body")
        self.assertEqual(ub({"app/api/n/route.ts": cl}), [("app/api/n/route.ts", 1, "only cap is Content-Length")])

    def test_body_parser_limit(self):
        for lim, flag in (("'1gb'", 1), ("'50mb'", 1), ("Infinity", 1), ("50 * 1024 * 1024", 1), ("'100kb'", 0), ("'5mb'", 0)):
            a = src("const express = require('express');", "const app = express();", "app.use(express.json({ limit: %s }));" % lim, "app.get('/', (q, r) => r.send('ok'));")
            self.assertEqual(len(ub({"a.js": a})), flag, lim)
        d = src("const express = require('express');", "const app = express();", "app.use(express.json());", "app.use(express.urlencoded({ extended: true }));")
        self.assertEqual(ub({"a.js": d}), [], "the default 100kb is not flagged")

    def test_negatives(self):
        stream = src("export async function POST(req) {", "  const r = req.body.getReader();", "  let total = 0;", "  for (;;) {", "    const { done, value } = await r.read();",
                     "    if (done) break;", "    total += value.length;", "    if (total > 1e6) return new Response('big', { status: 413 });", "  }", "  return new Response('ok');", "}")
        self.assertEqual(ub({"app/api/n/route.ts": stream}), [])
        self.assertEqual(ub({"app/api/n/route.ts": stream.replace("req.body.getReader()", "req.body.getReader()  /* content-length checked too */")}), [])
        for name, extra in (("next.config.js", "module.exports = { experimental: { serverActions: { bodySizeLimit: '1mb' } } };\n"),
                            ("f.js", "const f = Fastify({ bodyLimit: 1048576 });\n"), ("h.ts", "app.use(bodyLimit({ maxSize: 1024 }));\n"),
                            ("cfg.py", "app.config['MAX_CONTENT_LENGTH'] = 1 << 20\n")):
            self.assertEqual(ub({name: extra, "app/api/n/route.ts": NEXT, "m.py": FAST, "a.py": FLASK, "s.js": EXPRESS}), [], name)
        self.assertEqual(ub({"s.js": "// await req.json()\n" + EXPRESS.replace("await req.text()", "'x'")}), [], "comments and non-body reads")
        self.assertEqual(ub({"s.js": src("const app = require('express')();", "app.get('/x', async (req, res) => { const r = await fetch('https://example.com'); res.json(await r.json()); });")}), [])

    def test_wiring_keeps_rule(self):
        r = subprocess.run([sys.executable, "-I", str(SK / "cost_limit_map.py"), str(ROOT / "nonexistent-dir")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unbounded-body", (SK / "review_checks.sh").read_text())


if __name__ == "__main__":
    unittest.main()
