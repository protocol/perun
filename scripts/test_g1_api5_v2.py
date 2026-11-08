#!/usr/bin/env python3
"""G1 API5 detector v2 (route_auth_map.py --privileged): router-level guards (JS .use, FastAPI prefix and dependencies, Flask before_request), Security scopes,
named guard helpers, caller-owned writes and state verbs. Seeded positives and near-miss negatives with fictional names, plus a pin that the default output is unchanged.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/route_auth_map.py"

# (name, filename, source, expected flagged lines)
CASES = [
    ("pos use path-scoped auth only", "a.js", """const express = require('express');
const app = express();
app.use('/admin', requireAuth);
app.post('/admin/flush', (req, res) => {
  cache.clear();
  res.sendStatus(204);
});
""", {4}),
    ("pos router.use auth only then role write", "a.js", """const router = require('express').Router();
router.use(requireAuth);
router.patch('/users/:id/role', (req, res) => {
  Member.update({ role: req.body.role }, { where: { id: req.params.id } });
  res.sendStatus(204);
});
""", {3}),
    ("pos include_router prefix with login dependency", "a.py", """from fastapi import FastAPI, APIRouter, Depends
app = FastAPI()
ops = APIRouter()
@ops.delete('/cache')
def drop_cache(user=Depends(get_current_user)):
    return {}
app.include_router(ops, prefix='/admin')
""", {4}),
    ("pos flask app.before_request login only", "a.py", """from flask import Flask, abort, g
app = Flask(__name__)
@app.before_request
def need_login():
    if g.user is None:
        abort(401)
@app.route('/admin/purge', methods=['POST'])
def purge():
    return {}
""", {7}),
    ("pos audit column is not ownership", "a.js", """const app = require('express')();
app.put('/members/:id', requireAuth, async (req, res) => {
  await Member.update({ name: req.body.name, updatedBy: req.user.id }, { where: { id: req.params.id } });
  res.sendStatus(204);
});
""", {2}),
    ("pos state verb on a record", "a.js", """const app = require('express')();
app.post('/orders/:id/approve', requireAuth, async (req, res) => {
  await Order.update({ approved: true }, { where: { id: req.params.id } });
  res.sendStatus(204);
});
""", {2}),
    ("pos authorization header is not a check", "a.js", """const app = require('express')();
function authenticate(req, res, next) {
  req.user = verify((req.headers.authorization || '').replace('Bearer ', ''));
  next();
}
app.delete('/admin/sessions', authenticate, (req, res) => { Session.clear(); res.sendStatus(204); });
""", {6}),
    ("pos flask admin write, roles shorthand in response", "a.py", """from flask import Blueprint, jsonify
from flask_login import login_required
bp = Blueprint('ops', __name__)
@bp.route('/admin/export', methods=['POST'])
@login_required
def export():
    roles = ['a']
    return jsonify(roles)
""", {4}),
    ("neg use with restrictTo", "a.js", """const router = require('express').Router();
router.use(requireAuth, restrictTo('admin'));
router.delete('/admin/users/:id', (req, res) => { User.destroy({ where: { id: req.params.id } }); res.sendStatus(204); });
""", set()),
    ("neg router dependency require_superuser", "a.py", """from fastapi import APIRouter, Depends
router = APIRouter(prefix='/admin', dependencies=[Depends(require_superuser)])
@router.post('/flush')
def flush():
    return {}
""", set()),
    ("neg before_request group membership", "a.py", """from flask import Blueprint, abort, g
bp = Blueprint('ops', __name__, url_prefix='/admin')
@bp.before_request
def gate():
    if g.user is None:
        abort(401)
    if g.user.level not in LEVELS:
        abort(403)
@bp.route('/purge', methods=['POST'])
def purge():
    return {}
""", set()),
    ("neg Security scopes", "a.py", """from fastapi import APIRouter, Security
router = APIRouter()
@router.put('/users/{uid}')
def edit(uid: int, who=Security(get_user, scopes=['users:write'])):
    return {}
""", set()),
    ("neg write scoped to the caller's own id", "a.js", """const app = require('express')();
app.put('/users/:id', requireAuth, async (req, res) => {
  await User.update({ name: req.body.name }, { where: { id: req.user.id } });
  res.sendStatus(204);
});
""", set()),
    ("neg inline tier comparison", "a.js", """const app = require('express')();
app.delete('/admin/posts/:id', requireAuth, async (req, res) => {
  if (req.user.tier !== 'staff') return res.sendStatus(403);
  await Post.destroy({ where: { id: req.params.id } });
  res.sendStatus(204);
});
""", set()),
    ("neg permission object decorator", "a.py", """from flask import Flask
from flask_login import login_required
app = Flask(__name__)
@app.route('/admin/ban/<int:uid>', methods=['POST'])
@login_required
@ban_permission.require(http_exception=403)
def ban(uid):
    return {}
""", set()),
    ("neg ensure_staff helper", "a.py", """from fastapi import APIRouter, Depends
router = APIRouter()
@router.post('/admin/refund')
def refund(user=Depends(get_current_user)):
    ensure_staff(user)
    return {}
""", set()),
    ("neg read-only admin page", "a.js", """const app = require('express')();
app.get('/admin/stats', requireAuth, (req, res) => res.json({}));
""", set()),
    ("neg scope membership with not in on a call", "a.py", """from flask import Flask, abort
from flask_jwt_extended import jwt_required, get_jwt
app = Flask(__name__)
@app.route('/admin/keys', methods=['DELETE'])
@jwt_required()
def drop_keys():
    if 'ops' not in get_jwt().get('scopes', []):
        abort(403)
    return {}
""", set()),
]


# default output of this fixture is pinned byte for byte: the privileged logic must not leak into it
PIN_PY = """from fastapi import APIRouter, Depends
router = APIRouter(prefix="/admin", dependencies=[Depends(get_current_user)])
@router.post("/tenants/{tid}/disable")
def disable(tid: int):
    return {}
"""
PIN_JS = """const router = require('express').Router();
router.use(requireAuth, adminOnly);
router.delete('/admin/users/:id', async (req, res) => { res.sendStatus(204); });
router.put('/users/:id', requireAuth, async (req, res) => { res.json({}); });
"""
PIN_OUT = """a.py:3: INFO: POST /tenants/:tid/disable auth=Depends(get_current_user)
b.js:3: INFO: DELETE /admin/users/:id auth=requireAuth
b.js:4: INFO: PUT /users/:id auth=requireAuth
{"tool": "route_auth_map", "handlers": 3, "files": 2, "high": 0, "unjudged": 0, "findings": []}
"""


def run(d, *flags):
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), *flags, str(d)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return r.stdout


class Api5V2(unittest.TestCase):
    def test_cases(self):
        for label, name, body, want in CASES:
            with self.subTest(label), tempfile.TemporaryDirectory() as d:
                (Path(d) / name).write_text(body)
                got = {int(l.split(":")[1]) for l in run(d, "--privileged").splitlines() if ": PRIV: " in l}
                self.assertEqual(got, want)

    def test_default_output_pinned(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.py").write_text(PIN_PY)
            (Path(d) / "b.js").write_text(PIN_JS)
            self.assertEqual(run(d), PIN_OUT)


if __name__ == "__main__":
    unittest.main()
