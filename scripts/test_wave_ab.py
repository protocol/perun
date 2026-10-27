"""Wave AB: shared queue-eligibility rule, base-fix fast lane, lane-overlap plan check."""
import os
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "agentic-delivery", "scripts")
sys.path.insert(0, D)
import landing_watchdog as lw  # noqa: E402
import merge_train as mt  # noqa: E402
import union_overlap as uo  # noqa: E402


class Blocker(unittest.TestCase):
    def test_one_rule_for_train_and_watchdog(self):
        ok = {"isDraft": False, "mergeable": "MERGEABLE"}
        ok = {**ok, "isCrossRepository": False}
        self.assertEqual(lw.blocker(ok), "")
        self.assertEqual(lw.blocker({**ok, "isDraft": True}), "draft")
        self.assertIn("fork", lw.blocker({**ok, "isCrossRepository": True}))
        self.assertEqual(lw.blocker({**ok, "isCrossRepository": True}, allow_forks=True), "")
        self.assertIn("mergeable=None", lw.blocker({"isDraft": False, "isCrossRepository": False}))  # fail closed
        self.assertEqual(lw.blocker({"isCrossRepository": False, "mergeable": "MERGEABLE"}), "draft")  # missing isDraft
        self.assertIn("fork", lw.blocker({"isDraft": False, "mergeable": "MERGEABLE"}))  # missing isCrossRepository
        self.assertIs(mt.blocker, lw.blocker)  # no second copy in the train


class Green(unittest.TestCase):
    pr = {"isDraft": False, "isCrossRepository": False, "mergeable": "MERGEABLE",
          "statusCheckRollup": [{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}]}

    def test_unknown_mergeable_still_counts_waiting(self):
        self.assertTrue(lw.green({**self.pr, "mergeable": "UNKNOWN"}))
        self.assertFalse(lw.green({**self.pr, "mergeable": "CONFLICTING"}))

    def test_allow_forks_threads_through(self):
        fork = {**self.pr, "isCrossRepository": True}
        self.assertFalse(lw.green(fork))
        self.assertTrue(lw.green(fork, allow_forks=True))


class Parked(unittest.TestCase):
    def test_parked_fork_reports_parked(self):
        t = mt.Train.__new__(mt.Train)
        t.a = SimpleNamespace(allow_forks=False)
        t._held = lambda pr: ""
        pr = {"number": 5, "isDraft": False, "isCrossRepository": True, "mergeable": "MERGEABLE"}
        self.assertTrue(t._ineligible(pr, {"5": {"reason": "x"}}).startswith("parked"))


class BaseFixLane(unittest.TestCase):
    def train(self):
        t = mt.Train.__new__(mt.Train)
        t.a = SimpleNamespace(base_fix=1, base="main", admit_red=False)
        t.say = lambda *_: None
        t._latest = lambda sha: {"ci": {"status": "completed", "conclusion": "failure"}}
        return t

    def test_fix_rides_alone_on_red_base(self):
        m = [{"number": 1}, {"number": 2}]
        self.assertFalse(self.train().red_base("abcdef0", m, lane=True))
        self.assertEqual(m, [{"number": 1}])

    def test_merge_refuses_longer_lineup(self):
        m = [{"number": 1}, {"number": 2}]
        self.assertTrue(self.train().red_base("abcdef0", m))
        self.assertEqual(len(m), 2)


class LaneOverlap(unittest.TestCase):
    def test_plan_flags_open_pr_files(self):
        d = tempfile.mkdtemp()
        g = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@example.com", *a], check=True, capture_output=True)
        g("init", "-q", "-b", "main")
        g("commit", "-q", "--allow-empty", "-m", "base")
        g("checkout", "-q", "-b", "pr")
        open(os.path.join(d, "a.txt"), "w").close()
        g("add", "a.txt")
        g("commit", "-q", "-m", "pr")
        self.assertEqual(uo.overlap(d, "main", [], ["pr"], ["a.txt", "b.txt"]), ["a.txt"])
        self.assertEqual(uo.overlap(d, "main", [], ["pr"], ["b.txt"]), [])
        with self.assertRaises(uo.Fail):
            uo.overlap(d, "main", [], ["nope"], ["a.txt"])
        self.assertEqual(uo.overlap(d, "main", [], ["pr"], ["./x/../a.txt"]), ["a.txt"])  # normalized
        cli = lambda *a: uo.main(["--repo", d, "--base", "main", *a])
        self.assertEqual(cli("--plan", "a.txt", "--other", "pr"), 1)
        self.assertEqual(cli("--plan", "b.txt", "--other", "pr"), 0)
        self.assertEqual(cli("--plan", "a.txt"), 2)  # empty --other
        for bad in ("/etc/x", "../x", "dir/", "."):
            self.assertEqual(cli("--plan", bad, "--other", "pr"), 2, bad)


if __name__ == "__main__":
    unittest.main()
