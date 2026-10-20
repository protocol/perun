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
        self.state = Path(self.tmp, "s.json")
        self.f = Forge(3)
        for n in (1, 2):  # #1 and #2: "e2e" never finished on the head; both carry a receipt naming it
            self.f.prs[n]["runs"] = [mt._run("ci", "success"), mt._run("e2e", None, status="in_progress")]
            pp.write(n, f"h{n}", ["e2e"], self.tmp)

    def go(self, *argv):
        buf = io.StringIO()
        rc = mt.run([*argv, "--base", "main", "--state", str(self.state), "--partial-dir", self.tmp, "--backoff", "5"],
                    runner=self.f, out=buf, sleep=self.f.sleeps.append)
        return rc, buf.getvalue()

    def land(self):
        self.assertEqual(self.go("verify", "--verify-cmd", "t")[0], OK)
        rc, out = self.go("merge", "--apply", "--grant", "g")
        self.assertEqual(rc, OK, out)
        return out

    def edit_state(self, **kv):
        s = json.loads(self.state.read_text())
        s.update(kv)
        self.state.write_text(json.dumps(s))

    def reverts(self):
        return [c for c in self.f.calls if c[:3] == ["gh", "api", "graphql"]]

    def test_accepts_one_and_lists_the_unchecked(self):
        rc, out = self.go("plan")
        self.assertEqual(rc, OK)
        self.assertIn("ELIGIBLE #1 h1 PARTIAL-PASS unchecked=e2e", out)
        self.assertIn("PLAN base=main members=#1,#3", out)

    def test_a_check_missing_from_the_head_is_waived_too(self):
        self.f.prs[1]["runs"] = [mt._run("ci", "success")]
        self.assertIn("ELIGIBLE #1 h1 PARTIAL-PASS unchecked=e2e", self.go("plan")[1])

    def test_refuses_a_second_with_a_clear_message(self):
        _, out = self.go("plan")
        self.assertIn("SKIP #2 second PARTIAL-PASS (one per train; #1 holds the slot)", out)
        self.assertNotIn("ELIGIBLE #2", out)

    def test_a_named_check_that_ran_and_failed_still_blocks(self):
        self.f.prs[1]["runs"] = [mt._run("ci", "success"), mt._run("e2e", "failure")]
        os.remove(os.path.join(self.tmp, "2.json"))  # no receipt
        pp.write(3, "stale-head", ["e2e"], self.tmp)  # receipt for an older push
        self.f.prs[3]["runs"] = [mt._run("ci", "success"), mt._run("lint", "failure")]
        pp.write(3, "h3", ["e2e"], self.tmp)  # receipt names e2e, but lint is what failed
        _, out = self.go("plan")
        self.assertIn("SKIP #1 check e2e=failure", out)
        self.assertIn("SKIP #2 check e2e=in_progress", out)  # no receipt: unfinished still blocks
        self.assertIn("SKIP #3 check lint=failure", out)

    def test_merge_records_the_kill_criterion_and_the_unchecked_list(self):
        out = self.land()
        self.assertIn(f"MERGED #1 h1 -> main@M1 grant=g PARTIAL-PASS unchecked=e2e kill={pp.KILL}", out)
        rec = json.loads(self.state.read_text())["partial"]
        self.assertEqual({k: rec[k] for k in ("number", "merge_sha", "unchecked")},
                         {"number": 1, "merge_sha": "M1", "unchecked": ["e2e"]})
        self.assertEqual(json.loads(Path(self.tmp, "1.json").read_text())["kill"], pp.KILL)

    def test_only_one_outstanding_until_partial_kill_decides(self):
        self.land()
        self.assertIn("SKIP #2 PARTIAL-PASS #1 merged and undecided (run partial-kill first)", self.go("plan")[1])
        self.f.post["M1"] = [mt._run("e2e", "success")]
        self.assertIn("KEPT #1", self.go("partial-kill")[1])
        self.f.prs[2]["state"] = "OPEN"
        self.assertIn("ELIGIBLE #2 h2 PARTIAL-PASS", self.go("plan")[1])

    def test_merge_rechecks_the_rule_against_the_state(self):
        self.assertEqual(self.go("verify", "--verify-cmd", "t")[0], OK)
        s = json.loads(self.state.read_text())
        self.edit_state(members=s["members"] + [{"number": 2, "head": "h2", "partial": ["e2e"]}])
        rc, out = self.go("merge", "--apply", "--grant", "g")
        self.assertEqual(rc, mt.HALT, out)
        self.assertIn("second outstanding", out)
        self.edit_state(members=s["members"], partial={"number": 9, "merge_sha": "M9", "unchecked": ["x"]})
        rc, out = self.go("merge", "--apply", "--grant", "g")
        self.assertEqual(rc, mt.HALT, out)
        self.assertIn("#9 undecided", out)
        self.assertFalse([c for c in self.f.calls if c[:3] == ["gh", "pr", "merge"]])

    def test_kill_reverts_when_an_unchecked_check_fails_post_merge(self):
        self.land()
        self.f.post["M1"] = [mt._run("e2e", "failure")]
        rc, out = self.go("partial-kill")
        self.assertEqual(rc, RED)
        self.assertIn("KILL #1", out)
        self.assertIn("WOULD-REVERT #1", out)
        self.assertFalse(self.reverts(), "dry run must not revert")
        rc, out = self.go("partial-kill", "--apply")
        self.assertEqual(rc, RED)
        self.assertIn("REVERT #1 revert PR opened https://example.com/revert/1", out)
        self.assertIn("id=NODE1", self.reverts()[0])
        self.assertIn("NOOP", self.go("partial-kill")[1])  # decided: the record is cleared

    def test_kill_keeps_a_passing_pr_and_waits_for_a_running_check(self):
        self.land()
        self.f.post["M1"] = [mt._run("e2e", None, status="in_progress")]
        self.assertIn("PENDING #1", self.go("partial-kill")[1])
        self.f.post["M1"] = [mt._run("e2e", "success")]
        rc, out = self.go("partial-kill", "--apply")
        self.assertEqual(rc, OK)
        self.assertIn("KEPT #1", out)
        self.assertFalse(self.reverts())

    def test_a_check_that_never_ran_is_unverified_never_kept(self):
        self.land()
        self.assertIn("PENDING #1", self.go("partial-kill")[1])  # no runs yet, inside the wait
        self.f.post["M1"] = [mt._run("ci", "success")]  # CI finished without e2e
        rc, out = self.go("partial-kill")
        self.assertEqual(rc, RED)
        self.assertIn("UNVERIFIED #1 not KEPT: e2e", out)
        self.assertNotIn("KEPT #1", out)
        self.assertIn("partial", json.loads(self.state.read_text()), "record kept: it is still outstanding")
        self.f.post["M1"] = []  # no runs at all: waits, then times out
        self.edit_state(partial={**json.loads(self.state.read_text())["partial"], "merged_at": 0})
        rc, out = self.go("partial-kill", "--wait", "60")
        self.assertEqual(rc, RED)
        self.assertIn("UNVERIFIED #1", out)

    def test_skipped_or_neutral_is_not_kept(self):
        for verdict in ("skipped", "neutral"):
            if not self.state.exists():
                self.land()
            self.f.post["M1"] = [mt._run("e2e", verdict)]
            rc, out = self.go("partial-kill")
            self.assertEqual(rc, RED, verdict)
            self.assertIn("UNVERIFIED #1", out)
            self.assertNotIn("KEPT #1", out)

    def test_receipt_needs_a_named_check(self):
        with self.assertRaises(ValueError):
            pp.write(9, "h9", [" "], self.tmp)
        self.assertIsNone(pp.load(9, "h9", self.tmp))


if __name__ == "__main__":
    unittest.main()
