#!/usr/bin/env python3
"""Tests for templates/semgrep-taint/input-exposure.yml: perun.js.unvalidated-size-or-qty (CWE-20), perun.py.exception-in-response
and perun.py.secret-field-in-response (CWE-200). Fixtures use semgrep's `// ruleid:` / `// ok:` (`# ruleid:` / `# ok:` in Python)
convention, which marks the NEXT line. Also three class seeds (vulnerable, renamed mutant, fixed twin) per language: the vulnerable
and mutant seeds must report, the fixed twin must not. Fictional values only. The live check needs semgrep: without it the test
prints SKIP and exits 0, unless CI=true or REQUIRE_SEMGREP=1, which fails instead. Plain asserts."""
import json, os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
FILE = os.path.join(RULES, "input-exposure.yml")
IDS = ("perun.js.unvalidated-size-or-qty", "perun.py.exception-in-response", "perun.py.secret-field-in-response")

JS = '''const express = require('express');
const app = express();
const PRICE = 250;

app.post('/a', (req, res) => {
  const qty = req.body.qty;
  // ruleid: perun.js.unvalidated-size-or-qty
  const items = new Array(qty).fill('w');
  res.json({ items });
});

app.get('/b', (req, res) => {
  const n = parseInt(req.query.n);
  // ruleid: perun.js.unvalidated-size-or-qty
  const rows = Array.from({ length: n }, () => 'r');
  res.json({ rows });
});

app.get('/c', (req, res) => {
  // ruleid: perun.js.unvalidated-size-or-qty
  const buf = Buffer.alloc(Number(req.query.size));
  res.send(buf);
});

app.get('/d', (req, res) => {
  // ruleid: perun.js.unvalidated-size-or-qty
  res.send('ab'.repeat(req.params.times));
});

app.post('/e', (req, res) => {
  const { qty } = req.body;
  const q = +qty;
  // ruleid: perun.js.unvalidated-size-or-qty
  res.json({ totalCents: PRICE * q });
});

app.post('/f', (req, res) => {
  // ruleid: perun.js.unvalidated-size-or-qty
  res.json({ total: req.body.qty * item.unitPrice });
});

app.post('/g', (request, response) => {
  const len = request.body.len;
  // ruleid: perun.js.unvalidated-size-or-qty
  response.send(Buffer.allocUnsafe(len));
});

app.post('/h', (req, res) => {
  const qty = req.body.qty;
  if (qty < 1) return res.status(400).end();
  // Accepted miss: a lower-bound-only comparison counts as a range guard.
  // todoruleid: perun.js.unvalidated-size-or-qty
  res.json(new Array(qty).fill('w'));
});

app.post('/ok1', (req, res) => {
  const qty = req.body.qty;
  if (!Number.isInteger(qty) || qty < 1 || qty > 100) return res.status(400).end();
  // ok: perun.js.unvalidated-size-or-qty
  res.json({ cents: PRICE * qty, items: new Array(qty).fill('w') });
});

app.get('/ok2', (req, res) => {
  const n = Math.min(Number(req.query.n), 64);
  // ok: perun.js.unvalidated-size-or-qty
  res.send(Buffer.alloc(n));
});

app.get('/ok3', (req, res) => {
  // ok: perun.js.unvalidated-size-or-qty
  res.send('-'.repeat(20) + String(req.query.title));
});

app.get('/ok4', (req, res) => {
  const w = req.query.width;
  // ok: perun.js.unvalidated-size-or-qty
  res.json({ area: w * HEIGHT_PX });
});

app.get('/ok5', (req, res) => {
  const n = req.query.n;
  if (!Number.isSafeInteger(n)) return res.status(400).end();
  if (n > 1000) return res.status(400).end();
  // ok: perun.js.unvalidated-size-or-qty
  res.send(Buffer.alloc(n));
});

function helper(count) {
  // ok: perun.js.unvalidated-size-or-qty
  return new Array(count).fill(0);
}
'''

