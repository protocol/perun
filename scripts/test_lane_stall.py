#!/usr/bin/env python3
"""Tests for landing_watchdog per-lane stall alarm (lane_idle_h + lane_globs). Synthetic PR JSON; gh is mocked."""
import json
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

SC = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
import landing_watchdog as lw  # noqa: E402
import perun_policy as pp  # noqa: E402

NOW = time.time()
GLOBS = {"backend": ["api/*"], "app": ["app/*"]}
OK = [{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}]


def iso(h_ago):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - h_ago * 3600))


def run(merged, opened, cfg=(6, GLOBS)):
    def fake(args, cwd, timeout=15):
        return json.dumps(merged if args[args.index("--state") + 1] == "merged" else opened)
    with mock.patch.object(lw, "_run", fake):
        return lw._lanes("/x", "main", cfg, NOW)


class LaneStall(unittest.TestCase):
    def test_idle_lane_with_ready_prs_alarms_busy_lane_does_not(self):
        merged = [{"mergedAt": iso(0.1), "files": [{"path": "api/a.py"}]}, {"mergedAt": iso(9), "files": [{"path": "app/x.tsx"}]}]
        opened = [{"isDraft": False, "statusCheckRollup": OK, "files": [{"path": "app/y.tsx"}]},
                  {"isDraft": False, "statusCheckRollup": OK, "files": [{"path": "api/b.py"}]},
                  {"isDraft": True, "statusCheckRollup": OK, "files": [{"path": "app/z.tsx"}]}]
        out = run(merged, opened)
        self.assertIn("Lane stalled: app has 1 ready PRs, last merge 9.0 h ago (limit 6 h)", out)
        self.assertNotIn("backend", out)

    def test_no_merge_ever_alarms_and_no_ready_pr_is_quiet(self):
        opened = [{"isDraft": False, "statusCheckRollup": OK, "files": [{"path": "app/y.tsx"}]}]
        self.assertIn("none in the last 100 merged", run([], opened))
        self.assertIsNone(run([], []))

    def test_off_without_map_or_limit(self):
        self.assertIsNone(run([], [], (0, GLOBS)))
        self.assertIsNone(run([], [], (6, {})))

    def test_cross_lane_pr_credits_every_lane(self):
        both = [{"path": "api/a.py"}, {"path": "app/x.tsx"}]
        merged = [{"mergedAt": iso(0.1), "files": both}]
        opened = [{"isDraft": False, "statusCheckRollup": OK, "files": both}]
        self.assertIsNone(run(merged, opened))
        out = run([], opened)
        self.assertIn("backend has 1", out)
        self.assertIn("app has 1", out)

    def test_age_equal_limit_is_not_stalled(self):
        opened = [{"isDraft": False, "statusCheckRollup": OK, "files": [{"path": "app/y.tsx"}]}]
        self.assertIsNone(run([{"mergedAt": iso(5.99), "files": [{"path": "app/x"}]}], opened))
        self.assertIsNotNone(run([{"mergedAt": iso(6.1), "files": [{"path": "app/x"}]}], opened))

    def test_all_fails_open_when_lanes_raises(self):
        with mock.patch.object(lw, "_lanes", side_effect=RuntimeError("boom")), mock.patch.object(lw, "_train_yield", return_value=None):
            out = lw._all("/x", ("main", 0, 2, 2, []), 60, 0, (0, 0), (6, GLOBS))
        self.assertIn("Landing stalled", out)

    def test_line_cache_invalidates_on_lane_change(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d, mock.patch.dict("os.environ", {"PERUN_LANDING_DIR": d}), \
                mock.patch.object(lw, "cache_file", return_value=d + "/c.json"), mock.patch.object(lw, "settings", return_value=("warn", 60)), \
                mock.patch.object(lw, "probe", return_value=("main", 1, 0, 0, [])) as pr, \
                mock.patch.object(lw, "_all", return_value="L") as al:
            data = {"hook_event_name": "UserPromptSubmit", "cwd": d}
            with mock.patch.object(lw, "lane_cfg", return_value=(6, GLOBS)):
                lw._line(data, NOW)
                lw._line(data, NOW)
                self.assertEqual(pr.call_count, 1)
            with mock.patch.object(lw, "lane_cfg", return_value=(8, GLOBS)):
                lw._line(data, NOW)
            self.assertEqual(pr.call_count, 2)

    def test_policy_validates(self):
        self.assertEqual(pp.validate({"lane_idle_h": 6, "lane_globs": GLOBS})["lane_idle_h"], 6)
        for bad in ({"lane_globs": {"a": "x"}}, {"lane_globs": {"a": []}}, {"lane_idle_h": -1}):
            with self.assertRaises(ValueError):
                pp.validate(bad)


if __name__ == "__main__":
    unittest.main()
