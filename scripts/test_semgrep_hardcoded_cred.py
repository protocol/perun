#!/usr/bin/env python3
"""Tests for the bundled semgrep hardcoded-credential rules (js.yml, py.yml). Lines tagged HIT must be flagged, all others must stay clean. Plain asserts; needs semgrep, else prints SKIP (also in CI, which installs none)."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")

# The shared name and literal regexes live in both rule files; they must not drift.
src = [open(os.path.join(RULES, f)).read() for f in ("js.yml", "py.yml")]
for pat, n in ((r"regex: (\^\(\?:\(\?:\.\*\[\._\].+)", 1), (r"regex: (\^\(\?!\(\?i:bearer.+)", 2)):
    rx = [re.findall(pat, s) for s in src]
    assert len(rx[0]) == n and rx[0] == rx[1], rx

JS = '''function gate(req, res, next, password, config, bypass, tokenType, type, body, token, secret, pwd, PWD, parts) {
  const [user, pass] = Buffer.from(req.headers.authorization.split(" ")[1], "base64").toString().split(":");
  if (pass === "example-pass-1") return next(); // HIT decoded Basic credential
  const creds = atob(req.headers.authorization.slice(6));
  if (creds !== "jane:example-pass-1") return res.end(); // HIT decoded pair vs literal
  if (password == 'example-pass-2') {} // HIT
  if (req.body.password === "example-pass-3") {} // HIT
  if ("example-key" !== config.apiKey) {} // HIT
  if (ADMIN_PASSWORD === "example-pass-4") {} // HIT
  if (this.authToken != "example-token") {} // HIT
  if (body["secret"] === "example-secret") {} // HIT
  if (req.query.get("token") === "example-token") {} // HIT
  if (password.toLowerCase() === "example-pass-5") {} // HIT wrapped
  if ("example-pass-6" == token.trim()) {} // HIT wrapped, literal first
  if (password === "") {}
  if (password === process.env.APP_PASSWORD) {}
  if (process.env.APP_TOKEN === "example-token" || process.env["PWD"] === "/" || process.env.PWD == "/") {}
  if (token === "(" || token === "-" || password === "a") {}
  if (token === "bearer" || token === "Basic" || password === "None" || token == "null" || token === "undefined" || secret === "true" || secret !== "false") {}
  if (pwd === "/" || PWD === "/" || config.pwd !== "/") {}
  const hdr = JSON.parse(atob(parts[0]));
  if (hdr.alg === "none" || hdr.alg === "None" || hdr.alg !== "HS256" || hdr["typ"] !== "JWT") {}
  if (bypass === "yes" || tokenType === "bearer" || type === "password") {}
  if (typeof password === "string") {}
  const [scheme] = req.headers.authorization.split(" ");
  if (scheme !== "Basic") {}
  if (Buffer.from(user, "base64").toString() === "") {}
}
'''
PY = '''import base64, json, os
def gate(request, password, bypass, token_type, token, pwd, PWD, hmac, secrets):
    user, pw = base64.b64decode(request.headers["Authorization"][6:]).decode().split(":", 1)
    if pw == "example-pass-1":  # HIT decoded Basic credential
        return 1
    if base64.b64decode(request.data) != b"jane:example-pass-1":  # HIT bytes literal
        return 1
    if password == "example-pass-2":  # HIT
        return 1
    if request.form["password"] != "example-pass-3":  # HIT
        return 1
    if self.api_key == "example-key":  # HIT
        return 1
    if "example-secret" == SECRET:  # HIT
        return 1
    if request.args.get("token") == "example-token":  # HIT
        return 1
    if hmac.compare_digest(password, "example-pass-5"):  # HIT
        return 1
    if secrets.compare_digest("example-pass-6", token):  # HIT literal first
        return 1
    if compare_digest(token, "example-token-7"):  # HIT bare import
        return 1
    if password.strip() == "example-pass-8" or token.lower() != "example-token-9":  # HIT wrapped
        return 1
    if self.db_pwd == "example-pass-10":  # HIT
        return 1
    if password == "":
        return 1
    if password == os.environ.get("APP_PASSWORD"):
        return 1
    if os.environ.get("PWD") == "/" or os.environ["TOKEN"] == "example-token" or os.getenv("TOKEN") == "example-token":
        return 1
    if token == "(" or token == "-" or password == "a":
        return 1
    if token == "bearer" or token == "Basic" or password == "None" or token == "null" or password == "undefined" or token == "True" or token != "false":
        return 1
    if pwd == "/" or PWD == "/" or os.pwd != "/":
        return 1
    if hmac.compare_digest(password, os.environ["APP_PASSWORD"]) or hmac.compare_digest(token, ""):
        return 1
    hdr = json.loads(base64.urlsafe_b64decode(token.split(".")[0]))
    if hdr["alg"] == "none" or hdr["alg"] != "HS256":
        return 1
    if bypass == "yes" or token_type == "bearer":
        return 1
    if request.headers["Authorization"].split()[0] != "Basic":
        return 1
'''
FILES = {"app/gate.ts": JS, "app/gate.py": PY, "tests/gate.ts": JS, "app/gate.spec.ts": JS,
         "app/test_gate.py": PY, "app/gate_test.py": PY, "app/__tests__/gate.js": JS, "fixtures/gate.py": PY}

if not shutil.which("semgrep"):  # CI installs no semgrep (ci.yml pip-installs only hypothesis), so this skips there too
    print("SKIP: semgrep not installed; the regex-identity check ran, the live-rule check did not")
    sys.exit(0)
d = tempfile.mkdtemp()
want = set()
for p, body in FILES.items():
    os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
    open(os.path.join(d, p), "w").write(body)
    if p in ("app/gate.ts", "app/gate.py"):
        want |= {(p, i) for i, l in enumerate(body.split("\n"), 1) if "HIT" in l}
env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
p = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", *FILES], capture_output=True, text=True, env=env, cwd=d)
r = json.loads(p.stdout)
assert not r["errors"], r["errors"]
got = {(x["path"], x["start"]["line"]) for x in r["results"] if "hardcoded" in x["check_id"]}
assert got == want, (sorted(got - want), sorted(want - got))
assert {x["check_id"].rsplit(".", 1)[1] for x in r["results"]} >= {"hardcoded-basic-auth", "hardcoded-credential-compare"}
shutil.rmtree(d)
print("ok")
