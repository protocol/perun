#!/usr/bin/env python3
"""G1 pilot, status (a): API2, API4, API7, API8 (OWASP API Top 10:2023).

Each item runs the detectors named in docs/bench/g1-matrix/DENOMINATORS.md "Costed pilot plan" against inline
tempdir fixtures (fictional names): >=2 seeded positives flagged at the seeded line, >=1 negative clean.
Detectors are not edited to fit the seeds; a detector that misses a seed keeps the case as expectedFailure and
the item is marked "(a) REJECTED -> (b)" in docs/bench/g1-matrix/pilot-api.md. A missing tool skips, never passes.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review"
SCRIPTS = SKILL / "scripts"
TAINT = SKILL / "templates/semgrep-taint"


def tool_env():
    """Private HOME so semgrep/checkov never write to the real one (sandbox denies ~/.semgrep)."""
    h = tempfile.mkdtemp(prefix="g1pa-home-")
    return {**os.environ, "HOME": h, "XDG_CACHE_HOME": h, "SEMGREP_USER_HOME": h, "BC_SKIP_MAPPING": "TRUE", "CHECKOV_RUN_SCA_PACKAGE_SCAN_V2": "false"}


def tree(files):
    d = Path(tempfile.mkdtemp(prefix="g1pa-"))
    for name, body in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return d


def script_rows(script, d):
    """Rows (file, line, rule) from a TSV lead-finder."""
    r = subprocess.run([sys.executable, "-I", str(SCRIPTS / script), str(d)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return {(f[0], int(f[1]), f[2]) for f in (ln.split("\t") for ln in r.stdout.splitlines()) if len(f) >= 3 and f[1].isdigit()}


def semgrep_hits(cfg, d):
    """(file, line, short rule id) from the bundled semgrep taint rules."""
    if not shutil.which("semgrep"):
        raise unittest.SkipTest("semgrep not installed")
    r = subprocess.run(["semgrep", "--config", str(TAINT / cfg), "--metrics=off", "--disable-version-check", "--json", "-q", str(d)],
                       capture_output=True, text=True, timeout=300, env=tool_env())
    assert r.returncode in (0, 1), r.stderr
    return {(Path(x["path"]).name, x["start"]["line"], x["check_id"].split("perun.", 1)[-1]) for x in json.loads(r.stdout)["results"]}


class Case(unittest.TestCase):
    def has(self, rows, name, line, rule):
        self.assertIn((name, line, rule), rows, sorted(rows))

    def clean(self, rows, rule, name=None):
        self.assertEqual([r for r in rows if r[2] == rule and (name is None or r[0] == name)], [])


JS_LOGIN = """const bcrypt = require('bcrypt');
const express = require('express');
const app = express();
app.post('/login', async (req, res) => {
  const ok = await bcrypt.compare(req.body.password, user.hash);
  res.json({ ok });
});
"""


class Api2(Case):
    """API2 Broken Authentication: attempt_limit_map, csrf_cookie_map, perun.js.auth-cookie-flags."""

    def test_attempt_limit_js_positive(self):
        self.has(script_rows("attempt_limit_map.py", tree({"login.js": JS_LOGIN})), "login.js", 4, "missing-attempt-limit")

    def test_attempt_limit_py_positive(self):
        src = "from fastapi import FastAPI\nfrom passlib.hash import bcrypt\napp = FastAPI()\n@app.post('/login')\ndef login(pw: str):\n    return bcrypt.verify(pw, 'h')\n"
        self.has(script_rows("attempt_limit_map.py", tree({"app.py": src})), "app.py", 4, "missing-attempt-limit")

    def test_attempt_limit_negative(self):
        src = JS_LOGIN.replace("const app", "const rateLimit = require('express-rate-limit');\nconst app").replace("'/login', async", "'/login', rateLimit({ max: 5 }), async")
        self.clean(script_rows("attempt_limit_map.py", tree({"login.js": src})), "missing-attempt-limit")

    def test_cookie_flags_positive_script(self):
        src = "const app = require('express')();\napp.get('/s', (req, res) => {\n  res.cookie('sid', 'abc');\n  res.send('ok');\n});\n"
        self.has(script_rows("csrf_cookie_map.py", tree({"s.js": src})), "s.js", 3, "missing-cookie-flags")

    def test_cookie_flags_positive_semgrep(self):
        src = "const app = require('express')();\napp.get('/s', (req, res) => {\n  res.cookie('sessionToken', 'abc');\n  res.send('ok');\n});\n"
        self.has(semgrep_hits("js.yml", tree({"s.js": src})), "s.js", 3, "js.auth-cookie-flags")

    def test_cookie_flags_negative(self):
        src = "const app = require('express')();\napp.get('/s', (req, res) => {\n  res.cookie('sid', 'abc', { httpOnly: true, secure: true, sameSite: 'lax' });\n  res.send('ok');\n});\n"
        d = tree({"s.js": src})
        self.clean(script_rows("csrf_cookie_map.py", d), "missing-cookie-flags")
        self.clean(semgrep_hits("js.yml", d), "js.auth-cookie-flags")


LLM_JS = """const express = require('express');
const OpenAI = require('openai');
const app = express();
app.post('/summarize', async (req, res) => {
  const r = await new OpenAI().chat.completions.create({ model: 'm', messages: [] });
  res.json(r);
});
"""


class Api4(Case):
    """API4 Unrestricted Resource Consumption: cost_limit_map, perun.js.body-cap-after-buffer."""

    def test_llm_handler_no_limit(self):
        self.has(script_rows("cost_limit_map.py", tree({"llm.js": LLM_JS})), "llm.js", 4, "missing-cost-limit")

    def test_upload_no_limit_py(self):
        src = "from fastapi import FastAPI, UploadFile\napp = FastAPI()\n@app.post('/upload')\nasync def upload(f: UploadFile):\n    data = await f.read()\n    return {'n': len(data)}\n"
        rows = script_rows("cost_limit_map.py", tree({"up.py": src}))
        self.has(rows, "up.py", 3, "missing-cost-limit")
        self.has(rows, "up.py", 3, "unbounded-body")

    def test_cost_limit_negative(self):
        src = LLM_JS.replace("const app", "const rateLimit = require('express-rate-limit');\nconst app").replace("'/summarize', async", "'/summarize', rateLimit({ max: 5 }), async")
        self.clean(script_rows("cost_limit_map.py", tree({"llm.js": src})), "missing-cost-limit")

    def test_body_cap_after_buffer_positive_json(self):
        src = "export async function POST(request: Request) {\n  const body = await request.json();\n  if (body.length > 1000) return new Response('big', { status: 413 });\n  return new Response('ok');\n}\n"
        self.has(semgrep_hits("js.yml", tree({"route.ts": src})), "route.ts", 2, "js.body-cap-after-buffer")

    def test_body_cap_after_buffer_positive_formdata(self):
        src = "export async function POST(request: Request) {\n  const form = await request.formData();\n  const f = form.get('file');\n  if (f.size > 1000000) return new Response('big', { status: 413 });\n  return new Response('ok');\n}\n"
        self.has(semgrep_hits("js.yml", tree({"route.ts": src})), "route.ts", 2, "js.body-cap-after-buffer")

    def test_body_cap_streamed_negative(self):
        src = "export async function POST(request: Request) {\n  const reader = request.body.getReader();\n  let total = 0;\n  for (;;) {\n    const { done, value } = await reader.read();\n    if (done) break;\n    total += value.length;\n    if (total > 1000) return new Response('big', { status: 413 });\n  }\n  return new Response('ok');\n}\n"
        self.clean(semgrep_hits("js.yml", tree({"route.ts": src})), "js.body-cap-after-buffer")


class Api7(Case):
    """API7 SSRF: perun.py.ssrf, perun.js.ssrf."""

    def test_py_flask_requests(self):
        src = "import requests\nfrom flask import Flask, request\napp = Flask(__name__)\n@app.route('/fetch')\ndef fetch():\n    u = request.args.get('url')\n    return requests.get(u).text\n"
        self.has(semgrep_hits("py.yml", tree({"app.py": src})), "app.py", 7, "py.ssrf")

    def test_py_urlopen(self):
        src = "import urllib.request\nfrom flask import Flask, request\napp = Flask(__name__)\n@app.route('/p')\ndef p():\n    u = request.form['target']\n    return urllib.request.urlopen(u).read()\n"
        self.has(semgrep_hits("py.yml", tree({"app.py": src})), "app.py", 7, "py.ssrf")

    def test_js_fetch(self):
        src = "const express = require('express');\nconst app = express();\napp.get('/fetch', async (req, res) => {\n  const r = await fetch(req.query.url);\n  res.send(await r.text());\n});\n"
        self.has(semgrep_hits("js.yml", tree({"app.js": src})), "app.js", 4, "js.ssrf")

    def test_js_axios(self):
        src = "const axios = require('axios');\nconst express = require('express');\nconst app = express();\napp.post('/hook', async (req, res) => {\n  const r = await axios.get(req.body.callback);\n  res.json(r.data);\n});\n"
        self.has(semgrep_hits("js.yml", tree({"app.js": src})), "app.js", 5, "js.ssrf")

    def test_negatives(self):
        py = "import requests\nfrom flask import Flask, request\napp = Flask(__name__)\n@app.route('/fetch')\ndef fetch():\n    q = request.args.get('q')\n    return requests.get('https://api.example.com/search', params={'q': q}).text\n"
        js = "const express = require('express');\nconst app = express();\napp.get('/fetch', async (req, res) => {\n  console.log(req.query.q);\n  const r = await fetch('https://api.example.com/items');\n  res.json(await r.json());\n});\n"
        d = tree({"app.py": py, "app.js": js})
        self.clean(semgrep_hits("py.yml", d), "py.ssrf")
        self.clean(semgrep_hits("js.yml", d), "js.ssrf")

    @unittest.expectedFailure
    def test_js_fixed_host_concat_is_flagged(self):
        """Known false positive: tainted text appended to a fixed https host is not host-controlling; the rule still flags it."""
        js = "const express = require('express');\nconst app = express();\napp.get('/fetch', async (req, res) => {\n  const r = await fetch('https://api.example.com/items?q=' + encodeURIComponent(req.query.q));\n  res.send(await r.text());\n});\n"
        self.clean(semgrep_hits("js.yml", tree({"app.js": js})), "js.ssrf")


NO_HEADERS = {"package.json": '{"dependencies": {"express": "4.19.2"}}\n', "server.js": "const express = require('express');\nconst app = express();\napp.listen(3000);\n"}


class Api8(Case):
    """API8 Security Misconfiguration: header_config, perun.js.cors-credentials-any-origin, hadolint, checkov."""

    def test_headers_missing(self):
        rows = script_rows("header_config.py", tree(NO_HEADERS))
        self.assertIn((".", 0, "header-not-found"), rows, sorted(rows))

    def test_headers_missing_vercel(self):
        rows = script_rows("header_config.py", tree({"vercel.json": '{"headers": []}\n'}))
        self.assertIn((".", 0, "header-not-found"), rows, sorted(rows))

    def test_headers_present_negative(self):
        d = tree({**NO_HEADERS, "server.js": "const express = require('express');\nconst helmet = require('helmet');\nconst app = express();\napp.use(helmet());\napp.listen(3000);\n"})
        self.clean(script_rows("header_config.py", d), "header-not-found")

    def test_cors_config_positive(self):
        src = "const cors = require('cors');\nconst app = require('express')();\napp.use(cors({ origin: true, credentials: true }));\n"
        self.has(semgrep_hits("js.yml", tree({"a.js": src})), "a.js", 3, "js.cors-credentials-any-origin")

    def test_cors_reflect_positive(self):
        src = "const app = require('express')();\napp.use((req, res, next) => {\n  res.setHeader('Access-Control-Allow-Origin', req.get('Origin'));\n  res.setHeader('Access-Control-Allow-Credentials', 'true');\n  next();\n});\n"
        self.has(semgrep_hits("js.yml", tree({"a.js": src})), "a.js", 3, "js.cors-credentials-any-origin")

    def test_cors_allowlist_negative(self):
        src = "const cors = require('cors');\nconst app = require('express')();\napp.use(cors({ origin: ['https://app.example.com'], credentials: true }));\n"
        self.clean(semgrep_hits("js.yml", tree({"a.js": src})), "js.cors-credentials-any-origin")

    def _tool(self, name, args, d):
        if not shutil.which(name):
            raise unittest.SkipTest(f"{name} not installed")
        r = subprocess.run([name, *args, str(d)], capture_output=True, text=True, timeout=300, env=tool_env())
        return r.stdout + r.stderr

    def test_hadolint_positive_and_negative(self):
        bad = tree({"Dockerfile": "FROM ubuntu:latest\nRUN apt-get install curl\n"})
        good = tree({"Dockerfile": "FROM ubuntu:22.04\nUSER app\n"})
        out = self._tool("hadolint", ["-f", "json"], bad / "Dockerfile")
        self.assertIn("DL3007", out)
        self.assertNotIn("DL3007", self._tool("hadolint", ["-f", "json"], good / "Dockerfile"))

    def _checkov(self, tf):
        out = self._tool("checkov", ["--quiet", "--compact", "-o", "json", "--framework", "terraform", "-d"], tree({"main.tf": tf}))
        return {(c["check_id"], c["file_line_range"][0]) for c in json.loads(out[: out.rindex("}") + 1])["results"]["failed_checks"]}

    def test_checkov_open_ssh_positive(self):
        sg = 'resource "aws_security_group" "g" {\n  name = "acme-sg"\n  ingress {\n    from_port   = 22\n    to_port     = 22\n    protocol    = "tcp"\n    cidr_blocks = ["%s"]\n  }\n}\n'
        self.assertIn(("CKV_AWS_24", 1), self._checkov(sg % "0.0.0.0/0"))
        self.assertNotIn("CKV_AWS_24", {c for c, _ in self._checkov(sg % "10.0.0.0/8")})

    def test_checkov_s3_public_block_positive(self):
        tf = 'resource "aws_s3_bucket" "b" {\n  bucket = "acme"\n}\nresource "aws_s3_bucket_public_access_block" "p" {\n  bucket = aws_s3_bucket.b.id\n  block_public_acls = false\n}\n'
        self.assertIn(("CKV_AWS_53", 4), self._checkov(tf))


if __name__ == "__main__":
    unittest.main()
