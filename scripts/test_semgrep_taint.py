#!/usr/bin/env python3
"""Tests for the bundled semgrep taint rules and security_verify.py's native semgrep JSON input (plain asserts)."""
import json, os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SK = os.path.join(ROOT, ".claude", "skills", "deep-code-review")
sys.path.insert(0, os.path.join(SK, "scripts"))
import security_verify as s  # noqa: E402

# 1. Trace mapping (shape per semgrep's CliLoc output: ["CliLoc", [location, content]]).
loc = lambda p, n: {"path": p, "start": {"line": n, "col": 1}}
res = {"results": [
    {"check_id": "r.sqli", "path": "a.py", "start": {"line": 9}, "extra": {"severity": "ERROR", "dataflow_trace": {
        "taint_source": ["CliLoc", [loc("a.py", 3), "x"]], "taint_sink": ["CliLoc", [loc("a.py", 9), "y"]]}}},
    {"check_id": "r.plain", "path": "b.py", "start": {"line": 4}, "extra": {"severity": "INFO"}},
    {"check_id": "r.junk", "path": "c.py", "start": {"line": 1}, "extra": {"dataflow_trace": {"taint_source": "bad"}}},
]}
rows = s.from_semgrep(res)
assert rows[0] == {"rule": "r.sqli", "severity": "high", "sink": "a.py:9", "source": "a.py:3"}, rows[0]
assert rows[1]["sink"] == "b.py:4" and "source" not in rows[1] and rows[1]["severity"] == "low"
assert "source" not in rows[2] and rows[2]["sink"] == "c.py:1"
out = s.triage([{**rows[0], "hunter": "tool", "verifier": "human"}] + rows[1:], set())
assert [r["status"] for r in out] == ["confirmed", "unverified", "unverified"], out
assert s.triage(rows[:1], set())[0]["status"] == "needs_validation", "no verifier recorded"
# CLI accepts the report directly; a non-report object is still rejected.
sv = os.path.join(SK, "scripts", "security_verify.py")
p = subprocess.run([sys.executable, sv, "-", os.devnull], input=json.dumps(res), capture_output=True, text=True)
assert p.returncode == 0 and json.loads(p.stdout)["rows"][0]["status"] == "needs_validation", p.stderr
assert subprocess.run([sys.executable, sv, "-", os.devnull], input="{}", capture_output=True, text=True).returncode == 2

# 2. Bundled rules on a generic mini fixture (needs semgrep; skipped otherwise).
if shutil.which("semgrep"):
    d = tempfile.mkdtemp()
    open(d + "/v.py", "w").write('''import os, pickle, subprocess, requests
ALLOWED = {"example.com"}
def a(q, cur): cur.execute("SELECT 1 WHERE x = '%s'" % q)
def b(h): os.system("ping " + h)
def c(n): return open("/srv/" + n).read()
def d(u): return requests.get(u)
def e(blob): return pickle.loads(blob)
def ok1(cur, q): cur.execute("SELECT 1 WHERE x = ?", (q,))
def ok2(): return os.system("df -h")
def ok3(h):
    if h not in ALLOWED:
        raise ValueError(h)
    return requests.get("https://" + h)
class K:
    def m(self, cur): return cur.execute("SELECT " + self.table)
def n1(): return open(request.args["f"]).read()
def n2(h):
    o = "a"
    if o not in ALLOWED:
        raise ValueError(o)
    return requests.get(h)
''')
    open(d + "/v.js", "w").write('''app.get("/a", (req, res) => { db.query(`SELECT * FROM t WHERE n = '${req.query.n}'`); });
app.get("/b", (req, res) => { exec("convert " + req.query.f); });
app.get("/c", (req, res) => { res.redirect(req.query.next); });
app.get("/ok", (req, res) => { db.query("SELECT 1 WHERE n = $1", [req.query.n]); });
app.get("/ok2", (req, res) => {
  const f = req.query.f;
  if (!FILES.has(f)) return res.status(404).end();
  fs.readFile(path.join(ROOT, f), () => {});
});
app.get("/n1", (req, res) => { m.get(req.query.k); document.body.innerHTML = "a"; });
app.get("/n2", (req, res) => { const u = req.query.u; if (!H.has(u)) { log(); } fetch(u); });
app.get("/ok3", async (req, res) => {
  const u = new URL(req.query.url);
  if (!H.has(u.hostname)) { return res.status(400).end(); }
  await fetch(u);
});
''')
    env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
    p = subprocess.run(["semgrep", "--config", os.path.join(SK, "templates", "semgrep-taint"), "--metrics=off",
                        "--json", "--quiet", d], capture_output=True, text=True, env=env)
    r = json.loads(p.stdout)
    assert not r["errors"], r["errors"]
    hits = sorted((x["path"][-4:], x["start"]["line"]) for x in r["results"])
    want = sorted([("v.py", 3), ("v.py", 4), ("v.py", 5), ("v.py", 6), ("v.py", 7), ("v.py", 16), ("v.py", 21), ("v.js", 1), ("v.js", 2), ("v.js", 3), ("v.js", 11)])
    assert hits == want, hits
    shutil.rmtree(d)
print("ok")
