#!/usr/bin/env python3
"""review_checks.sh --full rows for the G1 API pilot: tool `ownership` (ownership_sibling_check.py) and tool `privileged-route` (route_auth_map.py --privileged).

Each tool gets a fixture where its row appears and a clean fixture with no row. Fictional names only.
"""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

RC = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts/review_checks.sh"
ENV = dict(os.environ, PATH="/usr/bin:/bin")

OWN_BAD = """const express = require('express');
const app = express();
app.get('/notes/:id', requireAuth, async (req, res) => {
  const n = await Note.findOne({ _id: req.params.id, owner: req.user.id });
  res.json(n);
});
app.get('/notes/:id/raw', requireAuth, async (req, res) => {
  const n = await Note.findOne({ _id: req.params.id });
  res.json(n);
});
"""
OWN_OK = OWN_BAD.replace("findOne({ _id: req.params.id });", "findOne({ _id: req.params.id, owner: req.user.id });")
PRIV_BAD = """const express = require('express');
const app = express();
app.delete('/admin/users/:id', requireAuth, async (req, res) => {
  await User.deleteOne({ _id: req.params.id });
  res.sendStatus(204);
});
"""
PRIV_OK = PRIV_BAD.replace("requireAuth", "requireAuth, requireAdmin")


def run(t, name, src):
    g = Path(t) / name
    g.mkdir()
    (g / "api.js").write_text(src)
    for a in (["init", "-q"], ["add", "api.js"], ["-c", "user.email=a@example.com", "-c", "user.name=Acme", "commit", "-qm", "fixture"]):
        subprocess.run(["git", "-C", str(g), *a], check=True, capture_output=True, env=ENV)
    r = subprocess.run(["bash", str(RC), "--full", "--repo", str(g)], capture_output=True, text=True, env=ENV)
    return json.loads(r.stdout)


class Rows(unittest.TestCase):
    def test_rows(self):
        with tempfile.TemporaryDirectory() as t:
            rows = lambda n, s, tool: [x for x in run(t, n, s) if x["tool"] == tool]
            o = rows("o1", OWN_BAD, "ownership")
            self.assertEqual([(x["file"], x["line"], x["rule"]) for x in o], [("api.js", 8, "ownership-sibling")])
            self.assertEqual(rows("o2", OWN_OK, "ownership"), [])
            p = rows("p1", PRIV_BAD, "privileged-route")
            self.assertEqual([(x["file"], x["line"], x["rule"]) for x in p], [("api.js", 3, "privileged-route")])
            self.assertEqual(rows("p2", PRIV_OK, "privileged-route"), [])


if __name__ == "__main__":
    unittest.main()
