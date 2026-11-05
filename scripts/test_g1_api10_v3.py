#!/usr/bin/env python3
"""G1 API10:2023 detector v3 (perun.{py,js}.unsafe-api-consumption, perun.{py,js}.tls-verify-off).

Fixes beyond v2, each with seeded positives and near-miss negatives:
- a multi-line client call is reported at the line of the unsafe argument (verify=False, cert_reqs, ssl=False);
- promisify(exec) / util.promisify(exec) wrappers are shell sinks at their call sites;
- a request URL built from a function parameter is not response-derived: a destructured { data } source covers
  the binding, not the request expression that contains the URL;
- a same-file validator helper (a def whose raising `if` tests its parameter or a local derived from it with commonpath,
  is_relative_to, fullmatch, match, isalnum, isdigit or isalpha) sanitizes its result, while a type-only, startswith or
  unrelated guard and a status-check raise do not;
- a renamed { data: alias } destructure still sources the alias;
- promisify(exec) is a sink only when exec comes from child_process;
- a request URL taken from a response body stays a positive.
A line ending in the HIT marker must be flagged by the named rule; every other line must stay silent. Fictional
names only. A missing semgrep skips, never passes.
Known uncovered: a helper defined in another file of the same case (OSS semgrep taint is single-file).
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_g1_api10_v2 import marked  # noqa: E402
from test_g1_api_pilot_a import semgrep_hits, tree  # noqa: E402

UAC, TLS = "unsafe-api-consumption", "tls-verify-off"

_META = 'import os, re, requests\nROOT = "/srv"\n\n\ndef meta(a):\n    r = requests.get(f"https://api.acme.example/m/{a}")\n    r.raise_for_status()\n    return r.json()\n\n\n'
# guard condition -> kept token (clears) or None (must stay positive); each guard tests the helper parameter or a local derived from it
_GUARDS = {
    "commonpath": 'os.path.commonpath([ROOT, c]) != ROOT',
    "is_relative_to": 'not Path(c).is_relative_to(ROOT)',
    "fullmatch": 'not re.fullmatch(r"[a-z.]+", name)',
    "match": 'not re.match(r"[a-z]+$", name)',
    "isalnum": 'not name.isalnum()',
    "isdigit": 'not name.isdigit()',
    "isalpha": 'not name.isalpha()',
}
_POS_GUARDS = {
    "isinstance": 'not isinstance(name, str)',
    "startswith": 'name.startswith("x")',
    "status": 'name == "zzz"',
}


def _validator(guard):
    return _META + f'def chk(name):\n    c = os.path.realpath(os.path.join(ROOT, name))\n    if {guard}:\n        raise ValueError("no")\n    return c\n\n\ndef go(a):\n    m = meta(a)\n    with open(chk(m["name"]), "wb") as fh:\n        fh.write(b"x")\n'


PY_POS = {
    "h_url_from_body.py": 'import requests\ndef go(a):\n    m = requests.get(f"https://api.acme.example/m/{a}").json()\n    return requests.get(m["download_url"]).content  # HIT\n',
    "h_status_helper.py": 'import os, requests\ndef meta(a):\n    r = requests.get(f"https://api.acme.example/m/{a}")\n    if r.status_code != 200:\n        raise RuntimeError("bad")\n    return r.json()\n\ndef go(a):\n    m = meta(a)\n    return open(os.path.join("/srv", m["name"]))  # HIT\n',
}
for _k, _g in _POS_GUARDS.items():
    PY_POS[f"h_guard_{_k}.py"] = _validator(_g).replace('    with open(chk(m["name"]), "wb") as fh:', '    with open(chk(m["name"]), "wb") as fh:  # HIT')
PY_NEG = {
    "n_tls_multiline.py": 'import httpx\nc = httpx.Client(\n    base_url="https://api.acme.example",\n    verify="/etc/ca.pem",\n)\n',
}
for _k, _g in _GUARDS.items():
    PY_NEG[f"n_guard_{_k}.py"] = _validator(_g)
PY_TLS = {
    "t_multiline.py": 'import httpx\nc = httpx.Client(\n    base_url="https://api.acme.example",\n    verify=False,  # HIT\n    timeout=5,\n)\n',
    "t_multiline_cert.py": 'import urllib3\nhttp = urllib3.PoolManager(\n    timeout=5,\n    cert_reqs="CERT_NONE",  # HIT\n)\n',
    "t_multiline_ssl.py": 'import aiohttp\nc = aiohttp.TCPConnector(\n    limit=5,\n    ssl=False,  # HIT\n)\n',
}
JS_POS = {
    "h_promisify.js": 'const { exec } = require("child_process");\nconst { promisify } = require("util");\nconst run = promisify(exec);\nasync function go(p) {\n  const { data } = await axios.get(`${B}/p/${p}`);\n  return run(`tar -xf ${data.name}`);  // HIT\n}\n',
    "h_util_promisify.js": 'const util = require("util");\nconst { exec } = require("child_process");\nconst run = util.promisify(exec);\nasync function go() {\n  const res = await axios(`${B}/x`);\n  const { data } = await axios.get(`${B}/m`);\n  return run(`ls ${data.dir}`);  // HIT\n}\n',
    "h_alias.js": 'async function go() {\n  const { data: d2 } = await axios.get(`${B}/m`);\n  return fs.readFileSync(d2.p);  // HIT\n}\n',
    "h_alias_direct.js": 'async function go() {\n  const { data: d3 } = await axios(`${B}/m`);\n  return fs.readFileSync(d3.p);  // HIT\n}\n',
    "h_chain_in_destructure.js": 'async function go() {\n  const { data: a } = await axios.get(`${B}/m`);\n  const { data: b } = await axios.get(`${a.base}/x`);  // HIT\n  return b;\n}\n',
    "h_import_promisify.js": 'import { exec } from "child_process";\nimport { promisify } from "util";\nconst run = promisify(exec);\nasync function go() {\n  const { data } = await axios.get(`${B}/m`);\n  return run(`ls ${data.dir}`);  // HIT\n}\n',
    "h_cp_promisify.js": 'const cp = require("child_process");\nconst run = require("util").promisify(cp.exec);\nconst run2 = util.promisify(cp.exec);\nasync function go() {\n  const { data } = await axios.get(`${B}/m`);\n  return run2(`ls ${data.dir}`);  // HIT\n}\n',
    "h_url_from_body.js": 'async function go() {\n  const { data } = await axios.get(`${B}/m`);\n  return axios.get(data.url);  // HIT\n}\n',
}
JS_NEG = {
    "n_url_param.js": 'async function latest(project) {\n  const { data } = await axios.get(`${B}/projects/${project}/latest`, { timeout: 8000 });\n  return data;\n}\n',
    "n_url_param_direct.js": 'async function latest(project) {\n  const { data } = await axios(`${B}/projects/${project}/latest`);\n  return data;\n}\n',
    "n_promisify_execfile.js": 'const { execFile } = require("child_process");\nconst { promisify } = require("util");\nconst run = promisify(execFile);\nasync function go() {\n  const { data } = await axios.get(`${B}/m`);\n  return run("tar", ["-xf", data.name]);\n}\n',
    "n_promisify_local_exec.js": 'const { exec } = require("./db");\nconst { promisify } = require("util");\nconst run = promisify(exec);\nasync function go() {\n  const { data } = await axios.get(`${B}/m`);\n  return run(data.q);\n}\n',
    "n_alias_url_param.js": 'async function latest(project) {\n  const { data: d } = await axios.get(`${B}/projects/${project}/latest`);\n  return d;\n}\n',
    "n_promisify_lit.js": 'const { exec } = require("child_process");\nconst run = require("util").promisify(exec);\nasync function go() {\n  return run("uptime");\n}\n',
}


class Api10V3(unittest.TestCase):
    def check(self, cfg, pos, neg, rule):
        rows = {(f, line) for f, line, r in semgrep_hits(cfg, tree({**pos, **neg})) if r.endswith(rule)}
        self.assertEqual(rows, marked(pos))

    def test_py_unsafe_consumption(self):
        self.check("py.yml", PY_POS, PY_NEG, UAC)

    def test_py_tls_multiline_reported_at_argument(self):
        self.check("py.yml", PY_TLS, PY_NEG, TLS)

    def test_js_unsafe_consumption(self):
        self.check("js.yml", JS_POS, JS_NEG, UAC)

    def test_no_duplicate_reports_with_sqli(self):
        for cfg, groups in (("py.yml", (PY_POS, PY_NEG, PY_TLS)), ("js.yml", (JS_POS, JS_NEG))):
            by = {}
            for f, line, r in semgrep_hits(cfg, tree({k: v for g in groups for k, v in g.items()})):
                by.setdefault((f, line), set()).add(r.rsplit(".", 1)[-1])
            self.assertEqual({k: v for k, v in by.items() if v & {UAC, TLS} and "sqli" in v}, {}, cfg)


if __name__ == "__main__":
    unittest.main()
