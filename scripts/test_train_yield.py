#!/usr/bin/env python3
"""Tests for train_yield.py and its landing_watchdog line: yield, re-rides, empty ledger, zero trains."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"))
import landing_watchdog as lw  # noqa: E402
import train_yield as ty  # noqa: E402


class T(unittest.TestCase):
    def setUp(self):
        self.p = os.path.join(tempfile.mkdtemp(prefix="ty-"), "l.jsonl")

    def test_missing_and_empty_ledger_is_silent(self):
        self.assertEqual(ty.stats(self.p), (0, 0, {}))
        self.assertIsNone(ty.alarm(self.p))
        Path(self.p).write_text("")
        self.assertIsNone(ty.alarm(self.p))

    def test_low_yield_alarms_and_names_infra(self):
        for i in range(4):
            ty.record(self.p, f"t{i}", [10 + i, 20], [10 + i] if i == 0 else [])
        self.assertEqual(ty.stats(self.p)[:2], (4, 1))
        msg = ty.alarm(self.p)
        self.assertIn("1 of 4", msg)
        self.assertIn("infra", msg)

    def test_healthy_yield_is_silent(self):
        for i in range(4):
            ty.record(self.p, f"t{i}", [i, i + 100], [i])
        self.assertIsNone(ty.alarm(self.p))

    def test_reride_count_alarms_even_at_good_yield(self):
        for i in range(6):
            ty.record(self.p, f"t{i}", [7, 100 + i], [100 + i])
        self.assertEqual(ty.stats(self.p)[2], {"7": 5})
        self.assertIn("PR #7 re-rode 5 times", ty.alarm(self.p))

    def test_bad_lines_skipped(self):
        Path(self.p).write_text("not json\n{}\n")
        self.assertEqual(ty.stats(self.p)[:2], (0, 0))

    def test_yield_needs_four_trains(self):
        for i in range(3):
            ty.record(self.p, f"t{i}", [1, 2], [])
        self.assertIsNone(ty.alarm(self.p))

    def test_landed_pr_not_counted_as_reride_and_red_skipped(self):
        for i in range(6):
            ty.record(self.p, f"t{i}", [7, 100 + i], [100 + i])
        ty.record(self.p, "t9", [7], [7])
        self.assertEqual(ty.stats(self.p)[2], {})
        q = self.p + "2"
        for i in range(6):
            ty.record(q, f"r{i}", [1, 2], [], "red")
        self.assertEqual(ty.stats(q), (0, 0, {}))
        self.assertIsNone(ty.alarm(q))

    def test_cli_record_report_and_unwritable_ledger(self):
        sc = Path(ty.__file__)
        env = {**os.environ, "PERUN_TRAIN_LEDGER": self.p}
        r = subprocess.run([sys.executable, str(sc), "record", "t", "1 2", "1", "red"], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        r = subprocess.run([sys.executable, str(sc), "report"], env={**env, "PERUN_TRAIN_LEDGER": self.p}, capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.splitlines()[0]), (0, "trains started=0"))
        bad = {**os.environ, "PERUN_TRAIN_LEDGER": "/nonexistent-dir/x.jsonl"}
        r = subprocess.run([sys.executable, str(sc), "record", "t", "1", ""], env=bad, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("train_yield:", r.stderr)

    def test_watchdog_line_and_fail_open(self):
        os.environ["PERUN_TRAIN_LEDGER"] = self.p
        self.addCleanup(os.environ.pop, "PERUN_TRAIN_LEDGER")
        self.assertIsNone(lw._train_yield("/nonexistent"))
        for i in range(4):
            ty.record(self.p, f"t{i}", [1, 2], [])
        self.assertIn("0 of 4", lw._train_yield("/nonexistent"))


if __name__ == "__main__":
    unittest.main()
