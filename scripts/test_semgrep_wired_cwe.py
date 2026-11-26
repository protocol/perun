#!/usr/bin/env python3
"""Tests for the source-to-sink rules that back the wired CWE-94, CWE-502 and CWE-434 rows of references/standards-coverage.md:
perun.js.code-injection, perun.py.code-injection (CWE-94), perun.js.deserialize-untrusted (CWE-502; the Python side is
perun.py.deserialize, probed by bench/class-seeds/vuln/cwe502.py) and perun.js.unrestricted-upload, perun.py.unrestricted-upload (CWE-434).
Each rule has positive cases and clean twins (a constant, a data parser, an extension check in the same function).

Fixtures are annotated like semgrep's own tests: `// ruleid: <id>` (or `# ruleid: <id>`) marks the NEXT line as a required finding, and every
unannotated line must stay free of these rules. All names are fictional. RULES=<dir> checks another copy of the rules. The live check needs semgrep:
it prints SKIP and exits 0 without it, unless REQUIRE_SEMGREP=1, which fails instead. The offline pins always run. Plain asserts."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
IDS = {"perun.js.code-injection": "CWE-94", "perun.py.code-injection": "CWE-94", "perun.js.deserialize-untrusted": "CWE-502",
       "perun.js.unrestricted-upload": "CWE-434", "perun.py.unrestricted-upload": "CWE-434"}

JS = '''const express = require("express");
const vm = require("vm");
const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");
const serialize = require("node-serialize");
const app = express();

app.get("/calc", (req, res) => {
  // ruleid: perun.js.code-injection
  res.send(String(eval(req.query.expr)));
});
app.post("/fn", (req, res) => {
  // ruleid: perun.js.code-injection
  const f = new Function("x", req.body.code);
  res.send(String(f(1)));
});
app.post("/vm", (req, res) => {
  // ruleid: perun.js.code-injection
  res.send(String(vm.runInNewContext(req.body.script, {})));
});
app.get("/clean-code", (req, res) => {
  const two = eval("1 + 1");
  res.json({ two, parsed: JSON.parse(req.query.expr) });
});

app.post("/ser", (req, res) => {
  // ruleid: perun.js.deserialize-untrusted
  res.json(serialize.unserialize(req.body.blob));
});
app.post("/yaml", (req, res) => {
  // ruleid: perun.js.deserialize-untrusted
  res.json(yaml.load(req.body.doc));
});
app.post("/clean-ser", (req, res) => {
  res.json(JSON.parse(req.body.blob));
  res.json(yaml.safeLoad(req.body.doc));
  res.json(serialize.unserialize("{}"));
});

app.post("/up-mv", (req, res) => {
  // ruleid: perun.js.unrestricted-upload
  req.files.doc.mv(path.join("/srv/up", req.files.doc.name), () => res.end());
});
app.post("/up-write", (req, res) => {
  // ruleid: perun.js.unrestricted-upload
  fs.writeFile("/srv/up/" + req.file.originalname, req.file.buffer, () => res.end());
});
app.post("/clean-ext", (req, res) => {
  const doc = req.files.doc;
  const ext = path.extname(doc.name).toLowerCase();
  if (![".pdf", ".png"].includes(ext)) return res.sendStatus(400);
  doc.mv("/srv/up/" + Date.now() + ext, () => res.end());
});
app.post("/clean-fixed", (req, res) => {
  req.files.doc.mv("/srv/up/fixed-name.bin", () => res.end());
});
'''

PY = '''import os
from flask import request

UP = "/srv/up"
OK_EXT = {"png", "pdf"}


def allowed_file(name):
    return "." in name and name.rsplit(".", 1)[1].lower() in OK_EXT


def calc():
    # ruleid: perun.py.code-injection
    return str(eval(request.args["expr"]))


def run():
    # ruleid: perun.py.code-injection
    exec(request.form["code"])


def clean_code():
    return str(eval("1 + 1"))


def up_direct():
    f = request.files["doc"]
    # ruleid: perun.py.unrestricted-upload
    f.save(os.path.join(UP, f.filename))


def up_get():
    f = request.files.get("doc")
    # ruleid: perun.py.unrestricted-upload
    f.save(UP + "/" + f.filename)


def clean_splitext():
    f = request.files["doc"]
    if os.path.splitext(f.filename)[1] not in (".png", ".pdf"):
        return "bad", 400
    f.save(os.path.join(UP, f.filename))


def clean_helper_exit():
    f = request.files["doc"]
    if not allowed_file(f.filename):
        return "bad", 400
    f.save(os.path.join(UP, f.filename))


def clean_generated():
    f = request.files["doc"]
    f.save(os.path.join(UP, "upload.bin"))
'''

FILES = {"app.js": JS, "app.py": PY}


def annotated(body):
    """Return {line number of the annotated NEXT line: id} for `// ruleid: id` or `# ruleid: id` comments."""
    return {i + 2: m.group(1) for i, l in enumerate(body.splitlines()) if (m := re.match(r"\s*(?://|#) ruleid: (\S+)$", l))}


want = {n: annotated(b) for n, b in FILES.items()}
assert [len(v) for v in want.values()] == [7, 4], [len(v) for v in want.values()]
assert {i for v in want.values() for i in v.values()} == set(IDS), "every rule needs a ruleid fixture"

# Offline pins: every rule exists with its CWE metadata, and the CWE-94 and CWE-502 rules share the request sources of the existing rules.
txt = "".join(open(os.path.join(RULES, f)).read() for f in sorted(os.listdir(RULES)) if f.endswith(".yml"))
for i, cwe in IDS.items():
    m = re.search(rf"^- id: {re.escape(i)}\n(.*?)(?=^- id: |\Z)", txt, re.S | re.M)
    assert m and f'cwe: "{cwe}"' in m.group(1), (i, cwe)
assert "eval" not in re.search(r"- id: perun.js.deserialize-untrusted\n(.*?)(?=^- id: )", txt, re.S | re.M).group(1).split("pattern-sinks:")[1], "eval-type sinks belong to CWE-94"

if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for n, b in FILES.items():
            open(os.path.join(d, n), "w").write(b)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--"] + list(FILES),
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = {n: {} for n in FILES}
    for x in r["results"]:
        m = re.search(r"perun\.(?:js|py)\.(?:code-injection|deserialize-untrusted|unrestricted-upload)$", x["check_id"])
        if not m:
            continue  # another bundled rule firing on a fixture line is not this file's concern
        assert x["extra"]["metadata"]["cwe"] == IDS[m.group(0)], x["extra"]["metadata"]
        got[x["path"]][x["start"]["line"]] = m.group(0)
    assert got == want, ("got", got, "want", want)
    print("semgrep-wired-cwe: live ok")
elif os.environ.get("REQUIRE_SEMGREP") == "1":
    sys.exit("FAIL: semgrep not installed but REQUIRE_SEMGREP=1, so the live check cannot be skipped")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-wired-cwe: ok")
