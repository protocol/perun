#!/usr/bin/env python3
"""Tests: a passes-alone-fails-in-parallel test, once moved to the serial project, leaves the candidate list, is never quarantined, and blocks as a real bug."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

FL = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/flake_ledger.py"


def fl(d, *args, stdin=""):
    r = subprocess.run([sys.executable, str(FL), "--dir", d, *args], input=stdin, capture_output=True, text=True)
    return r.returncode, r.stdout


class SerialProject(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.d = self.t.name
        self.addCleanup(self.t.cleanup)
        for tree in ("t1", "t2", "t3"):
            fl(self.d, "record", "--tree", tree, stdin="SUITE test_port\nPASS test_port\nSUITE test_flaky\nFAIL test_flaky\nPASS test_flaky\n")

    def test_candidate_then_moved(self):
        rc, out = fl(self.d, "serial")
        self.assertEqual(rc, 1)
        self.assertIn("SERIAL-CANDIDATE test_port", out)
        self.assertEqual(fl(self.d, "serial-move", "test_port")[0], 0)
        self.assertEqual(fl(self.d, "serial"), (0, ""))  # moved: no longer a candidate

    def test_moved_test_failure_is_blocking_real_bug_never_quarantined(self):
        fl(self.d, "serial-move", "test_port")
        fl(self.d, "quarantine")
        self.assertNotIn("test_port", Path(self.d, "quarantine.json").read_text())
        self.assertIn("test_flaky", Path(self.d, "quarantine.json").read_text())  # the real flake still quarantines
        rc, out = fl(self.d, "check", "test_port", "--tree", "t1")
        self.assertEqual(rc, 1)
        self.assertIn("BLOCKING test_port (serial-project test: a failure here is a real bug", out)

    def test_move_is_idempotent(self):
        fl(self.d, "serial-move", "b", "a")
        self.assertEqual(fl(self.d, "serial-move", "a")[1], "serial-project: 2 test(s)\n")


if __name__ == "__main__":
    unittest.main()
