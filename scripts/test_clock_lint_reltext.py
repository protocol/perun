#!/usr/bin/env python3
"""Offline tests for clock_lint.py's day/week-relative text advisory and Playwright fake-clock markers."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINT = os.path.join(ROOT, ".claude/skills/agentic-delivery/scripts/clock_lint.py")
WEEK = "await expect(page.getByText('No demos yet this week')).toBeVisible();\n"


def lint(name, text):
    d = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    r = subprocess.run([sys.executable, LINT, p], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


class RelText(unittest.TestCase):
    def test_week_text_and_new_date_flagged(self):
        rc, out = lint("a.spec.ts", "const d = new Date();\n" + WEEK)
        self.assertIn("a.spec.ts:1: real clock in test", out)
        self.assertIn("a.spec.ts:2: advisory: day/week-relative text", out)
        self.assertEqual(rc, 1)

    def test_week_text_alone_is_advisory_only(self):
        rc, out = lint("a.spec.ts", WEEK)
        self.assertIn(":1: advisory", out)
        self.assertEqual(rc, 0)

    def test_playwright_clock_silences_advisory_not_real_clock(self):
        for m in ("await page.clock.setFixedTime(new Date('2026-01-05'));", "await page.clock.install({ time: 0 });",
                  "await page.clock.pauseAt(0);"):
            rc, out = lint("a.spec.ts", m + "\nconst d = new Date();\n" + WEEK)
            self.assertEqual(rc, 1, m)
            self.assertIn(":2: real clock", out)
            self.assertNotIn("advisory", out)

    def test_node_fake_clock_exempts_all(self):
        rc, out = lint("a.spec.ts", "jest.useFakeTimers();\nconst d = new Date();\n" + WEEK)
        self.assertEqual((rc, out), (0, ""))

    def test_myclock_not_a_marker(self):
        self.assertIn("advisory", lint("a.spec.ts", "myclock.install();\n" + WEEK)[1])

    def test_non_assert_and_comment_not_advisory(self):
        for src in ("await page.getByText('Next week').click();\n",
                    "expect(total).toBe(3); // updated today\n",
                    "assert total == 3  # updated today\n"):
            self.assertEqual(lint("a.spec.ts" if "expect" in src or "click" in src else "test_a.py", src), (0, ""), src)

    def test_elapsed_timing_and_plain_text_not_advisory(self):
        rc, out = lint("a.spec.ts", "const start = performance.now();\nexpect(performance.now() - start).toBeLessThan(5000);\n"
                       "await expect(page.getByText('Welcome')).toBeVisible();\n")
        self.assertEqual((rc, out), (0, ""))

    def test_python_and_escape(self):
        self.assertIn(":2: advisory", lint("test_a.py", "def test_a():\n    assert page.text == 'Nothing today'\n")[1])
        self.assertEqual(lint("test_a.py", "def test_a():\n    assert t == 'x today'  # clock-lint: allow\n")[1], "")


if __name__ == "__main__":
    unittest.main()