PY = '''import os
import traceback
from traceback import format_exc
from flask import Flask, jsonify, Response, make_response
from django.http import JsonResponse

app = Flask(__name__)


@app.route("/a")
def a():
    try:
        return load()
    except Exception:
        # ruleid: perun.py.exception-in-response
        return jsonify(error=traceback.format_exc()), 500


@app.route("/b")
def b():
    try:
        return load()
    except KeyError as exc:
        # ruleid: perun.py.exception-in-response
        return Response("lookup failed: %r" % exc, status=500)


@app.route("/c")
def c():
    try:
        return load()
    except ValueError as err:
        # ruleid: perun.py.exception-in-response
        return make_response(f"bad input {err}", 400)


def d(request):
    try:
        return load()
    except Exception as e:
        # ruleid: perun.py.exception-in-response
        return JsonResponse({"error": str(e)}, status=500)


@app.route("/e")
def e():
    try:
        return load()
    except Exception:
        # ruleid: perun.py.exception-in-response
        return jsonify({"trace": format_exc()}), 500


@app.route("/f")
def f():
    try:
        return load()
    except Exception as ex:
        # ruleid: perun.py.exception-in-response
        return str(ex), 500


@app.route("/g")
def g():
    try:
        return load()
    except Exception as ex:
        # ruleid: perun.py.exception-in-response
        return {"error": str(ex)}


@app.route("/ok1")
def ok1():
    try:
        return load()
    except Exception as exc:
        app.logger.exception(exc)
        # ok: perun.py.exception-in-response
        return jsonify(error="internal error"), 500


@app.route("/ok2")
def ok2():
    try:
        return load()
    except Exception:
        print(traceback.format_exc())
        # ok: perun.py.exception-in-response
        return jsonify(ok=False), 500


def ok3():
    try:
        return load()
    except Exception as exc:
        # ok: perun.py.exception-in-response
        raise RuntimeError("wrapped") from exc


@app.route("/h")
def h(u):
    # ruleid: perun.py.secret-field-in-response
    return jsonify({"name": u.name, "password_hash": u.ph})


@app.route("/i")
def i(k):
    # ruleid: perun.py.secret-field-in-response
    return jsonify(name="Jane Smith", api_key=k)


def j(request, s):
    # ruleid: perun.py.secret-field-in-response
    return JsonResponse({"client_secret": s})


@app.get("/k")
def k(p):
    # ruleid: perun.py.secret-field-in-response
    return {"user": "jane", "password": p}


@app.route("/l")
def l():
    # ruleid: perun.py.secret-field-in-response
    return jsonify(dict(os.environ))


@app.route("/m")
def m(u):
    # ruleid: perun.py.secret-field-in-response
    return jsonify(data={"profile": {"secret": u.s}})


@app.route("/ok4")
def ok4(u):
    # ok: perun.py.secret-field-in-response
    return jsonify(name=u.name, email=u.email)


@app.route("/ok5")
def ok5(t):
    # ok: perun.py.secret-field-in-response
    return jsonify({"token": t})


def ok6(p):
    # ok: perun.py.secret-field-in-response
    return {"password": p}


def ok7(request):
    # ok: perun.py.secret-field-in-response
    return JsonResponse({"ok": request.POST.get("pass") == os.environ.get("APP_PW")})


USERS = {1: {"name": "Jane Smith", "password_hash": "x1", "api_key": "k-demo"}}
'''

