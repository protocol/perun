#!/usr/bin/env python3
"""Tests: a train park() records a head-bound refusal comment on the PR; admission refuses a re-ride at the same head and allows it at a new head."""
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"))
import merge_train as mt  # noqa: E402

X, Y = "a" * 40, "b" * 40


class Refusal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="train-refusal-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.calls = []

    def train(self, rc=0):
        a = SimpleNamespace(repo=None, state=f"{self.tmp}/s.json", base="main", allow_forks=False, min_checks=1, no_status=False)

        def runner(argv, cwd=None, **kw):
            self.calls.append(argv)
            return rc, "", ""
        return mt.Train(a, runner, io.StringIO(), lambda s: None)

    def test_drop_at_x_refused_at_x_allowed_at_y(self):
        self.train().park({"number": 7, "head": X}, "culprit")
        body = next(c[c.index("--body") + 1] for c in self.calls if c[:3] == ["gh", "pr", "comment"])
        self.assertEqual(body.splitlines()[0], mt.REFUSED + X)
        comments = [{"body": body}]
        self.assertTrue(mt.refused({"headRefOid": X, "comments": comments}))
        self.assertFalse(mt.refused({"headRefOid": Y, "comments": comments}))  # new push -> re-admitted

    def test_fail_closed_shapes(self):
        self.assertFalse(mt.refused({"headRefOid": X}))
        self.assertFalse(mt.refused({"headRefOid": X, "comments": [{"body": mt.REFUSED + X + "deadbeef"}]}))  # longer sha, not this head
        self.assertTrue(mt.refused({"headRefOid": X, "comments": [{"body": mt.REFUSED + X}]}))

    def test_clear_author_failure_and_neutral(self):
        c = lambda who, body: {"author": {"login": who}, "body": body}  # noqa: E731
        pr = {"headRefOid": X, "comments": [c("bot", mt.REFUSED + X), c("rando", mt.CLEARED + X)]}
        self.assertTrue(mt.refused(pr, "bot"))  # a clear by someone else does not count
        self.assertFalse(mt.refused({"headRefOid": X, "comments": [c("bot", mt.REFUSED + X), c("bot", mt.CLEARED + X)]}, "bot"))
        self.assertFalse(mt.refused({"headRefOid": X, "comments": [c("rando", mt.REFUSED + X)]}, "bot"))  # forged refusal ignored
        self.assertTrue(mt.refused({"headRefOid": X, "comments": [c("rando", mt.REFUSED + X)]}))  # login unknown: fail toward refusing
        t = self.train(rc=1)
        t.park({"number": 7, "head": X}, "x @octocat [a](http://e.example)")
        self.assertEqual(len([k for k in self.calls if k[:3] == ["gh", "pr", "comment"]]), 2)  # retried once
        self.assertIn("REFUSAL-NOT-RECORDED", t.out.getvalue())
        body = next(k[k.index("--body") + 1] for k in self.calls if k[:3] == ["gh", "pr", "comment"])
        self.assertNotIn("@octocat", body)
        self.assertNotIn("](", body)


if __name__ == "__main__":
    unittest.main()
