#!/usr/bin/env python3
"""handback.py tests-count: a done claim needs Tests: X/X with X>0 (or No-Tests-Reason:). Reuses test_handback.py's fixture."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_handback as th  # noqa: E402


class Count(unittest.TestCase):
    setUp, tearDown, git, commit, hb = (th.T.__dict__[n] for n in ("setUp", "tearDown", "git", "commit", "hb"))

    def lane_with(self, msg):
        self.git("checkout", "-q", "-b", "lane")
        self.commit("changelog.d/x.md", "### Added\n- x\n", "frag")
        return self.commit("work.txt", "w\n", msg)

    def run_hb(self, msg, mode="enforce"):
        if mode:
            self.env["HANDBACK_TESTS_COUNT"] = mode
        return self.hb(self.lane_with(msg))

    def bad(self, msg):
        r = self.run_hb(msg)
        self.assertEqual(r.returncode, 4, msg + r.stdout)
        self.assertIn("UNVERIFIED: no passing test count", r.stdout)
        self.assertNotIn("GREEN", r.stdout)

    def test_full_flow_enforce_valid_count_is_green(self):
        r = self.run_hb("work\n\nTests: 12/12")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("handback GREEN", r.stdout)
        self.assertNotIn("tests-count", r.stdout)

    def test_valid_variants_pass(self):
        for m in ("w\n\nTests: 3/3 and 4/4", "w\n\n> Tests (unit): 2/2", "w\n\n- tests: 1/1"):
            with self.subTest(m=m):
                self.setUp()
                self.assertEqual(self.run_hb(m).returncode, 0)
                self.tearDown()

    def test_bad_claims_are_unverified(self):
        for t in ("Tests: 0/0", "Tests: 3/5", "Tests: skipped", "Tests: blocked by host load", "no count at all",
                  "Tests: 5/5 and 5/6", "Tests: 0/0 and 0/0"):
            with self.subTest(t=t):
                self.setUp()
                self.bad("work\n\n" + t)
                self.tearDown()

    def test_failing_line_beats_later_valid_line(self):
        self.bad("work\n\nTests: 5/6\nTests: 9/9")

    def test_reason_trailer_waives(self):
        self.assertEqual(self.run_hb("work\n\nTests: 0/0\nNo-Tests-Reason: docs only").returncode, 0)

    def test_blocked_head_is_exempt(self):
        self.assertEqual(self.run_hb("BLOCKED: host load gate\n\nTests: 0/0").returncode, 0)

    def test_counts_read_across_lane_commits(self):
        self.lane_with("work\n\nTests: 1/1")
        sha = self.commit("more.txt", "m\n", "more")
        self.env["HANDBACK_TESTS_COUNT"] = "enforce"
        self.assertEqual(self.hb(sha).returncode, 0)

    def test_default_shadow_warns_and_stays_green(self):
        self.env.pop("HANDBACK_TESTS_COUNT", None)
        r = self.run_hb("work", mode=None)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("tests-count shadow", r.stdout)

    def test_off_is_silent(self):
        r = self.run_hb("work", mode="off")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("tests-count", r.stdout)


if __name__ == "__main__":
    unittest.main()
