#!/usr/bin/env python3
"""destructive_guard.py is a stub that runs destructive_guard_core.py from the bytecode cache: it must cache the core,
keep the guard's exit codes, expose the core's names for importers, and block (exit 2) when the core is missing."""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"
STUB = SCRIPTS / "destructive_guard.py"


def run(path, command, prefix=None):
    env = {"PATH": "/usr/bin:/bin", **({"PYTHONPYCACHEPREFIX": prefix} if prefix else {})}
    return subprocess.run([sys.executable, str(path)], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}),
                          capture_output=True, text=True, env=env)


class Stub(unittest.TestCase):
    def test_exit_codes_and_cache(self):
        with tempfile.TemporaryDirectory() as pfx:
            self.assertEqual(run(STUB, "git status", pfx).returncode, 0)
            blocked = run(STUB, "rm -rf $X", pfx)
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("Blocked destructive command", blocked.stderr)
            cached = [p.name for p in Path(pfx).rglob("*.pyc")]
            self.assertTrue(any(n.startswith("destructive_guard_core.") for n in cached), cached)
            self.assertFalse(any(n.startswith("destructive_guard.") for n in cached), "the stub itself is never cached")

    def test_importers_see_core_names_and_patches_apply(self):
        spec = importlib.util.spec_from_file_location("dg_stub_test", STUB)
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        for name in ("check", "main", "TIMEOUT", "_cmd"):
            self.assertTrue(hasattr(g, name), name)
        self.assertTrue(g.check("rm -rf $X"))
        g.check = lambda c: "patched"  # main -> _run looks `check` up in the stub's namespace, as before the split
        self.assertEqual(g._run.__globals__["check"]("x"), "patched")

    def test_missing_core_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            lone = Path(d) / "destructive_guard.py"
            shutil.copy(STUB, lone)
            r = run(lone, "git status")
            self.assertEqual(r.returncode, 2)
            self.assertIn("could not load", r.stderr)


if __name__ == "__main__":
    unittest.main()
