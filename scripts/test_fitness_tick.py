"""fitness_tick.py: ALARM lines, consecutive-pass counting, and the closable gate (2 passes + a caller)."""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/fitness_tick.py"


def run(root, *a):
    return subprocess.run([sys.executable, str(SCRIPT), "--dir", f"{root}/fit", "--state", f"{root}/st.json",
                           "--root", f"{root}/repo", *a], capture_output=True, text=True)


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(f"{self.d}/fit")
        os.makedirs(f"{self.d}/repo")

    def check(self, name, code, msg="boom"):
        p = f"{self.d}/fit/{name}"
        pathlib.Path(p).write_text(f"#!/bin/sh\necho {msg}\nexit {code}\n")
        os.chmod(p, 0o755)

    def test_alarm_one_line_and_exit_1(self):
        self.check("a", 1, "queue stuck")
        r = run(self.d)
        self.assertEqual((r.returncode, r.stdout), (1, "ALARM a: queue stuck\n"))

    def test_missing_or_empty_dir_alarms_exit_2(self):
        r = run(self.d)  # fit/ exists but is empty
        self.assertEqual((r.returncode, r.stdout.startswith("ALARM no executable fitness checks")), (2, True))
        os.rmdir(f"{self.d}/fit")
        self.assertEqual(run(self.d).returncode, 2)

    def test_pass_exit_0_and_non_executable_ignored(self):
        self.check("a", 0)
        pathlib.Path(f"{self.d}/fit/notes.txt").write_text("x")
        r = run(self.d)
        self.assertEqual((r.returncode, r.stdout), (0, "ok a\n"))

    def test_closable_needs_two_passes_then_caller(self):
        self.check("a", 0)
        run(self.d)
        r = run(self.d, "closable", "a")
        self.assertEqual(r.returncode, 1)
        self.assertIn("2 consecutive", r.stdout)
        run(self.d)
        r = run(self.d, "closable", "a")
        self.assertEqual(r.returncode, 1)
        self.assertIn("nothing calls fitness_tick.py", r.stdout)
        pathlib.Path(f"{self.d}/repo/loop.sh").write_text("python3 fitness_tick.py\n")
        self.assertEqual(run(self.d, "closable", "a").stdout, "CLOSABLE a\n")

    def test_failure_resets_the_streak(self):
        self.check("a", 0)
        run(self.d)
        run(self.d)
        self.check("a", 1)
        run(self.d)
        self.check("a", 0)
        run(self.d)
        pathlib.Path(f"{self.d}/repo/loop.sh").write_text("python3 fitness_tick.py\n")
        self.assertEqual(run(self.d, "closable", "a").returncode, 1)

    def test_missing_check_not_closable_and_usage_exit_2(self):
        self.assertEqual(run(self.d, "closable", "nope").returncode, 1)
        self.assertEqual(run(self.d, "bogus").returncode, 2)


if __name__ == "__main__":
    unittest.main()
