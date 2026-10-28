#!/usr/bin/env python3
"""Tests: the landing watchdog surfaces an uncovered/old red main (red_main.py) only when a threshold is set, and fails open."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"))
import landing_watchdog as lw  # noqa: E402


class RedWatchdog(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.cwd = self.t.name
        Path(self.cwd, ".claude").mkdir()
        old = time.time() - 3 * 3600
        Path(self.cwd, ".claude/red-main.json").write_text(json.dumps([{"id": "t_e2e", "since": old}]))
        self.pol = Path(self.cwd, "policy.json")
        os.environ["PERUN_POLICY"] = str(self.pol)
        self.addCleanup(os.environ.pop, "PERUN_POLICY", None)

    def test_alarm_when_threshold_set(self):
        self.pol.write_text('{"red_uncovered_max": 1}')
        out = lw._red(self.cwd)
        self.assertIn("Red main needs an owner", out)
        self.assertIn("UNCOVERED t_e2e", out)

    def test_silent_when_off_or_covered(self):
        self.pol.write_text("{}")
        self.assertIsNone(lw._red(self.cwd))
        self.pol.write_text('{"red_uncovered_max": 1}')
        Path(self.cwd, ".claude/red-main.json").write_text(json.dumps([{"id": "t", "since": 0, "owner": "lane-a"}]))
        self.assertIsNone(lw._red(self.cwd))

    def test_missing_or_bad_list_with_threshold_alarms_not_silent(self):
        self.pol.write_text('{"red_uncovered_max": 1}')
        os.remove(Path(self.cwd, ".claude/red-main.json"))
        self.assertIn("Red-main check failed (rc 2)", lw._red(self.cwd))
        Path(self.cwd, ".claude/red-main.json").write_text("not json")
        self.assertIn("Red-main check failed (rc 2)", lw._red(self.cwd))

    def test_missing_list_threshold_off_is_silent(self):
        self.pol.write_text("{}")
        os.remove(Path(self.cwd, ".claude/red-main.json"))
        self.assertIsNone(lw._red(self.cwd))


if __name__ == "__main__":
    unittest.main()
