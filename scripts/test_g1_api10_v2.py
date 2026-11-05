#!/usr/bin/env python3
"""G1 API10:2023 detector v2 (perun.{py,js}.unsafe-api-consumption, perun.{py,js}.tls-verify-off).

New seeded shapes beyond the first test file: a same-file helper that returns the response body (plain, async,
method, arrow, promise-then), a same-file wrapper around a shell/SQL/file sink, client-instance URL sinks,
Path/send_file/popen sinks, and near-miss negatives (coercion helper, hash, constant-map lookup, URL host check,
helper that does not call an API, literal wrapper argument). A line ending in the HIT marker must be flagged by the
named rule; every other line must stay silent. Fictional names only. A missing semgrep skips, never passes.
Known uncovered: a helper defined in another file of the same case (OSS semgrep taint is single-file), a helper
defined after its caller in the same block, a response that arrives through an unnamed client.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_g1_api_pilot_a import semgrep_hits, tree  # noqa: E402

UAC, TLS = "unsafe-api-consumption", "tls-verify-off"

PY_POS = {
    "h_plain.py": 'def load(n):\n    r = requests.get(f"https://api.acme.example/p/{n}")\n    r.raise_for_status()\n    return r.json()\n\ndef go(cur, n):\n    p = load(n)\n    cur.execute("DELETE FROM t WHERE k = \'%s\'" % p["key"])  # HIT\n',
    "h_text.py": 'import os\ndef body():\n    r = httpx.get("https://api.acme.example/script")\n    return r.text\n\ndef go():\n    os.system("sh -c " + body())  # HIT\n',
    "h_async.py": 'import httpx\nasync def cfg():\n    async with httpx.AsyncClient() as c:\n        r = await c.get("https://api.acme.example/cfg")\n        return r.json()\n\nasync def go():\n    d = await cfg()\n    return open(d["path"])  # HIT\n',
    "h_method.py": 'import requests\nclass Feed:\n    def __init__(self):\n        self.session = requests.Session()\n    def items(self):\n        r = self.session.get("https://api.acme.example/items")\n        return r.json()["items"]\n    def save(self, cur):\n        for it in self.items():\n            cur.execute("INSERT INTO t VALUES (\'" + it["name"] + "\')")  # HIT\n',
    "w_shell.py": 'import subprocess\ndef run(cmd):\n    return subprocess.run(cmd, shell=True)\n\ndef go():\n    j = requests.get("https://api.acme.example/job").json()\n    run("make " + j["target"])  # HIT\n',
    "w_sql.py": 'def q(cur, sql):\n    cur.execute(sql)\n\ndef go(cur):\n    j = requests.get("https://api.acme.example/f").json()\n    q(cur, f"SELECT * FROM {j[\'table\']}")  # HIT\n',
    "k_client_url.py": 'import httpx\ndef go():\n    with httpx.Client() as client:\n        d = client.get("https://api.acme.example/p").json()\n        return client.get(d["next"])  # HIT\n',
    "k_path.py": 'from pathlib import Path\ndef go():\n    d = requests.get("https://api.acme.example/f").json()\n    return Path(d["file"]).read_text()  # HIT\n',
    "k_send_file.py": 'def go():\n    d = requests.get("https://api.acme.example/f").json()\n    return send_file(d["name"])  # HIT\n',
    "k_popen.py": 'import os\ndef go():\n    t = requests.get("https://api.acme.example/t").text\n    return os.popen(f"cat {t}")  # HIT\n',
    "k_sh_c.py": 'import subprocess\ndef go():\n    d = requests.get("https://api.acme.example/j").json()\n    subprocess.run(["sh", "-c", d["cmd"]])  # HIT\n',
}
PY_NEG = {
    "n_int.py": 'def load():\n    r = requests.get("https://api.acme.example/p")\n    return r.json()\n\ndef go(cur):\n    p = load()\n    cur.execute("SELECT %d" % int(p["n"]))\n',
    "n_coerce.py": 'def go(cur):\n    d = requests.get("https://api.acme.example/p").json()\n    n = as_count(d["n"])\n    cur.execute(f"SELECT {n}")\n',
    "n_hash.py": 'import hashlib\ndef go():\n    d = requests.get("https://api.acme.example/f").json()\n    h = hashlib.sha256(d["name"].encode()).hexdigest()\n    return open("/srv/" + h)\n',
    "n_constmap.py": 'COLS = {"a": "col_a"}\ndef go(cur):\n    d = requests.get("https://api.acme.example/p").json()\n    cur.execute(f"SELECT {COLS[d[\'k\']]} FROM t")\n',
    "n_urlcheck.py": 'from urllib.parse import urlparse\ndef go():\n    d = requests.get("https://api.acme.example/p").json()\n    h = urlparse(d["u"]).hostname\n    if h != "files.acme.example":\n        return None\n    return requests.get(d["u"])\n',
    "n_nohelper.py": 'def load():\n    return open("/etc/app.json").read()\n\ndef go(cur):\n    p = load()\n    cur.execute("SELECT " + p)\n',
    "n_literal_wrap.py": 'import subprocess\ndef run(cmd):\n    return subprocess.run(cmd, shell=True)\n\ndef go():\n    requests.get("https://api.acme.example/job").json()\n    run("make all")\n',
    "n_wrap_quote.py": 'import subprocess, shlex\ndef run(cmd):\n    return subprocess.run(cmd, shell=True)\n\ndef go():\n    j = requests.get("https://api.acme.example/job").json()\n    run("make " + shlex.quote(j["target"]))\n',
    "n_client_literal.py": 'import httpx\ndef go():\n    with httpx.Client() as client:\n        d = client.get("https://api.acme.example/p").json()\n        return client.get("https://api.acme.example/q/" + d["id"])\n',
    "n_tls_ok.py": 'import jwt\ndef go(s, t):\n    s.get("https://api.acme.example/p", verify="/etc/ca.pem")\n    return jwt.decode(t, key, verify=False)\n',
}
PY_TLS = {
    "t_attr_session.py": 'class C:\n    def go(self):\n        return self.session.get("https://api.acme.example/p", timeout=3, verify=False)  # HIT\n',
    "t_client_var.py": 'def go(client):\n    return client.post("https://api.acme.example/p", json={}, verify=False)  # HIT\n',
    "t_pool.py": 'import urllib3\nhttp = urllib3.PoolManager(cert_reqs="CERT_NONE")  # HIT\n',
    "t_pool_ssl.py": 'import ssl, urllib3\nhttp = urllib3.PoolManager(cert_reqs=ssl.CERT_NONE)  # HIT\n',
    "t_httpx_ctor.py": 'import httpx\nc = httpx.AsyncClient(timeout=5, verify=False)  # HIT\n',
}
JS_POS = {
    "h_fetch.js": 'async function load(id) {\n  const res = await fetch(`https://api.acme.example/p/${id}`);\n  if (!res.ok) throw new Error("x");\n  return res.json();\n}\nasync function go(db, id) {\n  const p = await load(id);\n  await db.query("DELETE FROM t WHERE k = \'" + p.key + "\'");  // HIT\n}\n',
    "h_destructure.js": 'const fs = require("fs");\nasync function load() {\n  const { data } = await axios.get("https://api.acme.example/f");\n  return data;\n}\nasync function go() {\n  const d = await load();\n  fs.writeFileSync(d.target, "x");  // HIT\n}\n',
    "h_arrow.js": 'const load = async () => {\n  const r = await axios.get("https://api.acme.example/f");\n  return r.data;\n};\nasync function go(db) {\n  const d = await load();\n  await db.execute(`SELECT * FROM ${d.table}`);  // HIT\n}\n',
    "h_method.js": 'const { exec } = require("child_process");\nclass Jobs {\n  async load() {\n    const r = await this.client.get("https://api.acme.example/j");\n    return r.data;\n  }\n  async run() {\n    const j = await this.load();\n    exec("make " + j.target);  // HIT\n  }\n}\n',
    "h_then.js": 'function load() {\n  return axios.get("https://api.acme.example/j").then((r) => r.data);\n}\nasync function go() {\n  const j = await load();\n  return fetch(j.callback);  // HIT\n}\n',
    "h_expr.js": 'async function load() {\n  return (await axios.get("https://api.acme.example/j")).data;\n}\nasync function go(db) {\n  const j = await load();\n  await db.query(`SELECT ${j.col}`);  // HIT\n}\n',
    "w_shell.js": 'const { exec } = require("child_process");\nfunction sh(cmd) {\n  return new Promise((ok, bad) => {\n    exec(cmd, (e, out) => (e ? bad(e) : ok(out)));\n  });\n}\nasync function go() {\n  const { data } = await axios.get("https://api.acme.example/j");\n  return sh(`tar xf ${data.file}`);  // HIT\n}\n',
    "w_arrow.js": 'const { execSync } = require("child_process");\nconst run = (c) => execSync(c);\nasync function go() {\n  const { data } = await axios.get("https://api.acme.example/j");\n  run("make " + data.target);  // HIT\n}\n',
    "k_instance.js": 'const { exec } = require("child_process");\nconst api = axios.create({ baseURL: "https://api.acme.example" });\nasync function go() {\n  const { data } = await api.get("/j");\n  exec("make " + data.target);  // HIT\n}\n',
    "k_instance_data.js": 'const fs = require("fs");\nasync function go(apiClient) {\n  const r = await apiClient.get("/f");\n  fs.unlinkSync(r.data.file);  // HIT\n}\n',
    "k_promises.js": 'const fs = require("fs");\nasync function go() {\n  const res = await fetch("https://api.acme.example/f");\n  const f = await res.json();\n  return fs.promises.readFile(f.path);  // HIT\n}\n',
    "k_execsync.js": 'const cp = require("child_process");\nasync function go() {\n  const res = await fetch("https://api.acme.example/j");\n  const j = await res.json();\n  cp.execSync(`git clone ${j.url}`);  // HIT\n}\n',
}
JS_NEG = {
    "n_int.js": 'async function load() {\n  const r = await axios.get("https://api.acme.example/p");\n  return r.data;\n}\nasync function go(db) {\n  const p = await load();\n  await db.query(`SELECT ${parseInt(p.n, 10)}`);\n}\n',
    "n_coerce.js": 'async function go(db) {\n  const { data } = await axios.get("https://api.acme.example/p");\n  const n = asCount(data.n);\n  await db.query("SELECT " + n);\n}\n',
    "n_hash.js": 'const fs = require("fs");\nconst crypto = require("crypto");\nasync function go() {\n  const { data } = await axios.get("https://api.acme.example/f");\n  const h = crypto.createHash("sha256").update(data.name).digest("hex");\n  fs.readFileSync("/srv/" + h);\n}\n',
    "n_constmap.js": 'const COLS = { a: "col_a" };\nasync function go(db) {\n  const { data } = await axios.get("https://api.acme.example/p");\n  await db.query(`SELECT ${COLS[data.k]} FROM t`);\n}\n',
    "n_urlcheck.js": 'async function go() {\n  const { data } = await axios.get("https://api.acme.example/p");\n  const u = new URL(data.u);\n  if (u.hostname !== "files.acme.example") throw new Error("host");\n  return fetch(u.toString());\n}\n',
    "n_nohelper.js": 'const fs = require("fs");\nfunction load() {\n  return JSON.parse(fs.readFileSync("/etc/app.json", "utf8"));\n}\nasync function go(db) {\n  const p = load();\n  await db.query("SELECT " + p.col);\n}\n',
    "n_literal_wrap.js": 'const { exec } = require("child_process");\nfunction sh(cmd) {\n  exec(cmd);\n}\nasync function go() {\n  await axios.get("https://api.acme.example/j");\n  sh("make all");\n}\n',
    "n_instance_literal.js": 'const api = axios.create({ baseURL: "https://api.acme.example" });\nasync function go() {\n  const { data } = await api.get("/j");\n  return fetch("https://api.acme.example/q/" + encodeURIComponent(data.id));\n}\n',
    "n_tls_ok.js": 'const a = new https.Agent({ rejectUnauthorized: true });\nconst env = { NODE_TLS_REJECT_UNAUTHORIZED: "1" };\n',
}
JS_TLS = {
    "t_env_obj.js": 'const child = spawn("node", ["x.js"], { env: { ...process.env, NODE_TLS_REJECT_UNAUTHORIZED: "0" } });  // HIT\n',
    "t_zero.js": 'const agent = new https.Agent({ rejectUnauthorized: 0 });  // HIT\n',
    "t_got.js": 'const r = await got("https://api.acme.example/p", { https: { rejectUnauthorized: false } });  // HIT\n',
}


def marked(files):
    return {(n, i + 1) for n, b in files.items() for i, ln in enumerate(b.splitlines()) if ln.rstrip().endswith("# HIT") or ln.rstrip().endswith("// HIT")}


class Api10V2(unittest.TestCase):
    def check(self, cfg, pos, neg, rule):
        rows = {(f, line) for f, line, r in semgrep_hits(cfg, tree({**pos, **neg})) if r.endswith(rule)}
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
        self.assertGreaterEqual((len(PY_POS), len(PY_NEG), len(JS_POS), len(JS_NEG), len(PY_TLS), len(JS_TLS)), (10, 8, 10, 8, 3, 3))


if __name__ == "__main__":
    unittest.main()
