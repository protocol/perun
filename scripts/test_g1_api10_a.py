#!/usr/bin/env python3
"""G1 status (a): OWASP API10:2023 unsafe consumption of APIs
(perun.{py,js}.unsafe-api-consumption, perun.{py,js}.tls-verify-off).

Inline tempdir fixtures (fictional names). A line ending in the HIT marker must be flagged by the named rule,
every other line must stay silent; negatives (near misses) must produce no hit at all. Rules are not edited to fit
the seeds. A missing semgrep skips, never passes. Known uncovered: a helper in another file returning the response
field (taint stays inside one file).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_g1_api_pilot_a import semgrep_hits, tree  # noqa: E402

UAC, TLS = "unsafe-api-consumption", "tls-verify-off"

PY_POS = {
    "sql_fstring.py": 'def f(cur):\n    d = requests.get("https://api.acme.example/u").json()\n    cur.execute(f"SELECT * FROM t WHERE n = \'{d[\'name\']}\'")  # HIT\n',
    "sql_concat_get.py": 'def f(cur):\n    r = httpx.get("https://api.acme.example/u")\n    name = r.json().get("name")\n    cur.execute("SELECT * FROM t WHERE n = \'" + name + "\'")  # HIT\n',
    "sql_text.py": 'def f(conn):\n    body = requests.post("https://api.acme.example/q", json={}).text\n    conn.execute(text(f"DELETE FROM t WHERE k = {body}"))  # HIT\n',
    "path_open.py": 'def f():\n    d = requests.get("https://api.acme.example/f").json()\n    open(d["path"], "w")  # HIT\n',
    "path_join.py": 'import os\ndef f():\n    d = httpx.get("https://api.acme.example/f").json()\n    return open(os.path.join("/srv/data", d["file"]))  # HIT\n',
    "url_next.py": 'def f():\n    resp = requests.get("https://api.acme.example/list")\n    nxt = resp.json()["next"]\n    return requests.get(nxt)  # HIT\n',
    "url_host.py": 'def f():\n    d = requests.get("https://api.acme.example/cfg").json()\n    return httpx.post("https://" + d["host"] + "/hook", json={})  # HIT\n',
    "shell_system.py": 'import os\ndef f():\n    r = requests.get("https://api.acme.example/job")\n    os.system("convert " + r.text)  # HIT\n',
    "shell_run.py": 'import subprocess\ndef f():\n    d = requests.get("https://api.acme.example/job").json()\n    subprocess.run(f"tar xf {d[\'archive\']}", shell=True)  # HIT\n',
    "client_session.py": 'import httpx\nasync def f(cur):\n    async with httpx.AsyncClient() as client:\n        r = await client.get("https://api.acme.example/u")\n        cur.execute("SELECT " + r.json()["col"])  # HIT\n',
}
PY_NEG = {
    "bound.py": 'def f(cur):\n    d = requests.get("https://api.acme.example/u").json()\n    cur.execute("SELECT * FROM t WHERE n = %s", (d["name"],))\n',
    "cast_int.py": 'def f(cur):\n    d = requests.get("https://api.acme.example/u").json()\n    n = int(d["id"])\n    cur.execute(f"SELECT * FROM t WHERE id = {n}")\n',
    "allowlist.py": 'def f(cur):\n    d = requests.get("https://api.acme.example/u").json()\n    k = d["kind"]\n    if k not in ("a", "b"):\n        raise ValueError(k)\n    cur.execute(f"SELECT {k} FROM t")\n',
    "const_url.py": 'def f():\n    d = requests.get("https://api.acme.example/u").json()\n    return requests.get("https://api.acme.example/items/" + d["id"])\n',
    "basename.py": 'import os\ndef f():\n    d = requests.get("https://api.acme.example/f").json()\n    return open(os.path.join("/srv", os.path.basename(d["file"])))\n',
    "data_not_path.py": 'import json\ndef f():\n    d = requests.get("https://api.acme.example/f").json()\n    with open("/srv/out.json", "w") as fh:\n        json.dump(d, fh)\n',
    "request_source.py": 'from flask import request\ndef f(cur):\n    cur.execute("SELECT 1 WHERE n = %s", (request.args["n"],))\n    return requests.get("https://api.acme.example/u").status_code\n',
    "shell_list.py": 'import subprocess\ndef f():\n    d = requests.get("https://api.acme.example/job").json()\n    subprocess.run(["tar", "xf", "fixed.tar"])\n    print(d["name"])\n',
    "shlex.py": 'import os, shlex\ndef f():\n    r = requests.get("https://api.acme.example/job")\n    os.system("convert " + shlex.quote(r.text))\n',
    "regex_guard.py": 'import re\ndef f(cur):\n    d = requests.get("https://api.acme.example/u").json()\n    k = d["col"]\n    if not re.fullmatch(r"[a-z_]+", k):\n        raise ValueError(k)\n    cur.execute(f"SELECT {k} FROM t")\n',
    "verify_on.py": 'def f():\n    requests.get("https://api.acme.example/u", verify=True)\n    requests.get("https://api.acme.example/u", verify="/etc/ca.pem")\n    httpx.Client(verify=True)\n',
}
PY_TLS = {
    "tls_req.py": 'def f():\n    return requests.get("https://api.acme.example/u", verify=False)  # HIT\n',
    "tls_httpx.py": 'def f():\n    return httpx.get("https://api.acme.example/u", verify=False)  # HIT\n',
    "tls_client.py": 'def f():\n    return httpx.Client(verify=False)  # HIT\n',
    "tls_session.py": 'def f():\n    s = requests.Session()\n    s.verify = False  # HIT\n    return s\n',
    "tls_ctx.py": 'import ssl\nctx = ssl._create_unverified_context()  # HIT\n',
    "tls_cert_none.py": 'import ssl\nctx = ssl.create_default_context()\nctx.check_hostname = False  # HIT\nctx.verify_mode = ssl.CERT_NONE  # HIT\n',
    "tls_aiohttp.py": 'import aiohttp\nconn = aiohttp.TCPConnector(ssl=False)  # HIT\n',
    "tls_post.py": 'def f(p):\n    return requests.post("https://api.acme.example/u", json=p, timeout=5, verify=False)  # HIT\n',
}
JS_POS = {
    "sql_json.js": 'async function f(db) {\n  const res = await fetch("https://api.acme.example/u");\n  const body = await res.json();\n  await db.query(`SELECT * FROM t WHERE n = \'${body.name}\'`);  // HIT\n}\n',
    "path_axios.js": 'const fs = require("fs");\nconst path = require("path");\nasync function f() {\n  const { data } = await axios.get("https://api.acme.example/f");\n  fs.readFileSync(path.join("/srv", data.file));  // HIT\n}\n',
    "shell_axios.js": 'const { exec } = require("child_process");\nasync function f() {\n  const r = await axios.get("https://api.acme.example/job");\n  exec("convert " + r.data.name);  // HIT\n}\n',
    "url_next.js": 'async function f() {\n  const j = await (await fetch("https://api.acme.example/p")).json();\n  return fetch(j.next);  // HIT\n}\n',
    "then_chain.js": 'function f(db) {\n  fetch("https://api.acme.example/u").then((r) => r.json()).then((u) => {\n    db.query("SELECT " + u.col);  // HIT\n  });\n}\n',
    "then_axios.js": 'const fs = require("fs");\nfunction f() {\n  axios.get("https://api.acme.example/u").then((resp) => {\n    fs.writeFileSync(resp.data.name, "x");  // HIT\n  });\n}\n',
    "text_exec.js": 'const cp = require("child_process");\nasync function f() {\n  const res = await fetch("https://api.acme.example/job");\n  const t = await res.text();\n  cp.execSync(`run ${t}`);  // HIT\n}\n',
    "axios_host.js": 'async function f() {\n  const { data } = await axios.get("https://api.acme.example/cfg");\n  return axios.post(`https://${data.host}/hook`, {});  // HIT\n}\n',
    "raw_prisma.js": 'async function f(prisma) {\n  const res = await fetch("https://api.acme.example/u");\n  const u = await res.json();\n  return prisma.$queryRawUnsafe("SELECT * FROM t WHERE n = \'" + u.name + "\'");  // HIT\n}\n',
    "fs_write.js": 'const fs = require("fs");\nasync function f() {\n  const r = await axios.get("https://api.acme.example/f");\n  await fs.promises.writeFile(r.data.target, "x");  // HIT\n}\n',
}
JS_NEG = {
    "bound.js": 'async function f(db) {\n  const { data } = await axios.get("https://api.acme.example/u");\n  await db.query("SELECT * FROM t WHERE n = $1", [data.name]);\n}\n',
    "cast_int.js": 'async function f(db) {\n  const res = await fetch("https://api.acme.example/u");\n  const b = await res.json();\n  const id = parseInt(b.id, 10);\n  await db.query(`SELECT * FROM t WHERE id = ${id}`);\n}\n',
    "allowlist.js": 'async function f(db) {\n  const { data } = await axios.get("https://api.acme.example/u");\n  if (!ALLOW.has(data.kind)) throw new Error("bad");\n  await db.query(`SELECT ${data.kind} FROM t`);\n}\n',
    "const_url.js": 'async function f() {\n  const { data } = await axios.get("https://api.acme.example/u");\n  return fetch("https://api.acme.example/items/" + data.id);\n}\n',
    "basename.js": 'const fs = require("fs");\nconst path = require("path");\nasync function f() {\n  const { data } = await axios.get("https://api.acme.example/f");\n  fs.readFileSync(path.join("/srv", path.basename(data.file)));\n}\n',
    "data_not_path.js": 'const fs = require("fs");\nasync function f() {\n  const { data } = await axios.get("https://api.acme.example/f");\n  fs.writeFileSync("/srv/out.json", JSON.stringify(data));\n}\n',
    "request_source.js": 'async function f(req, db) {\n  await db.query("SELECT 1 WHERE n = $1", [req.query.n]);\n  const r = await fetch("https://api.acme.example/u");\n  return r.status;\n}\n',
    "regex_guard.js": 'async function f(db) {\n  const { data } = await axios.get("https://api.acme.example/u");\n  if (!/^[a-z_]+$/.test(data.col)) throw new Error("bad");\n  await db.query(`SELECT ${data.col} FROM t`);\n}\n',
    "map_get.js": 'async function f(cache) {\n  const { data } = await axios.get("https://api.acme.example/u");\n  return cache.get(data.key);\n}\n',
    "encode.js": 'async function f() {\n  const { data } = await axios.get("https://api.acme.example/u");\n  return fetch("https://" + encodeURIComponent(data.host) + "/x");\n}\n',
    "tls_on.js": 'const agent = new https.Agent({ rejectUnauthorized: true, ca: CA });\nprocess.env.NODE_TLS_REJECT_UNAUTHORIZED = "1";\n',
}
JS_TLS = {
    "tls_agent.js": 'const agent = new https.Agent({ rejectUnauthorized: false });  // HIT\n',
    "tls_axios.js": 'axios.get("https://api.acme.example/u", { httpsAgent: new https.Agent({ rejectUnauthorized: false }) });  // HIT\n',
    "tls_env.js": 'process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";  // HIT\n',
    "tls_env_num.js": 'process.env.NODE_TLS_REJECT_UNAUTHORIZED = 0;  // HIT\n',
    "tls_connect.js": 'const s = tls.connect({ host: "api.acme.example", port: 443, rejectUnauthorized: false });  // HIT\n',
    "tls_request.js": 'const req = https.request({ hostname: "api.acme.example", strictSSL: false });  // HIT\n',
    "tls_bracket.js": 'process.env["NODE_TLS_REJECT_UNAUTHORIZED"] = "0";  // HIT\n',
    "tls_ts.ts": 'export const agent = new https.Agent({ keepAlive: true, rejectUnauthorized: false });  // HIT\n',
}


def marked(files):
    return {(n, i + 1) for n, b in files.items() for i, ln in enumerate(b.splitlines()) if ln.rstrip().endswith("# HIT") or ln.rstrip().endswith("// HIT")}


class Api10(unittest.TestCase):
    def check(self, cfg, pos, neg, rule):
        files = {**pos, **neg}
        rows = {(f, line) for f, line, r in semgrep_hits(cfg, tree(files)) if r.endswith(rule)}
        self.assertEqual(rows, marked(pos))

    def test_py_unsafe_consumption(self):
        self.check("py.yml", PY_POS, PY_NEG, UAC)

    def test_py_tls_verify_off(self):
        self.check("py.yml", PY_TLS, PY_NEG, TLS)

    def test_js_unsafe_consumption(self):
        self.check("js.yml", JS_POS, JS_NEG, UAC)

    def test_js_tls_verify_off(self):
        self.check("js.yml", JS_TLS, JS_NEG, TLS)

    def test_fixture_counts(self):
        self.assertGreaterEqual((len(PY_POS), len(PY_NEG), len(JS_POS), len(JS_NEG)), (8, 8, 8, 8))
        self.assertGreaterEqual((len(PY_TLS), len(JS_TLS)), (8, 8))


if __name__ == "__main__":
    unittest.main()
