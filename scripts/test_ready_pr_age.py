#!/usr/bin/env python3
"""Tests for the landing_watchdog ready-PR age alarm (percentiles, thresholds, off, policy keys)."""
import sys
import unittest
from pathlib import Path

SC = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
import landing_watchdog as lw  # noqa: E402
import perun_policy as pp  # noqa: E402


class ReadyAge(unittest.TestCase):
    def test_percentile_nearest_rank(self):
        xs = list(range(1, 11))
        self.assertEqual((lw.pct(xs, 50), lw.pct(xs, 90)), (5, 9))

    def test_thresholds(self):
        ages = [1, 2, 3, 4, 30]
        self.assertIsNone(lw._age(ages, (0, 0)))  # off
        self.assertIsNone(lw._age(ages, (5, 40)))  # p50 3, p90 30: both under
        self.assertIn("p90 30.0 h", lw._age(ages, (0, 24)))  # p90 over
        self.assertIn("p50 3.0 h", lw._age(ages, (2, 0)))  # p50 over
        self.assertIsNone(lw._age([], (1, 1)))  # no green PRs

    def test_probe_feeds_age_into_the_line(self):
        import json
        import time
        import unittest.mock as m
        hrs = lambda h: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - h * 3600))
        prs = [{"isDraft": False, "isCrossRepository": False, "mergeable": "MERGEABLE", "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS", "completedAt": hrs(10)}], "createdAt": hrs(99)},
               {"isDraft": False, "isCrossRepository": False, "mergeable": "MERGEABLE", "statusCheckRollup": [{"status": "COMPLETED", "conclusion": "SUCCESS"}], "createdAt": "garbage"}]
        def run(args, cwd, timeout=15):
            return json.dumps(prs) if args[:2] == ["gh", "pr"] else "main" if "symbolic-ref" in args else ""
        with m.patch.object(lw, "_run", run), m.patch.object(lw, "default_branch", lambda c: "main"):
            probed = lw.probe(".", 60)
        self.assertEqual(len(probed[4]), 1)  # the bad createdAt is dropped, not fatal
        self.assertAlmostEqual(probed[4][0], 10, delta=0.1)  # last-green time, not creation
        self.assertIn("Ready PRs aging", lw._all(".", probed, 60, 0, (5, 0)))
        self.assertNotIn("Ready PRs aging", lw._all(".", probed, 60, 0, (0, 0)) or "")

    def test_policy_keys(self):
        self.assertEqual(pp.validate({})["ready_age_p90_h"], 0)
        self.assertEqual(pp.validate({"ready_age_p50_h": 6})["ready_age_p50_h"], 6)
        with self.assertRaises(ValueError):
            pp.validate({"ready_age_p50_h": -1})


if __name__ == "__main__":
    unittest.main()