SEEDS = {
    "vuln_cwe20.js": '''const express = require("express");
const app = express();
app.use(express.json());
const PRICE_CENTS = 250;

app.post("/orders", (req, res) => {
  const qty = req.body.qty;
  const items = new Array(qty).fill("widget");
  res.json({ totalCents: PRICE_CENTS * qty, items });
});
''',
    "mutant_cwe20.js": '''const express = require("express");
const shop = express();
const UNIT = 250;

shop.get("/cart/price", (request, response) => {
  const count = parseInt(request.query.count);
  const rows = Array.from({ length: count }, () => "gadget");
  response.json({ cents: UNIT * count, rows });
});
''',
    "clean_cwe20.js": '''const express = require("express");
const app = express();
app.use(express.json());
const PRICE_CENTS = 250;

app.post("/orders", (req, res) => {
  const qty = req.body.qty;
  if (!Number.isInteger(qty) || qty < 1 || qty > 100) {
    return res.status(400).json({ error: "qty must be an integer from 1 to 100" });
  }
  const items = new Array(qty).fill("widget");
  res.json({ totalCents: PRICE_CENTS * qty, items });
});
''',
    "vuln_cwe200.py": '''import traceback
from flask import Flask, jsonify

app = Flask(__name__)
USERS = {1: {"name": "Jane Smith", "email": "jane@example.com", "password_hash": "x1", "api_key": "k-demo"}}


@app.route("/users/<int:uid>")
def get_user(uid):
    try:
        return jsonify(USERS[uid])
    except Exception:
        return jsonify(error=traceback.format_exc()), 500
''',
    "mutant_cwe200.py": '''import os
from flask import Flask, Response

shop = Flask(__name__)
ROWS = {7: {"label": "Acme order", "card_last4": "4242", "secret_note": "internal"}}


@shop.route("/orders/<int:oid>")
def show_order(oid):
    try:
        return Response(str(ROWS[oid]))
    except KeyError as exc:
        return Response("lookup failed: %r env=%s" % (exc, dict(os.environ)), status=500)
''',
    "clean_cwe200.py": '''from flask import Flask, jsonify

app = Flask(__name__)
USERS = {1: {"name": "Jane Smith", "email": "jane@example.com", "password_hash": "x1", "api_key": "k-demo"}}


@app.route("/users/<int:uid>")
def get_user(uid):
    user = USERS.get(uid)
    if user is None:
        return jsonify(error="not found"), 404
    return jsonify(name=user["name"])
''',
}


def annotated(src, kind, prefix):
    return {(i + 2) for i, l in enumerate(src.splitlines()) if re.match(rf"\s*{prefix} {kind}: ", l)}


# offline: rule text
text = open(FILE).read()
for rid in IDS:
    assert f"- id: {rid}\n" in text, rid
assert text.count("severity: WARNING") == 3 and "languages: [javascript, typescript]" in text and "languages: [python]" in text
assert "by-side-effect: true" in text and "focus-metavariable: $X" in text, "guard sanitizer"
assert "token" not in re.search(r"regex: \^\[\"'\]\?\((.*?)\)", text).group(1), "tokens are not secret fields"
assert len(annotated(JS, "ruleid", "//")) == 7 and len(annotated(JS, "ok", "//")) == 6
assert len(annotated(PY, "ruleid", "#")) == 13 and len(annotated(PY, "ok", "#")) == 7

if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "app.js"), "w").write(JS)
        open(os.path.join(d, "app.py"), "w").write(PY)
        for name, src in SEEDS.items():
            open(os.path.join(d, "seed_" + name), "w").write(src)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", FILE, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "."],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    by = {}
    for x in r["results"]:
        by.setdefault(os.path.basename(x["path"]), []).append((x["check_id"].rsplit(".", 3)[-3] + "." + x["check_id"].rsplit(".", 3)[-2] + "." + x["check_id"].rsplit(".", 1)[-1], x["start"]["line"]))
    for fx, src, prefix in (("app.js", JS, "//"), ("app.py", PY, "#")):
        got = {ln for _, ln in by.get(fx, [])} - annotated(src, "todoruleid", prefix)  # todoruleid: a known miss, either outcome passes
        want = annotated(src, "ruleid", prefix)
        assert got == want, (fx, "unexpected", sorted(got - want), "missed", sorted(want - got))
    for name in SEEDS:
        n = len(by.get("seed_" + name, []))
        assert (n == 0) == name.startswith("clean_"), (name, n)
    print("semgrep-input-exposure: live ok")
elif os.environ.get("CI") == "true" or os.environ.get("REQUIRE_SEMGREP") == "1":
    sys.exit("FAIL: semgrep not installed but CI=true or REQUIRE_SEMGREP=1, so the live check cannot be skipped")
else:
    print("semgrep-input-exposure: SKIP live check (semgrep not installed)")
print("semgrep-input-exposure: ok")
