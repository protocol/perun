#!/usr/bin/env python3
"""Tests: slot floors scale with core count, fan-out waits for its floor instead of shrinking, and no shell gate hardcodes xargs -P N."""
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude/skills/agentic-delivery/scripts"))
os.environ["PERUN_FANOUT_WAIT_SECS"] = "0"  # never sleep in tests
import perun_policy as pp  # noqa: E402


class Scaling(unittest.TestCase):
    def test_floor_scales_with_nproc(self):
        self.assertEqual(pp.slot_floor(4), 2)
        self.assertEqual(pp.slot_floor(88), 11)
        self.assertEqual(pp.heavy_slots(88, load1=200.0, idle_pct=0.0), 11)  # saturated big host still gets its floor
        self.assertEqual(pp.heavy_slots(4, load1=9.0), 2)  # small host unchanged

    def test_fanout_waits_then_never_shrinks_below_floor(self):
        reads = iter([(39.0, 0.0)] * 3 + [(2.0, 90.0)])
        slept = []
        n = pp.fanout_workers(88, lambda: next(reads), wait=60, sleep=slept.append, now=lambda: len(slept))
        self.assertEqual((n, len(slept)), (79, 3))  # waited three reads, then took the idle cores
        t = [0]
        n = pp.fanout_workers(88, lambda: (39.0, 0.0), wait=2, sleep=lambda s: t.__setitem__(0, t[0] + 1), now=lambda: t[0])
        self.assertEqual(n, 11)  # still busy after the wait: the floor, never 2

    def test_floor_never_exceeds_cores_and_bad_wait_defaults(self):
        self.assertEqual((pp.slot_floor(1), pp.slot_floor(2)), (1, 2))
        os.environ["PERUN_FANOUT_WAIT_SECS"] = "abc"
        self.assertEqual(pp._wait_secs(), 30.0)
        os.environ["PERUN_FANOUT_WAIT_SECS"] = "0"

    def test_idle_host_uses_idle_cores(self):
        self.assertEqual(pp.fanout_workers(88, lambda: (1.0, 100.0), wait=0), 88)

    def test_no_hardcoded_xargs_parallelism_in_shell_gates(self):
        bad = [str(p.relative_to(ROOT)) for p in list((ROOT / "scripts").glob("*.sh")) + list((ROOT / ".claude/skills").glob("*/scripts/*.sh"))
               if not p.name.startswith("test") and re.search(r"xargs[^\n|]*\s-P\s*[0-9]", p.read_text())]
        self.assertEqual(bad, [], "xargs -P must scale with getconf _NPROCESSORS_ONLN, not a literal")


if __name__ == "__main__":
    unittest.main()
