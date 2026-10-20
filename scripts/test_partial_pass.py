#!/usr/bin/env python3
"""Tests for PARTIAL-PASS receipts in the merge train (#1778): a receipt waives exactly the checks it names, the train
carries at most one such PR and refuses a second with a clear message, and `partial-kill` enforces the recorded kill
criterion after merge. Offline: merge_train's own FakeForge, no network. Run: python3 scripts/test_partial_pass.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / ".claude/skills/agentic-delivery/scripts"))
import merge_train as mt  # noqa: E402
import partial_pass as pp  # noqa: E402

OK, RED = mt.OK, mt.RED


class Forge(mt.FakeForge):
    """FakeForge plus the post-merge calls: check runs on a merge commit, the PR node id and the revert mutation."""

    def __init__(self, n=3):
        super().__init__(n)
        self.post = {}  # merge commit -> check runs

    def __call__(self, args, cwd=None, timeout=None):
        if args[:2] == ["gh", "api"] and "/commits/M" in args[2]:
            sha = args[2].split("/commits/")[1].split("/")[0]
            runs = self.post.get(sha, [])
            self.calls.append(args)
            return 0, json.dumps({"total_count": len(runs), "check_runs": runs}), ""
        if args[:3] == ["gh", "pr", "view"] and "--jq" in args:
            self.calls.append(args)
            return 0, f"NODE{args[3]}\n", ""
        if args[:3] == ["gh", "api", "graphql"]:
            self.calls.append(args)
            return 0, "https://example.com/revert/1\n", ""
        return super().__call__(args, cwd, timeout)


class PartialPass(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="partial-pass-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.f = Forge(3)
        for n in (1, 2):  # #1 and #2 have a failing "e2e" check; both carry a receipt naming it
            self.f.prs[n]["runs"] = [mt._run("ci", "success"), mt._run("e2e", "failure")]
            pp.write(n, f"h{n}", ["e2e"], self.tmp)

    def go(self, *argv):
        buf = io.StringIO()
        rc = mt.run([*argv, "--base", "main", "--state", os.path.join(self.tmp, "s.json"), "--partial-dir", self.tmp,
                     "--backoff", "5"], runner=self.f, out=buf, sleep=self.f.sleeps.append)
        return rc, buf.getvalue()

    def land(self):
        self.assertEqual(self.go("verify", "--verify-cmd", "t")[0], OK)
        rc, out = self.go("merge", "--apply", "--grant", "g")
        self.assertEqual(rc, OK, out)
        return out

    def test_accepts_one_and_lists_the_unchecked(self):
        rc, out = self.go("plan")
        self.assertEqual(rc, OK)
        self.assertIn("ELIGIBLE #1 h1 PARTIAL-PASS unchecked=e2e", out)
        self.assertIn("PLAN base=main members=#1,#3", out)

    def test_refuses_a_second_with_a_clear_message(self):
        _, out = self.go("plan")
        self.assertIn("SKIP #2 second PARTIAL-PASS (one per train; #1 holds the slot)", out)
        self.assertNotIn("ELIGIBLE #2", out)

    def test_without_a_receipt_or_for_another_head_or_check_the_failure_still_skips(self):
        os.remove(os.path.join(self.tmp, "1.json"))  # no receipt
        pp.write(2, "stale-head", ["e2e"], self.tmp)  # receipt for an older push
        self.f.prs[3]["runs"] = [mt._run("ci", "success"), mt._run("lint", "failure")]
        pp.write(3, "h3", ["e2e"], self.tmp)  # receipt names e2e, but lint is what failed
        _, out = self.go("plan")
        self.assertIn("SKIP #1 check e2e=failure", out)
        self.assertIn("SKIP #2 check e2e=failure", out)
        self.assertIn("SKIP #3 check lint=failure", out)

    def test_merge_records_the_kill_criterion_and_the_unchecked_list(self):
        out = self.land()
        self.assertIn(f"MERGED #1 h1 -> main@M1 grant=g PARTIAL-PASS unchecked=e2e kill={pp.KILL}", out)
        self.assertEqual(json.loads(Path(self.tmp, "s.json").read_text())["partial"],
                         {"number": 1, "merge_sha": "M1", "unchecked": ["e2e"]})
        self.assertEqual(json.loads(Path(self.tmp, "1.json").read_text())["kill"], pp.KILL)

    def test_kill_reverts_when_an_unchecked_check_fails_post_merge(self):
        self.land()
        self.f.post["M1"] = [mt._run("e2e", "failure")]
        rc, out = self.go("partial-kill")
        self.assertEqual(rc, RED)
        self.assertIn("KILL #1", out)
        self.assertIn("WOULD-REVERT #1", out)
        self.assertFalse([c for c in self.f.calls if c[:3] == ["gh", "api", "graphql"]], "dry run must not revert")
        rc, out = self.go("partial-kill", "--apply")
        self.assertEqual(rc, RED)
        self.assertIn("REVERT #1 revert PR opened https://example.com/revert/1", out)
        self.assertIn("id=NODE1", [c for c in self.f.calls if c[:3] == ["gh", "api", "graphql"]][0])
        self.assertIn("NOOP", self.go("partial-kill")[1])  # decided: the record is cleared

    def test_kill_keeps_a_passing_pr_and_waits_for_a_running_check(self):
        self.land()
        self.assertIn("PENDING #1", self.go("partial-kill")[1])
        self.f.post["M1"] = [mt._run("e2e", "success")]
        rc, out = self.go("partial-kill", "--apply")
        self.assertEqual(rc, OK)
        self.assertIn("KEPT #1", out)
        self.assertFalse([c for c in self.f.calls if c[:3] == ["gh", "api", "graphql"]])

    def test_receipt_needs_a_named_check(self):
        with self.assertRaises(ValueError):
            pp.write(9, "h9", [" "], self.tmp)
        self.assertIsNone(pp.load(9, "h9", self.tmp))


if __name__ == "__main__":
    unittest.main()
