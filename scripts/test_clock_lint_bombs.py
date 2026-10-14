#!/usr/bin/env python3
"""End-to-end checks for clock_lint.py date-literal time bombs; "today" is always injected via --today."""
import os, subprocess, sys, tempfile, unittest

LINT = os.path.join(os.path.dirname(__file__), "..", ".claude", "skills", "agentic-delivery", "scripts", "clock_lint.py")
SRC = "SUNSET = date(2026, 10, 20)\n\n\ndef live():\n    return date.today() < SUNSET\n"


def lint(*a):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "rule_gate.py")
        with open(p, "w") as fh:
            fh.write(SRC)
        r = subprocess.run([sys.executable, LINT, "--today", "2026-10-14", *a, p], capture_output=True, text=True)
        return r.returncode, r.stdout.replace(p, "F")


class Bombs(unittest.TestCase):
    def test_urgent_warns_without_failing(self):
        rc, out = lint()
        self.assertIn("F:1: date literal compared with real clock; expires 2026-10-20 (URGENT: 6d)", out)
        self.assertEqual(rc, 0)

    def test_strict_fails(self):
        self.assertEqual(lint("--strict")[0], 1)


if __name__ == "__main__":
    unittest.main()
