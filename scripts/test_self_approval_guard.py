#!/usr/bin/env python3
"""Tests: bypass_guard denies a lane writing .perun/approvals (gate overrides are human-only); reads pass; the lane preamble says so."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude/skills/agentic-delivery/scripts"))
import bypass_guard as bg  # noqa: E402

env = {"PATH": os.environ["PATH"]}  # nothing here reads host state


class Approvals(unittest.TestCase):
    def test_writes_denied(self):
        for c in ["echo ok > .perun/approvals/revert-guard", "touch .perun/approvals/x", "cp a .perun/approvals/x",
                  "bash -c 'tee .perun/approvals/x'", "python3 -c \"open('.perun/approvals/x','w')\""]:
            self.assertIn("verified human", bg.bypass(c), c)

    def test_reviewer_bypass_forms_denied(self):
        for c in ["find / -name x -fprint .perun/approvals/y", "cd .perun/approvals && echo 1 > revert-guard", "rm -r .perun/approvals",
                  "cp x $'\\x2e'perun/approvals/y", "P=.perun/approvals; echo x > $P/a", "ln -s .perun/approvals l && echo x > l/a",
                  "echo 'unterminated approvals", "find .perun/approvals -delete", "cat .perun/approvals/x > y"]:
            self.assertIn("verified human", bg.bypass(c), c)

    def test_reads_and_unrelated_pass(self):
        for c in ["cat .perun/approvals/x", "ls .perun/approvals/", "grep ok .perun/approvals/x | wc -l", "echo hi > out.txt"]:
            self.assertEqual(bg.bypass(c), "", c)

    def test_preamble_forbids_it(self):
        t = (ROOT / ".claude/skills/agentic-delivery/templates/lane-preamble.md").read_text()
        self.assertIn(".perun/approvals", t)
        self.assertIn("scripts/bypass_guard.py", t)


if __name__ == "__main__":
    unittest.main()
