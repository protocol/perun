#!/usr/bin/env python3
"""Tests for the bundled insecure-default rules in templates/semgrep-taint/defaults.yml.

Each rule has seeded bad fixtures marked `ruleid: <id>` on the line before and a clean twin that must stay silent: recall 100%, zero hits
on the twins. The live check needs semgrep and prints SKIP without it (CI installs none). All names and values are fictional."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint", "defaults.yml")
src = open(CFG).read()
IDS = [l.split("id: ")[1] for l in src.splitlines() if l.startswith("- id: ")]
assert len(IDS) == 9 and src.count("  severity: ") == 9, IDS

BAD_PY = '''import jwt
from flask_cors import CORS
# ruleid: perun.py.debug-enabled
DEBUG = True
# ruleid: perun.py.debug-enabled
app.run(host="0.0.0.0", debug=True)
# ruleid: perun.py.cors-credentials-wildcard
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)
# ruleid: perun.py.cors-credentials-wildcard
CORS(app, origins="*", supports_credentials=True)
# ruleid: perun.py.jwt-unverified
jwt.decode(tok, options={"verify_signature": False})
# ruleid: perun.py.jwt-unverified
jwt.decode(tok, key, algorithms=["HS256", "none"])
# ruleid: perun.py.jwt-unverified
jwt.encode(claims, None, algorithm="none")
def add_cors(resp):
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin")
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    return resp
def add_cors_django(resp):
    resp["Access-Control-Allow-Credentials"] = "true"
    # ruleid: perun.py.cors-reflected-origin
    resp["Access-Control-Allow-Origin"] = request.META["HTTP_ORIGIN"]
    return resp
def cors_set(resp):
    resp.headers["Access-Control-Allow-Credentials"] = True
    # ruleid: perun.py.cors-reflected-origin
    resp.headers.set("Access-Control-Allow-Origin", request.headers.get("Origin"))
    return resp
def cors_lower(resp):
    resp.headers["access-control-allow-credentials"] = "true"
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["access-control-allow-origin"] = request.headers.get("origin")
    return resp
def decode_opts(tok, key):
    opts = {"verify_signature": False}
    # ruleid: perun.py.jwt-unverified
    return jwt.decode(tok, key, options=opts)
def decode_dict_call(tok, key):
    # ruleid: perun.py.jwt-unverified
    return jwt.decode(tok, key, options=dict(verify_signature=False))
def decode_complete(tok, key):
    # ruleid: perun.py.jwt-unverified
    return jwt.decode_complete(tok, key, options={"verify_signature": False})
def decode_complete_var(tok, key):
    opts = dict(verify_signature=False)
    # ruleid: perun.py.jwt-unverified
    return jwt.decode_complete(tok, key, options=opts)
def cors_update(resp):
    # ruleid: perun.py.cors-reflected-origin
    resp.headers.update({"Access-Control-Allow-Origin": request.headers.get("Origin"), "Access-Control-Allow-Credentials": "true"})
    return resp
def is_authenticated(tok):
    # ruleid: perun.py.auth-fails-open
    try:
        check(tok)
    except Exception:
        log.warning("auth backend down")
        return True
    return False
'''
CLEAN_PY = '''import os, jwt
from flask_cors import CORS
DEBUG = os.environ.get("ACME_DEBUG") == "1"
app.run(host="127.0.0.1", debug=False)
app.add_middleware(CORSMiddleware, allow_origins=["https://app.example.com"], allow_credentials=True)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False)
CORS(app, origins="https://app.example.com", supports_credentials=True)
jwt.decode(tok, key, algorithms=["HS256"])
jwt.decode(tok, options={"verify_signature": True})
jwt.encode(claims, key, algorithm="HS256")
def add_cors(resp):
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        resp.headers["Access-Control-Allow-Origin"] = origin
        resp.headers["Access-Control-Allow-Credentials"] = "true"
    return resp
def add_const_cors(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    resp.headers.set("Access-Control-Allow-Origin", "https://app.example.com")
    return resp
def decode_opts_verified(tok, key):
    opts = {"verify_signature": True}
    return jwt.decode(tok, key, algorithms=["HS256"], options=opts)
def decode_dict_verified(tok, key):
    return jwt.decode(tok, key, algorithms=["HS256"], options=dict(verify_signature=True))
def update_const_cors(resp):
    resp.headers.update({"Access-Control-Allow-Origin": "https://app.example.com", "Access-Control-Allow-Credentials": "true"})
    return resp
def add_public_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin")
    return resp
def is_authenticated(tok):
    try:
        check(tok)
    except Exception:
        return False
    return True
def parse_number(s):
    try:
        return int(s)
    except ValueError:
        return True
'''
BAD_CORS_DJANGO = '''# ruleid: perun.py.cors-credentials-wildcard
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
'''
CLEAN_CORS_DJANGO = '''CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = False
'''
BAD_JS = '''// ruleid: perun.js.jwt-decode-unverified
const claims = jwt.decode(tok);
// ruleid: perun.js.jwt-decode-unverified
const claims2 = require("jsonwebtoken").decode(tok);
// accepted noise: decode then verify the same token (a kid lookup) is still reported
function kidThenVerify(tok, keys) {
  // ruleid: perun.js.jwt-decode-unverified
  const kid = jwt.decode(tok, { complete: true }).header.kid;
  return jwt.verify(tok, keys[kid], { algorithms: ["HS256"] });
}
function verifyOtherToken(a, b) {
  // ruleid: perun.js.jwt-decode-unverified
  const c = jwt.decode(a);
  return jwt.verify(b, key);
}
function decodeBeforeVerify(t, other) {
  // ruleid: perun.js.jwt-decode-unverified
  const c = jwt.decode(t);
  jwt.verify(other, key);
  return c;
}
function verifyDead(t) {
  if (false) { jwt.verify(t, key); }
  // ruleid: perun.js.jwt-decode-unverified
  return jwt.decode(t);
}
function unrelatedVerify(t, v) {
  v.verify(x);
  // ruleid: perun.js.jwt-decode-unverified
  return jwt.decode(t);
}
function koaCors(ctx) {
  ctx.set("Access-Control-Allow-Credentials", "true");
  // ruleid: perun.js.cors-reflected-origin
  ctx.set("Access-Control-Allow-Origin", ctx.request.headers.origin);
}
function objectCors(req, res) {
  // ruleid: perun.js.cors-reflected-origin
  res.set({ "Access-Control-Allow-Origin": req.headers.origin, "Access-Control-Allow-Credentials": "true" });
}
class Session {
  check(t) {
    // ruleid: perun.js.jwt-decode-unverified
    return this.jwt.decode(t);
  }
}
function corsA(req, res) {
  res.header("Access-Control-Allow-Credentials", "true");
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", req.headers.origin);
}
const corsB = (req, res) => {
  res.set("Access-Control-Allow-Credentials", true);
  // ruleid: perun.js.cors-reflected-origin
  res.set("access-control-allow-origin", req.get("origin"));
};
// ruleid: perun.js.jwt-unverified
jwt.verify(tok, key, { algorithms: ["HS256", "none"] });
// ruleid: perun.js.jwt-unverified
jwt.sign(claims, "", { algorithm: "none" });
async function verifyToken(req, res, next) {
  // ruleid: perun.js.auth-fails-open
  try {
    await check(req.headers.authorization);
    return next();
  } catch (e) {
    log(e);
    return next();
  }
}
const isAuthorized = (req) => {
  // ruleid: perun.js.auth-fails-open
  try {
    return check(req);
  } catch (e) {
    return true;
  }
};
'''
CLEAN_JS = '''jwt.verify(tok, key, { algorithms: ["HS256"] });
j.decode(tok);
jwt2.decode(tok);
function constOrigin(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  res.setHeader("Access-Control-Allow-Origin", "https://app.example.com");
}
function constObject(res) {
  res.set({ "Access-Control-Allow-Origin": "https://app.example.com", "Access-Control-Allow-Credentials": "true" });
}
jwt.sign(claims, key, { algorithm: "HS256" });
async function verifyToken(req, res, next) {
  try {
    await check(req.headers.authorization);
    return next();
  } catch (e) {
    return res.status(401).end();
  }
}
const parseBody = (req) => {
  try {
    return JSON.parse(req.body);
  } catch (e) {
    return true;
  }
};
'''
BAD = {"app/bad.py": BAD_PY, "app/bad_cors.py": BAD_CORS_DJANGO, "app/bad.js": BAD_JS, "app/bad.ts": BAD_JS}
CLEAN = {"app/clean.py": CLEAN_PY, "app/clean_cors.py": CLEAN_CORS_DJANGO, "app/clean.js": CLEAN_JS, "app/clean.ts": CLEAN_JS}
SKIPPED = {"tests/bad.py": BAD_PY, "app/bad.spec.ts": BAD_JS}

if not shutil.which("semgrep"):
    print("SKIP: semgrep not installed; the live fixture check did not run")
    sys.exit(0)
d = tempfile.mkdtemp()
try:
    want = set()
    for rel, text in {**BAD, **CLEAN, **SKIPPED}.items():
        p = os.path.join(d, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w").write(text)
    for rel, text in BAD.items():
        lines = text.splitlines()
        want |= {(rel, i + 2, l.split("ruleid: ")[1]) for i, l in enumerate(lines) if "ruleid: " in l}
    run = subprocess.run(["semgrep", "--config", CFG, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "."],
                         cwd=d, capture_output=True, text=True)
    out = json.loads(run.stdout)
    got = {(r["path"], r["start"]["line"], re.search(r"perun\.(?:py|js)\..*$", r["check_id"])[0]) for r in out["results"]}
    # a multi-line try is reported at its first line; the annotation sits on the line before it
    assert got == want, f"missing {sorted(want - got)} extra {sorted(got - want)}"
    ids = {i for _, _, i in got}
    assert ids == set(IDS), f"rules without a bad fixture: {set(IDS) - ids}"
finally:
    shutil.rmtree(d)
print(f"ok: {len(want)} bad findings, 0 on clean twins and test paths")
