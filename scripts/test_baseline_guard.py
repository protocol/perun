"""baseline_guard.py: solo re-run drops load failures, records load, refuses a suspect run, writes nothing on refusal."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/baseline_guard.py"


def run(ids, *extra):
    d = tempfile.mkdtemp()
    pathlib.Path(d, "fails.txt").write_text("\n".join(ids) + "\n")
    rerun = pathlib.Path(d, "rerun.sh")  # test id starting with "real" fails solo, anything else passes
    rerun.write_text('#!/bin/sh\ncase "$1" in real*) exit 1;; esac\nexit 0\n')
    rerun.chmod(0o755)
    out = os.path.join(d, "base.json")
    r = subprocess.run([sys.executable, str(SCRIPT), "--fails", f"{d}/fails.txt", "--rerun", f"{rerun} {{id}}", "--out", out, "--max-load", "1e9", *extra],
                       capture_output=True, text=True, env={**os.environ, "PERUN_GATE_CORES": "4"})
    return r, out


class T(unittest.TestCase):
    def test_solo_passes_are_dropped_and_load_recorded(self):
        r, out = run(["real_a", "load_b", "load_c"])
        self.assertEqual(r.returncode, 0)
        b = json.load(open(out))
        self.assertEqual((b["fails"], b["flaky"]), (["real_a"], ["load_b", "load_c"]))
        self.assertIn("load1", b)

    def test_refuses_far_above_normal_and_writes_nothing(self):
        r, out = run([f"real_{i}" for i in range(10)], "--normal", "2")
        self.assertEqual(r.returncode, 1)
        self.assertIn("REFUSE baseline: 10 failures", r.stdout)
        self.assertFalse(os.path.exists(out))

    def test_within_normal_is_stored(self):
        self.assertEqual(run([f"real_{i}" for i in range(6)], "--normal", "2")[0].returncode, 0)

    def test_refuses_when_host_load_above_max(self):
        r, out = run(["real_a"], "--max-load", "-1")
        self.assertEqual((r.returncode, os.path.exists(out)), (1, False))

    def test_unreadable_fails_file_exit_2(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--fails", "/nonexistent/f", "--rerun", "true", "--out", "/dev/null"],
                           capture_output=True, text=True, env={**os.environ, "PERUN_GATE_CORES": "4"})
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
