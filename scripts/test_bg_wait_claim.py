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
    def flagged(self, msg, mode="warn", bg=lambda cwd: []):
        rc, out, _ = run_check({"last_assistant_message": msg}, mode, bg)
        self.assertEqual(rc, 0)
        return bool(out) and "waiting on background work" in json.loads(out)["systemMessage"]

    def test_waiting_claim_is_flagged(self):
        for m in ("status=UNVERIFIED waiting on my background tests", "VERIFIED. Still running in the background."):
            self.assertTrue(self.flagged(m), m)

    def test_common_wordings_are_flagged(self):
        for m in ("tests are running in the background", "waiting on the full test suite", "waiting for the unit tests",
                  "waiting on the e2e tests", "waiting on pytest", "waiting on the gate", "waiting for CI to finish",
                  "waiting on pre-push", "tests still running", "background tests running", "awaiting the test run",
                  "waiting for the bg tests", "waiting on result of the tests", "pytest still running",
                  "waiting for the integration tests", "waiting on the browser tests", "waiting on all the tests",
                  "waiting on both test suites", "waiting on the playwright run", "waiting on npm test",
                  "waiting on cargo build", "waiting on GitHub Actions", "waiting for the workflow",
                  "the pytest run is still running", "tests running in background", "e2e tests still going",
                  "waiting on tests - no failures so far", "waiting on tests (no failures so far)",
                  "waiting on tests \u2014 not yet green", "tests are still running after review",
                  "waiting on tests that I ran", "waiting on the test run I ran",
                  "I ran the suite and I am waiting on CI"):
            self.assertTrue(self.flagged(m), m)

    def test_negated_or_unrelated_claims_are_silent(self):
        for m in ("Not waiting on tests; all done", "no longer waiting for the build", "no background tests are running",
                  "never waiting on background", "waiting on owner approval", "VERIFIED; tests passed 12/12",
                  "nothing waiting on tests", "nothing is waiting on lint", "blockers=waiting on owner to run tests",
                  "waiting on owner to approve CI", "waiting on the gate decision from owner",
                  "waiting on the lint fixes from the owner", "parent: wait for CI before merge", "waiting for CI not needed",
                  "result=killed my dev server that was running in the background",
                  "tests passed; the earlier run that was running in the background finished",
                  "CI on main is still running a flaky job", "pre-existing failure, main CI is still running red"):
            self.assertFalse(self.flagged(m), m)

    def test_negation_in_an_earlier_clause_does_not_hide_a_claim(self):
        self.assertTrue(self.flagged("no flakes, waiting on CI"))

    def test_fenced_log_and_owner_command_lines_are_ignored(self):
        self.assertFalse(self.flagged("status=VERIFIED\n```\nwaiting on the build\n```\n! echo waiting on tests"))

    def test_blind_scan_still_flags_the_claim(self):
        self.assertTrue(self.flagged("UNVERIFIED waiting on my background tests", bg=lambda cwd: None))

    def test_found_background_work_emits_one_message(self):
        _, out, _ = run_check({"last_assistant_message": "waiting on my tests"}, "warn", lambda cwd: [(42, "pytest -q")])
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("still running from its worktree", json.loads(out)["systemMessage"])

    def test_block_mode_flags_but_does_not_block(self):
        self.assertTrue(self.flagged("VERIFIED, waiting for the test suite", "block"))

    def test_plain_handback_and_off_mode_are_silent(self):
        self.assertFalse(self.flagged("status=VERIFIED"))
        self.assertFalse(self.flagged("VERIFIED waiting on background tests", "off"))


if __name__ == "__main__":
    unittest.main()
