#!/usr/bin/env python3
"""Tests for feeder_order.py: recurring-class fix first, other fixes next, features last, stable, fail closed."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SC = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
import feeder_order as fo  # noqa: E402

ITEMS = [{"id": "f1", "kind": "feature"}, {"id": "x1", "kind": "fix", "class": "rare"},
         {"id": "f2", "kind": "feature"}, {"id": "x2", "kind": "fix", "class": "timeout"}]


class FeederOrder(unittest.TestCase):
    def test_order(self):
        ids = [i["id"] for i in fo.order(ITEMS, {"timeout": 3, "rare": 1})]
        self.assertEqual(ids, ["x2", "x1", "f1", "f2"])

    def test_starvation_cap_case_and_missing_class(self):
        its = [{"id": "x%d" % n, "kind": "Fix", "class": "timeout"} for n in range(5)] + [{"id": "f", "kind": "feature"}]
        self.assertEqual([i["id"] for i in fo.order(its, {"timeout": 9}, max_run=2)], ["x0", "x1", "f", "x2", "x3", "x4"])
        self.assertEqual([i["id"] for i in fo.order([{"id": "n", "kind": "bugfix"}, {"id": "r", "kind": "fix", "class": "timeout"}], {"timeout": 2})], ["r", "n"])
        for bad in ({"a": "x"}, []):
            with self.assertRaises(ValueError):
                fo.check(ITEMS, bad)
        with self.assertRaises(ValueError):
            fo.check([{"kind": "fix"}], {})

    def test_cli_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            led = Path(d) / "l.json"
            led.write_text(json.dumps({"timeout": 2}))
            run = lambda p: subprocess.run([sys.executable, str(SC / "feeder_order.py"), "--ledger", str(p)],
                                           input=json.dumps(ITEMS), capture_output=True, text=True)
            self.assertEqual(run(led).stdout.split(), ["x2", "x1", "f1", "f2"])
            self.assertEqual(run(Path(d) / "missing.json").returncode, 2)


if __name__ == "__main__":
    unittest.main()
