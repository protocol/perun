"""cost_limit_map.py (static lead-finder for costly or unbounded HTTP endpoints with no rate or quota limit evidence): Express, Next route handlers, FastAPI and Flask
positives, limiter negatives (express-rate-limit, rateLimit, @limiter, Upstash ratelimit, package-level), page-size caps, ignored files, the usage contract and the
review_checks.sh --full wiring. Fixtures are fictional (acme, example.com); one new file per feature."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/deep-code-review/scripts"
SCRIPT, RC = SK / "cost_limit_map.py", SK / "review_checks.sh"
sys.path.insert(0, str(SK))
import cost_limit_map as C  # noqa: E402

MISS, EVID = "missing-cost-limit", "cost-limit-evidence"


def src(*lines):
    """A source file from its lines."""
    return "\n".join(lines) + "\n"


def write(root, files):
    """Create every relative path -> str under root."""
    for rel, text in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def rows(files):
    """The (file, line, rule, kind) rows from analyze() for a fresh temp repo; kind is the message's first word."""
    with tempfile.TemporaryDirectory() as t:
        write(t, files)
        return [(f, ln, r, m.split(" ")[0]) for f, ln, r, m in C.analyze(t)[0]]


EXPRESS_LLM = src('const express = require("express");', 'const OpenAI = require("openai");', "const app = express();",
                  'app.post("/chat", async (req, res) => {', "  const out = await client.chat.completions.create({ model: 'm', messages: req.body.messages });", "  res.json(out);", "});")
NEXT_LLM = src('import Anthropic from "@anthropic-ai/sdk";', "export async function POST(req) {", "  const r = await anthropic.messages.create({ model: 'm', max_tokens: 9, messages: [] });", "  return Response.json(r);", "}")
FAST_LLM = src("from fastapi import FastAPI", "app = FastAPI()", "", '@app.post("/ask")', "async def ask(q: str):", "    return await client.chat.completions.create(model='m', messages=[q])")
FLASK_UP = src("from flask import Flask, request", "app = Flask(__name__)", "app.config['MAX_CONTENT_LENGTH'] = 1 << 20", '@app.route("/doc", methods=["POST"])', "def doc():", "    f = request.files['file']", "    f.save('/tmp/x')", "    return 'ok'")


class CostLimit(unittest.TestCase):
    def test_positives(self):
        self.assertEqual(rows({"server.js": EXPRESS_LLM}), [("server.js", 4, MISS, "llm")])
        self.assertEqual(rows({"app/api/chat/route.ts": NEXT_LLM}), [("app/api/chat/route.ts", 2, MISS, "llm")])
        self.assertEqual(rows({"main.py": FAST_LLM}), [("main.py", 4, MISS, "llm")])
        self.assertEqual(rows({"app.py": FLASK_UP}), [("app.py", 4, MISS, "upload")])

    def test_route_segments(self):
        a = src("const app = require('express')();", "app.get('/search', (req, res) => res.json([]));", "app.get('/reports/export', (req, res) => res.send(''));")
        self.assertEqual([r[3] for r in rows({"a.js": a})], ["search", "export"])

    def test_single_file_download_is_not_export(self):
        a = src("const app = require('express')();", "app.get('/resources/:id/download', (req, res) => res.send('x'));")
        self.assertEqual(rows({"a.js": a}), [])

    def test_page_size(self):
        raw = src("const app = require('express')();", "app.get('/items', (req, res) => {", "  const n = req.query.limit;", "  res.json(db.all(n));", "});")
        self.assertEqual(rows({"a.js": raw}), [("a.js", 2, MISS, "page-size")])
        capped = raw.replace("req.query.limit;", "Math.min(Number(req.query.limit), 100);")
        self.assertEqual(rows({"a.js": capped}), [])
        py = src("from fastapi import FastAPI, Query", "app = FastAPI()", '@app.get("/items")', "def items(", "    limit: int = Query(default=10, le=200),", "):", "    return []")
        self.assertEqual(rows({"a.py": py}), [])

    def test_negatives_limiter(self):
        for name, ev in (("express-rate-limit", 'app.use(require("express-rate-limit")());'), ("middleware", "app.use(limiter);"),
                         ("upstash", 'const rl = new Ratelimit({});'), ("429", "const c = 429;")):
            got = rows({"server.js": ev + "\n" + EXPRESS_LLM})
            self.assertEqual([r[2] for r in got], [EVID], name)
        py = rows({"main.py": "from slowapi import Limiter\n@limiter.limit('5/minute')\n" + FAST_LLM})
        self.assertEqual([r[2] for r in py], [EVID])
        self.assertEqual([r[2] for r in rows({"app.py": "limiter = Limiter(app)\n" + FLASK_UP})], [EVID])

    def test_comment_and_bare_throttle_are_not_evidence(self):
        self.assertEqual([r[2] for r in rows({"server.js": "// rateLimit later\n" + EXPRESS_LLM})], [MISS])
        self.assertEqual([r[2] for r in rows({"server.js": "const throttle = 1;\n" + EXPRESS_LLM})], [MISS])

    def test_package_scope(self):
        files = {"a/package.json": "{}", "a/s.js": EXPRESS_LLM, "b/package.json": "{}", "b/lim.js": 'const rateLimit = require("express-rate-limit");\n'}
        self.assertEqual([(r[0], r[2]) for r in rows(files)], [("a/s.js", MISS)])
        files["a/lim.js"] = "const limiter = 1;\n"
        self.assertEqual([r[2] for r in rows(files)], [EVID])

    def test_ignored(self):
        self.assertEqual(rows({"tests/chat.test.js": EXPRESS_LLM, "node_modules/x/s.js": EXPRESS_LLM}), [])
        self.assertEqual(rows({"s.js": 'const app = require("express")();\napp.get("/ping", (q, r) => r.send("ok"));\n'}), [])

    def test_cli_and_wiring(self):
        r = subprocess.run([sys.executable, "-I", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stderr), (2, "usage: cost_limit_map.py DIR\n"))
        env = dict(os.environ, PATH="/usr/bin:/bin")
        with tempfile.TemporaryDirectory() as t:
            def repo(name, files):
                g = Path(t) / name
                write(g, files)
                for a in (["init", "-q"], ["add", "-A"], ["-c", "user.email=a@example.com", "-c", "user.name=Acme", "commit", "-qm", "fixture"]):
                    subprocess.run(["git", "-C", str(g), *a], check=True, capture_output=True, env=env)
                return g

            r = subprocess.run(["bash", str(RC), "--full", "--repo", str(repo("g", {"server.js": EXPRESS_LLM}))], capture_output=True, text=True, env=env)
            self.assertEqual([(x["file"], x["line"], x["rule"]) for x in json.loads(r.stdout) if x["tool"] == "cost-limit"], [("server.js", 4, MISS)])
            r = subprocess.run(["bash", str(RC), "--full", "--repo", str(repo("g2", {"a.ts": "export const a = 1;\n"}))], capture_output=True, text=True, env=env)
            self.assertIn("cost-limit (SKIPPED: no HTTP handler)", r.stderr)
            self.assertEqual([x["rule"] for x in json.loads(r.stdout) if x["tool"] == "cost-limit"], ["not-checked"])


if __name__ == "__main__":
    unittest.main()
