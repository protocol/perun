#!/usr/bin/env python3
"""Offline tests for clock_lint.py: CLI output, exit codes, --base changed-files mode, COULD_NOT_CHECK."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINT = os.path.join(ROOT, ".claude/skills/agentic-delivery/scripts/clock_lint.py")


def lint(*args):
    p = subprocess.run([sys.executable, LINT, *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


class ClockLint(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))

    def put(self, name, text):
        p = os.path.join(self.d, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_finding_format_and_exit(self):
        p = self.put("test_a.py", "import time\nx = time.time()\n")
        rc, out = lint(p)
        self.assertEqual(rc, 1)
        self.assertEqual(out.strip(), "%s:2: real clock in test; pin a fake clock or inject now" % p)

    def test_marker_and_allow_and_non_test(self):
        self.assertEqual(lint(self.put("test_b.py", "from freezegun import freeze_time\ndatetime.now()\n"))[0], 0)
        self.assertEqual(lint(self.put("c.test.ts", "// clock-lint: allow\nDate.now()\n"))[0], 0)
        self.assertEqual(lint(self.put("app.py", "datetime.now()\n"))[0], 0)

    def test_each_language(self):
        for name, src in (("t.spec.js", "new Date()\n"), ("x_test.go", "time.Now()\n"),
                          ("test-x.sh", "echo $(date +%s)\n"), ("tests/test_z.py", "datetime.utcnow()\n")):
            self.assertEqual(lint(self.put(name, src))[0], 1, name)
        self.assertEqual(lint(self.put("t2.spec.js", "new Date(0)\nDate.now = () => 1\n"))[0], 0)

    def test_unreadable_is_not_silent(self):
        rc, out = lint(os.path.join(self.d, "test_nope.py"))
        self.assertEqual(rc, 2)
        self.assertIn("COULD_NOT_CHECK", out)

    def test_base_mode_only_changed_files(self):
        g = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *a],
                                      cwd=self.d, check=True, capture_output=True, text=True)
        g("init", "-q")
        self.put("test_old.py", "time.time()\n")
        g("add", "."), g("commit", "-qm", "base")
        base = g("rev-parse", "HEAD").stdout.strip()
        self.put("test_new.py", "time.time()\n")
        g("add", "."), g("commit", "-qm", "new")
        rc, out = lint("--root", self.d, "--base", base)
        self.assertEqual((rc, out.strip()), (1, "test_new.py:1: real clock in test; pin a fake clock or inject now"))
        self.assertEqual(lint("--root", self.d, "--base", "nope-ref")[0], 2)

    def test_selftest(self):
        self.assertEqual(lint("--selftest")[0], 0)


if __name__ == "__main__":
    unittest.main()
