#!/usr/bin/env python3
"""Regression test: a handback that says the lane is waiting on its background tests is flagged (advisory, never a
block) even when the process scan finds nothing, the case the scan alone missed."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_background_work_guard import run_check  # noqa: E402


class WaitClaim(unittest.TestCase):
    def flagged(self, msg, mode="warn"):
        rc, out, _ = run_check({"last_assistant_message": msg}, mode, lambda cwd: [])
        self.assertEqual(rc, 0)
        return bool(out) and "waiting on background work" in json.loads(out)["systemMessage"]

    def test_waiting_claim_is_flagged(self):
        for m in ("status=UNVERIFIED waiting on my background tests", "VERIFIED. Still running in the background."):
            self.assertTrue(self.flagged(m), m)

    def test_block_mode_flags_but_does_not_block(self):
        self.assertTrue(self.flagged("VERIFIED, waiting for the test suite", "block"))

    def test_plain_handback_and_off_mode_are_silent(self):
        self.assertFalse(self.flagged("status=VERIFIED"))
        self.assertFalse(self.flagged("VERIFIED waiting on background tests", "off"))


if __name__ == "__main__":
    unittest.main()
