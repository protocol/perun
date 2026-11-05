#!/usr/bin/env python3
"""G1 status (a): OWASP API3:2023 inbound mass assignment (perun.js.mass-assignment, perun.py.mass-assignment).

Inline tempdir fixtures (fictional names): >=4 seeded positives flagged at the seeded line, >=4 negatives clean.
Rules are not edited to fit the seeds. A missing semgrep skips, never passes.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_g1_api_pilot_a import semgrep_hits, tree  # noqa: E402

JS_RULE, PY_RULE = "js.mass-assignment", "py.mass-assignment"

EXPRESS_MONGOOSE = """const express = require('express');
const User = require('./models/user');
const app = express();
app.post('/users', async (req, res) => {
  const user = await User.create(req.body);
  res.json(user);
});
app.put('/users/:id', async (req, res) => {
  const updated = await User.findByIdAndUpdate(req.params.id, req.body, { new: true });
  res.json(updated);
});
"""

SEQUELIZE = """const { Account } = require('./models');
module.exports = async function patch(req, res) {
  const data = { ...req.body };
  const acct = await Account.findByPk(req.params.id);
  Object.assign(acct, req.body);
  await Account.update({ ...req.body }, { where: { id: 1 } });
  res.sendStatus(204);
};
"""

FLASK_SQLA = """from flask import Flask, request
app = Flask(__name__)
@app.post('/users')
def create():
    user = User(**request.get_json())
    db.session.add(user)
    payload = request.json
    other = Profile(**payload)
    return {}
"""

DJANGO_DRF = """from rest_framework import serializers
from rest_framework.views import APIView
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"
class UserView(APIView):
    def post(self, request):
        User.objects.create(**request.data)
        for key, value in request.data.items():
            setattr(self.obj, key, value)
"""

JS_NEG = """const User = require('./models/user');
const { pick } = require('lodash');
app.post('/users', async (req, res) => {
  const { name, email } = req.body;
  await User.create({ name, email });
  await User.create(pick(req.body, ['name', 'email']));
  const copy = Object.assign({}, req.body);
  const m = new Map(req.body);
  await User.update({ name: req.body.name }, { where: { id: 1 } });
});
"""

PY_NEG = """from flask import request
from pydantic import BaseModel
class UserIn(BaseModel):
    name: str
    email: str
def create():
    data = UserIn(**request.get_json())
    clean = UserSchema().load(request.json)
    user = User(**clean)
    user2 = User(name=request.json['name'], email=request.json['email'])
    send_mail(**request.json)
    for key, value in request.json.items():
        if key in ALLOWED:
            setattr(user, key, value)
    return {}
"""

DRF_NEG = """from rest_framework import serializers
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "email"]
"""


class Api3(unittest.TestCase):
    def rows(self, cfg, name, body, rule):
        return {(f, line) for f, line, r in semgrep_hits(cfg, tree({name: body})) if r == rule}

    def test_express_mongoose_positive(self):
        self.assertEqual(self.rows("js.yml", "a.js", EXPRESS_MONGOOSE, JS_RULE), {("a.js", 5), ("a.js", 9)})

    def test_sequelize_spread_positive(self):
        self.assertEqual(self.rows("js.yml", "b.js", SEQUELIZE, JS_RULE), {("b.js", 5), ("b.js", 6)})

    def test_flask_sqlalchemy_positive(self):
        self.assertEqual(self.rows("py.yml", "a.py", FLASK_SQLA, PY_RULE), {("a.py", 5), ("a.py", 8)})

    def test_django_drf_positive(self):
        self.assertEqual(self.rows("py.yml", "views.py", DJANGO_DRF, PY_RULE), {("views.py", 6), ("views.py", 9), ("views.py", 10)})

    def test_js_negatives_clean(self):
        self.assertEqual(self.rows("js.yml", "n.js", JS_NEG, JS_RULE), set())

    def test_py_negatives_clean(self):
        self.assertEqual(self.rows("py.yml", "n.py", PY_NEG, PY_RULE), set())

    def test_drf_explicit_fields_clean(self):
        self.assertEqual(self.rows("py.yml", "ser.py", DRF_NEG, PY_RULE), set())

    def test_tests_dir_excluded(self):
        self.assertEqual(self.rows("js.yml", "tests/a.js", EXPRESS_MONGOOSE, JS_RULE), set())


if __name__ == "__main__":
    unittest.main()
