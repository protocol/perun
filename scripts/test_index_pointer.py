#!/usr/bin/env python3
"""The always-injected host rules point agents at .claude/skills/INDEX.md, and install.sh ships that file."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
from subagent_start_inject import HOST_RULES  # noqa: E402

POINTER = "Find any Perun skill or tool: read .claude/skills/INDEX.md first."


def install(repo, *flags):
    return subprocess.run(["bash", str(ROOT / "install.sh"), *flags, str(repo)], capture_output=True, text=True)


class Pointer(unittest.TestCase):
    def test_host_rules_carry_the_pointer_in_at_most_three_lines(self):
        self.assertIn(POINTER, HOST_RULES.splitlines())
        self.assertLessEqual(len(HOST_RULES.splitlines()), 3)
        self.assertLessEqual(len(POINTER.encode()) // 4, 25)  # the owner's budget for this line, in est. tokens

    def test_session_start_injects_it(self):
        with tempfile.TemporaryDirectory() as d:
            env = {k: v for k, v in os.environ.items() if not k.startswith(("PERUN_", "HOUSE_"))}
            env.update(CLAUDE_PROJECT_DIR=d, PERUN_SOURCE=d)
            r = subprocess.run([sys.executable, str(SC / "session_brief.py")], input=json.dumps({"cwd": d}),
                               capture_output=True, text=True, env=env)
        self.assertIn(POINTER, json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])

    def test_the_pointed_to_file_exists_in_the_source_tree(self):
        self.assertTrue((ROOT / ".claude/skills/INDEX.md").is_file())


class InstallShipsIndex(unittest.TestCase):
    def test_every_host_gets_the_index_and_uninstall_removes_it(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            r = install(repo)
            self.assertEqual(r.returncode, 0, r.stderr)
            src = (ROOT / ".claude/skills/INDEX.md").read_bytes()
            for host in (".claude", ".cursor", ".agents"):
                self.assertEqual((repo / host / "skills/INDEX.md").read_bytes(), src, host)
            u = subprocess.run([sys.executable, str(ROOT / "scripts/perun_uninstall.py"), str(repo), "--apply"], capture_output=True, text=True)
            self.assertEqual(u.returncode, 0, u.stderr)
            self.assertFalse((repo / ".claude/skills/INDEX.md").exists())

    def test_reinstall_refreshes_a_stale_index_and_minimal_ships_claude_only(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            install(repo, "--minimal")
            self.assertTrue((repo / ".claude/skills/INDEX.md").is_file())
            self.assertFalse((repo / ".cursor/skills/INDEX.md").exists())
            (repo / ".claude/skills/INDEX.md").write_text("stale\n")
            install(repo, "--minimal")
            self.assertEqual((repo / ".claude/skills/INDEX.md").read_bytes(), (ROOT / ".claude/skills/INDEX.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
