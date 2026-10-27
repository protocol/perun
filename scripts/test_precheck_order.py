#!/usr/bin/env python3
"""Tests for land_ready.precheck_order: shadow keeps order and logs, on reorders by feeder_order, empty input."""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"))
import land_ready  # noqa: E402

PRS = [{"number": 1, "title": "feat: a"}, {"number": 2, "title": "fix: b"}, {"number": 3, "title": "Add c"}]


class T(unittest.TestCase):
    def test_shadow_keeps_order_and_logs_would_be(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(land_ready.precheck_order(PRS, "shadow"), PRS)
        self.assertIn("#2 #1 #3", err.getvalue())

    def test_on_puts_fix_first(self):
        self.assertEqual([p["number"] for p in land_ready.precheck_order(PRS, "on")], [2, 1, 3])

    def test_off_and_empty(self):
        self.assertEqual(land_ready.precheck_order(PRS, "off"), PRS)
        self.assertEqual(land_ready.precheck_order([], "on"), [])

    def test_mode_spellings(self):
        for m in ("ON", "1", "True"):
            self.assertEqual([p["number"] for p in land_ready.precheck_order(PRS, m)], [2, 1, 3])

    def test_env_unset_is_shadow_in_subprocess(self):
        env = {k: v for k, v in os.environ.items() if k != "PERUN_PRECHECK_ORDER"}
        code = "import json,sys,land_ready;print(json.dumps([p['number'] for p in land_ready.precheck_order(json.loads(sys.argv[1]))]))"
        r = subprocess.run([sys.executable, "-c", code, json.dumps(PRS)], env=env, capture_output=True, text=True,
                           cwd=str(Path(land_ready.__file__).parent))
        self.assertEqual(json.loads(r.stdout), [1, 2, 3])
        self.assertIn("shadow precheck order: #2 #1 #3", r.stderr)

    def test_bad_item_returns_input(self):
        bad = [{"title": "x"}]
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(land_ready.precheck_order(bad, "on"), bad)


if __name__ == "__main__":
    unittest.main()
