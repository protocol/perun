#!/usr/bin/env python3
"""Tests for `pipeline_profile.py tests`: per-script gate cost ranking and the worker floor."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PP = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/pipeline_profile.py"


class TestsCmd(unittest.TestCase):
    def test_rank_and_floor(self):
        with tempfile.TemporaryDirectory() as d:
            t = Path(d) / "scripts/ci-tests.d"
            t.mkdir(parents=True)
            (t / "a-fast.sh").write_text("true\n")
            (t / "b-slow.sh").write_text("sleep 0.3\n")
            run = lambda *a: subprocess.run([sys.executable, str(PP), "tests", "--root", d, "--log", str(Path(d) / "t.tsv"), *a],
                                            capture_output=True, text=True)
            self.assertIn("would time 2", run().stdout)
            out = run("--run", "--workers", "2")
            self.assertEqual(out.returncode, 0, out.stderr)
            lines = out.stdout.splitlines()
            self.assertIn("b-slow.sh", lines[0])  # costliest first
            self.assertIn("W=2", lines[-1])
            self.assertEqual(run("--workers", "0").returncode, 2)
            (t / "c-red.sh").write_text("exit 1\n")
            self.assertEqual(run("--run").returncode, 1)  # a failing script is not a clean measurement
            self.assertEqual(run("--glob", "nope/*.sh").returncode, 2)


if __name__ == "__main__":
    unittest.main()
