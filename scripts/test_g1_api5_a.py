#!/usr/bin/env python3
"""G1 status (a): OWASP API5:2023 Broken Function Level Authorization (route_auth_map.py --privileged).

Inline tempdir fixtures (fictional names): >=3 seeded positives flagged at the seeded line across Express, Flask and FastAPI,
>=3 negatives clean. The detector is not edited to fit the seeds. Default output must not change when the flag is absent.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/route_auth_map.py"

EXPRESS_POS = """const express = require('express');
const app = express();
const { requireAuth } = require('./auth');
app.delete('/admin/users/:id', requireAuth, async (req, res) => {
  await User.deleteOne({ _id: req.params.id });
  res.sendStatus(204);
});
app.post('/accounts/:id/roles', requireAuth, async (req, res) => {
  await Account.updateOne({ _id: req.params.id }, { grants: req.body.grants });
  res.sendStatus(204);
});
"""

FLASK_POS = """from flask import Flask, request
from flask_login import login_required
app = Flask(__name__)
@app.route('/users/<int:uid>', methods=['PUT'])
@login_required
def update_user(uid):
    User.query.get(uid).email = request.json['email']
    return {}
"""

FASTAPI_POS = """from fastapi import APIRouter, Depends
router = APIRouter()
@router.delete('/members/{member_id}')
def drop_member(member_id: int, user=Depends(get_current_user)):
    db.delete(member_id)
    return {}
"""

EXPRESS_NEG = """const express = require('express');
const app = express();
const { requireAuth, requireAdmin } = require('./auth');
app.delete('/admin/users/:id', requireAuth, requireAdmin, async (req, res) => {
  await User.deleteOne({ _id: req.params.id });
  res.sendStatus(204);
});
app.get('/users/:id', requireAuth, async (req, res) => {
  res.json(await User.findById(req.params.id));
});
app.put('/me', requireAuth, async (req, res) => {
  res.json(await User.findByIdAndUpdate(req.user.id, { name: req.body.name }));
});
"""

FLASK_NEG = """from flask import Flask, request, abort
from flask_login import login_required, current_user
app = Flask(__name__)
@app.route('/users/<int:uid>', methods=['DELETE'])
@login_required
def drop_user(uid):
    if current_user.role != 'admin':
        abort(403)
    User.query.filter_by(id=uid).delete()
    return {}
"""

FASTAPI_NEG = """from fastapi import APIRouter, Depends, HTTPException
router = APIRouter()
@router.post('/admin/reindex')
def reindex(user=Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(403)
    return {}
"""


class Api5(unittest.TestCase):
    def rows(self, name, body, *flags):
        d = Path(tempfile.mkdtemp(prefix="g1a5-"))
        (d / name).write_text(body)
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), *flags, str(d)], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def priv(self, name, body):
        return {(l.split(":")[0], int(l.split(":")[1])) for l in self.rows(name, body, "--privileged").splitlines() if ": PRIV: " in l}

    def test_express_positive(self):
        self.assertEqual(self.priv("a.js", EXPRESS_POS), {("a.js", 4), ("a.js", 8)})

    def test_flask_positive(self):
        self.assertEqual(self.priv("a.py", FLASK_POS), {("a.py", 4)})

    def test_fastapi_positive(self):
        self.assertEqual(self.priv("api.py", FASTAPI_POS), {("api.py", 3)})

    def test_express_negatives_clean(self):
        self.assertEqual(self.priv("n.js", EXPRESS_NEG), set())

    def test_flask_role_check_clean(self):
        self.assertEqual(self.priv("n.py", FLASK_NEG), set())

    def test_fastapi_admin_check_clean(self):
        self.assertEqual(self.priv("api.py", FASTAPI_NEG), set())

    def test_default_output_has_no_priv_rows(self):
        self.assertNotIn("PRIV", self.rows("a.js", EXPRESS_POS))


if __name__ == "__main__":
    unittest.main()
