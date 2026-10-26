#!/usr/bin/env python3
"""The destructive_guard.py stub must tell a core that fails to load apart from a core whose main() crashes: both block
(exit 2, because Claude Code allows on any other exit code), each with its own stderr message."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"


def run_with_core(core_src, command="git status"):
    with tempfile.TemporaryDirectory() as d:
        shutil.copy(SCRIPTS / "destructive_guard.py", d)
        (Path(d) / "destructive_guard_core.py").write_text(core_src)
        return subprocess.run([sys.executable, str(Path(d) / "destructive_guard.py")], input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": command}}), capture_output=True, text=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})


class StubCrash(unittest.TestCase):
    def test_main_crash_blocks_with_crash_message(self):
        r = run_with_core("def main():\n    raise RuntimeError('boom')\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("guard crashed (RuntimeError)", r.stderr)
        self.assertNotIn("could not load", r.stderr)

    def test_load_failure_blocks_with_load_message(self):
        r = run_with_core("def main(:\n")
        self.assertEqual(r.returncode, 2)
        self.assertIn("could not load (SyntaxError)", r.stderr)

    def test_unexpected_exit_code_blocks(self):
        self.assertEqual(run_with_core("def main():\n    raise SystemExit(1)\n").returncode, 2)

    def test_clean_exit_allows(self):
        self.assertEqual(run_with_core("def main():\n    return 0\n").returncode, 0)


if __name__ == "__main__":
    unittest.main()
