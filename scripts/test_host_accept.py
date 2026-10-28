#!/usr/bin/env python3
"""Tests: host_accept.py accepts a merge host only when reset, auto-reset and memory-cap/reserve are all verified; fails closed on bad input."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HA = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/host_accept.py"
E = {"verified": True, "evidence": "drill log 7", "date": "2026-01-02"}
OK = {"operator_reset": E, "auto_reset": E, "mem_caps": {**E, "reserved_mb": 1024}}


def run(cfg, raw=None):
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "h.json"
        if cfg is not None:
            f.write_text(raw if raw is not None else json.dumps(cfg))
        r = subprocess.run([sys.executable, str(HA), "--file", str(f)], capture_output=True, text=True)
        return r.returncode, r.stdout


class HostAccept(unittest.TestCase):
    def test_all_three_verified_accepted(self):
        self.assertEqual(run(OK), (0, "ACCEPTED\n"))

    def test_each_property_alone_blocks(self):
        for k in OK:
            rc, out = run({**OK, k: {**OK[k], "verified": False}})
            self.assertEqual((rc, out), (1, f"NOT-ACCEPTED {k}\n"))

    def test_evidence_and_date_required(self):
        for bad in ({**E, "evidence": " "}, {k: v for k, v in E.items() if k != "evidence"}, {**E, "date": "2999-01-01"}):
            self.assertEqual(run({**OK, "auto_reset": bad})[0], 1, bad)
        self.assertEqual(run({**OK, "auto_reset": {**E, "date": "x"}})[0], 2)  # unparseable date fails closed

    def test_string_yes_is_not_verified(self):
        self.assertEqual(run({**OK, "auto_reset": {**E, "verified": "yes"}})[0], 1)

    def test_mem_caps_need_a_reserve(self):
        self.assertEqual(run({**OK, "mem_caps": E})[0], 1)
        self.assertEqual(run({**OK, "mem_caps": {**E, "reserved_mb": 0}})[0], 1)
        self.assertEqual(run({**OK, "mem_caps": {**E, "reserved_mb": True}})[0], 1)

    def test_fail_closed(self):
        self.assertEqual(run(None)[0], 2)
        self.assertEqual(run(OK, raw="{")[0], 2)
        self.assertEqual(run({k: v for k, v in OK.items() if k != "mem_caps"})[0], 2)
        self.assertEqual(run({**OK, "operator_reset": True})[0], 2)  # non-object entry


if __name__ == "__main__":
    unittest.main()
