#!/usr/bin/env python3
"""Tests for the red-train flake rerun (merge_train.py --rerun-cmd) and the landing_watchdog flow alarms
(merges per hour target, PRs per landed train floor). Run: python3 scripts/test_train_flake_yield.py
"""
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SC = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SC))
import landing_watchdog as lw  # noqa: E402
import merge_train  # noqa: E402
import perun_policy as pp  # noqa: E402


class Rerun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="train-flake-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.wt = self.tmp / "wt"
        self.wt.mkdir()

    def gate(self, verify, rerun, retries=2):
        a = SimpleNamespace(repo=None, state=str(self.tmp / "s.json"), verify_cmd=verify, rerun_cmd=rerun, count_cmd="",
                            cap=None, retries=retries, gate_backoff=0, backoff=0, timeout=60)
        out = io.StringIO()
        t = merge_train.Train(a, merge_train.default_runner, out, lambda s: None)
        return t, t._gate(str(self.wt), "union"), out.getvalue()

    def test_rerun_pass_is_a_logged_flake(self):
        t, why, out = self.gate("echo boom; exit 1", 'test "$PERUN_LOW_LOAD" = 1 && grep -q boom "$PERUN_VERIFY_OUT"')
        self.assertEqual(why, "")
        self.assertIn("FLAKE union", out)
        self.assertEqual(t.state["flakes"], ["union"])

    def test_rerun_fail_is_deterministic_and_skips_full_reruns(self):
        counter = self.tmp / "n"
        t, why, out = self.gate(f"echo x >> {counter}; exit 1", "exit 1")
        self.assertEqual(why, "verify")
        self.assertEqual(len(counter.read_text().split()), 1)  # no full re-runs after a reproduced red
        self.assertIn("deterministic (1/1", out)
        self.assertNotIn("flakes", t.state)

    def test_no_rerun_cmd_keeps_the_old_retry_path(self):
        counter = self.tmp / "n"
        _, why, out = self.gate(f'echo x >> {counter}; test "$(wc -l < {counter})" -ge 2', "")
        self.assertEqual(why, "")
        self.assertIn("FLAKY union passed on attempt 2/3", out)


class Flow(unittest.TestCase):
    def test_trains_clusters_by_gap(self):
        self.assertEqual(lw.trains([]), 0)
        self.assertEqual(lw.trains([0, 10, 20, 1000, 1010]), 2)

    def test_slow_needs_waiting_green_prs_and_a_merge(self):
        f = lambda m, k, lim: lw._flow("main", m, k, 60, lim, lambda: [0] * m)
        self.assertIn("2.0 merged/h", f(2, 1, (5, 0)))
        self.assertIsNone(f(2, 0, (5, 0)))  # nothing waiting: idle, not slow
        self.assertIsNone(f(0, 3, (5, 0)))  # zero merged is the stall line's job
        self.assertIsNone(f(9, 3, (5, 0)))
        self.assertIsNone(f(2, 1, (0, 0)))  # off by default

    def test_yield_floor(self):
        t = [0, 10, 5000, 9000]  # 4 merges, 3 trains
        out = lw._flow("main", 4, 0, 60, (0, 2), lambda: t)
        self.assertIn("1.3 PRs per landed train < floor 2", out)
        self.assertIsNone(lw._flow("main", 4, 0, 60, (0, 1), lambda: t))

    def test_policy_keys(self):
        self.assertEqual(pp.validate({})["train_yield_floor"], 0)
        self.assertEqual(pp.validate({"merges_per_hour_target": 6})["merges_per_hour_target"], 6)
        for bad in (-1, 1.5, True, "3"):
            with self.assertRaises(ValueError):
                pp.validate({"train_yield_floor": bad})

    def test_check_cli_reports_flow_line(self):
        orig = (lw.probe, lw.flow_limits, lw.wip_cap)
        self.addCleanup(lambda: [setattr(lw, n, v) for n, v in zip(("probe", "flow_limits", "wip_cap"), orig)])
        lw.probe, lw.flow_limits, lw.wip_cap = (lambda c, m: ("main", 1, 2, 2)), (lambda: (6, 0)), (lambda: 0)
        buf = io.StringIO()
        old, sys.stdout = sys.stdout, buf
        try:
            rc = lw.check(["--minutes", "60"])
        finally:
            sys.stdout = old
        self.assertEqual(rc, 1)
        self.assertIn("Landing slow", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
