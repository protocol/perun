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
def cors_default(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = request.headers.get("Origin", "")
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["Access-Control-Allow-Origin"] = o
    return resp
def cors_local(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = request.headers.get("origin")
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["Access-Control-Allow-Origin"] = o
    return resp
def cors_local_set(resp):
    resp["Access-Control-Allow-Credentials"] = "true"
    origin = request.META["HTTP_ORIGIN"]
    # ruleid: perun.py.cors-reflected-origin
    resp.headers.set("Access-Control-Allow-Origin", origin)
    return resp
def cors_fallback(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = ALLOWED_ORIGINS.get(request.headers.get("Origin"), request.headers.get("Origin"))
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["Access-Control-Allow-Origin"] = o
    return resp
def cors_headers_alias(resp):
    h = request.headers
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = h.get("Origin")
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["Access-Control-Allow-Origin"] = o
    return resp
def cors_cred_var(resp):
    t = "true"
    resp.headers["Access-Control-Allow-Credentials"] = t
    o = request.headers.get("Origin")
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["Access-Control-Allow-Origin"] = o
    return resp
def cors_import_alias(resp):
    from flask import request as rq
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = rq.headers.get("Origin")
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["Access-Control-Allow-Origin"] = o
    return resp
def cors_or_fallback(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = request.headers.get("Origin") or "https://app.example.com"
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["Access-Control-Allow-Origin"] = o
    return resp
def cors_lowered(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = request.headers.get("Origin").lower()
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["Access-Control-Allow-Origin"] = o
    return resp
# accepted noise: an `in` allowlist guard is still reported; a single-argument map lookup (clean twin) is not
def cors_guarded(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    origin = request.headers.get("Origin")
    if origin in ALLOWED_ORIGINS:
        # ruleid: perun.py.cors-reflected-origin
        resp.headers["Access-Control-Allow-Origin"] = origin
    return resp
def cors_nested(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = request.headers.get("Origin")
    if o:
        # ruleid: perun.py.cors-reflected-origin
        resp.headers["Access-Control-Allow-Origin"] = o
    return resp
def cors_memo_cache(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = request.headers.get("Origin")
    MEMO[o] = o
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["Access-Control-Allow-Origin"] = MEMO.get(o)
    return resp
def cors_unknown_map(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = LOOKUP.get(request.headers.get("Origin"), request.headers.get("Origin"))
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["Access-Control-Allow-Origin"] = o
    return resp
def cors_fstring(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = request.headers.get("Origin")
    # ruleid: perun.py.cors-reflected-origin
    resp.headers["Access-Control-Allow-Origin"] = f"{o}"
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
ALLOWED_ORIGINS = {"https://app.example.com": "app"}
ALLOWED = {"https://app.example.com": "https://app.example.com"}
app.run(host="127.0.0.1", debug=False)
app.add_middleware(CORSMiddleware, allow_origins=["https://app.example.com"], allow_credentials=True)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False)
CORS(app, origins="https://app.example.com", supports_credentials=True)
jwt.decode(tok, key, algorithms=["HS256"])
jwt.decode(tok, options={"verify_signature": True})
jwt.encode(claims, key, algorithm="HS256")
def add_cors(resp):
    origin = ALLOWED_ORIGINS.get(request.headers.get("Origin"))
    if origin:
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
def cors_local_const(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = request.headers.get("Origin")
    log.info(o)
    resp.headers["Access-Control-Allow-Origin"] = "https://app.example.com"
    return resp
def cors_local_mapped(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = ALLOWED.get(request.headers.get("Origin"))
    resp.headers["Access-Control-Allow-Origin"] = o
    return resp
def cors_local_nocreds(resp):
    o = request.headers.get("Origin")
    resp.headers["Access-Control-Allow-Origin"] = o
    return resp
def cors_reassigned(resp):
    resp.headers["Access-Control-Allow-Credentials"] = "true"
    o = request.headers.get("Origin")
    o = "https://app.example.com"
    resp.headers["Access-Control-Allow-Origin"] = o
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
// ruleid: perun.js.jwt-decode-unverified
const viaBracket = jwt["decode"](tok);
function aliasedDestructure(t) {
  const { decode } = require("jsonwebtoken");
  // ruleid: perun.js.jwt-decode-unverified
  return decode(t);
}
function aliasedRenamed(t) {
  const { decode: d } = require("jsonwebtoken");
  // ruleid: perun.js.jwt-decode-unverified
  return d(t);
}
function aliasedModule(t) {
  const j = require("jsonwebtoken");
  // ruleid: perun.js.jwt-decode-unverified
  return j.decode(t);
}
function aliasedBracket(t) {
  const j = require("jsonwebtoken");
  // ruleid: perun.js.jwt-decode-unverified
  return j["decode"](t);
}
function twoHopAlias(t) {
  const j = require("jsonwebtoken");
  const j2 = j;
  // ruleid: perun.js.jwt-decode-unverified
  return j2.decode(t);
}
function destructureFromAlias(t) {
  const lib = require("jsonwebtoken");
  // ruleid: perun.js.jwt-decode-unverified
  const { decode } = lib;
  return decode(t);
}
function defaultExport(t) {
  const dd = require("jsonwebtoken").default;
  // ruleid: perun.js.jwt-decode-unverified
  return dd.decode(t);
}
function corsDefault(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const o = req.headers.origin || "";
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", o);
}
function corsLocal(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const o = req.headers.origin;
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", o);
}
function corsUpperKey(req, res) {
  const o = req.headers["ORIGIN"];
  res.setHeader("access-control-allow-credentials", "true");
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", o);
}
function corsFallback(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const o = ALLOWED[req.headers.origin] || req.headers.origin;
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", o);
}
function corsCredsAfter(req, res) {
  const o = req.headers.origin;
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", o);
  res.setHeader("Access-Control-Allow-Credentials", "true");
}
// accepted noise: an includes or has guard is still reported
function corsGuarded(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const o = req.headers.origin;
  // ruleid: perun.js.cors-reflected-origin
  if (ALLOWED.includes(o)) res.setHeader("Access-Control-Allow-Origin", o);
}
function corsTernaryGuard(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const o = req.headers.origin;
  const safe = ALLOWED.has(o) ? o : "https://app.example.com";
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", safe);
}
function corsCredVar(req, res) {
  const T = "true";
  res.setHeader("Access-Control-Allow-Credentials", T);
  const o = req.headers.origin;
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", o);
}
function corsGetMethod(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const o = req.get("Origin");
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", o);
}
const corsHeaderMethod = (req, res) => {
  res.set("Access-Control-Allow-Credentials", true);
  const o = req.header("ORIGIN");
  // ruleid: perun.js.cors-reflected-origin
  res.set("Access-Control-Allow-Origin", o);
};
function corsLowered(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const o = req.headers.origin;
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", o.toLowerCase());
}
function corsObjectAssign(req, res) {
  const o = req.headers.origin;
  // ruleid: perun.js.cors-reflected-origin
  Object.assign(res.headers, { "Access-Control-Allow-Origin": o, "Access-Control-Allow-Credentials": "true" });
}
function corsWriteHead(req, res) {
  const o = req.headers.origin;
  // ruleid: perun.js.cors-reflected-origin
  res.writeHead(200, { "Access-Control-Allow-Origin": o, "Access-Control-Allow-Credentials": "true" });
}
function corsHeaderMap(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const h = {};
  // ruleid: perun.js.cors-reflected-origin
  h["Access-Control-Allow-Origin"] = req.headers.origin;
  res.set(h);
}
function corsArrayIndex(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const o = [req.headers.origin][0];
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", o);
}
function corsMemoCache(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const o = MEMO[req.headers.origin];
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", o);
}
function corsTemplate(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const o = req.headers.origin;
  // ruleid: perun.js.cors-reflected-origin
  res.setHeader("Access-Control-Allow-Origin", `${o}`);
}
// ruleid: perun.js.jwt-decode-unverified
const viaCall = jwt.decode.call(null, tok);
// ruleid: perun.js.jwt-decode-unverified
const viaApply = jwt.decode.apply(null, [tok]);
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
CLEAN_JS = '''const ALLOWED = { "https://app.example.com": "https://app.example.com" };
jwt.verify(tok, key, { algorithms: ["HS256"] });
// known limit, not a detection: an Origin read inside a helper needs cross-function taint (Semgrep Pro)
function corsHelperRead(req, res) {
  const h = (k) => req.headers[k];
  res.setHeader("Access-Control-Allow-Credentials", "true");
  res.setHeader("Access-Control-Allow-Origin", h("origin"));
}
function verifyDestructured(t) {
  const { verify } = require("jsonwebtoken");
  return verify(t, key, { algorithms: ["HS256"] });
}
function decodeUnrelated(t) {
  const { decode } = require("other-lib");
  return decode(t);
}
function decodeRenamedOther(t) {
  const { decode: dz } = require("jose");
  return dz(t);
}
function decodeLocalObject(t) {
  const x = { decode: (v) => v };
  return x.decode(t);
}
function bracketOther(t) {
  return codec["decode"](t);
}
function corsLocalConst(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const o = req.headers.origin;
  log(o);
  res.setHeader("Access-Control-Allow-Origin", "https://app.example.com");
}
function corsLocalMapped(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  const o = ALLOWED[req.headers.origin];
  res.setHeader("Access-Control-Allow-Origin", o);
}
function corsLocalNoCreds(req, res) {
  const o = req.headers.origin;
  res.setHeader("Access-Control-Allow-Origin", o);
}
function corsReassigned(req, res) {
  res.setHeader("Access-Control-Allow-Credentials", "true");
  let o = req.headers.origin;
  o = "https://a.example.com";
  res.setHeader("Access-Control-Allow-Origin", o);
}
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
BAD_IMPORT = '''import jwtDefault from "jsonwebtoken";
import * as jwtNs from "jsonwebtoken";
import { decode as renamedDecode } from "jsonwebtoken";
// ruleid: perun.js.jwt-decode-unverified
const a = jwtDefault.decode(tok);
// ruleid: perun.js.jwt-decode-unverified
const b = jwtNs.decode(tok);
// ruleid: perun.js.jwt-decode-unverified
const c = renamedDecode(tok);
'''
CLEAN_IMPORT = '''import { verify } from "jsonwebtoken";
import { decode as otherDecode } from "jose";
import jwtDefault from "jose";
const a = verify(tok, key, { algorithms: ["HS256"] });
const b = otherDecode(tok);
const c = jwtDefault.decode(tok);
'''
BAD = {"app/bad.py": BAD_PY, "app/bad_cors.py": BAD_CORS_DJANGO, "app/bad.js": BAD_JS, "app/bad.ts": BAD_JS, "app/bad_import.js": BAD_IMPORT, "app/bad_import.ts": BAD_IMPORT}
CLEAN = {"app/clean.py": CLEAN_PY, "app/clean_cors.py": CLEAN_CORS_DJANGO, "app/clean.js": CLEAN_JS, "app/clean.ts": CLEAN_JS, "app/clean_import.js": CLEAN_IMPORT, "app/clean_import.ts": CLEAN_IMPORT}
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
