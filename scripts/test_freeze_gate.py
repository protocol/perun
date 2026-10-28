"""freeze_gate.py: freeze off allows all; on allows only deletions or a Red-Trunk-Fix trailer."""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/freeze_gate.py"


def repo(change, msg="work"):
    d = tempfile.mkdtemp()
    g = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)  # noqa: E731
    g("init", "-b", "main")
    g("config", "user.email", "a@example.com")
    g("config", "user.name", "A")
    pathlib.Path(d, "old.txt").write_text("x\n")
    g("add", ".")
    g("commit", "-m", "base")
    g("checkout", "-b", "feat")
    change(d)
    g("add", "-A")
    g("commit", "--allow-empty", "-m", msg)
    return d


def gate(d, frozen=True):
    if frozen:
        pathlib.Path(d, ".perun-freeze").write_text("release stabilisation\n")
    return subprocess.run([sys.executable, str(SCRIPT), "main", "feat"], cwd=d, capture_output=True, text=True,
                          env={k: v for k, v in os.environ.items() if k != "PERUN_FREEZE"})


add = lambda d: pathlib.Path(d, "new.txt").write_text("y\n")  # noqa: E731
rm = lambda d: os.remove(f"{d}/old.txt")  # noqa: E731


class T(unittest.TestCase):
    def test_no_freeze_allows_anything(self):
        self.assertEqual(gate(repo(add), frozen=False).returncode, 0)

    def test_freeze_blocks_addition_with_reason(self):
        r = gate(repo(add))
        self.assertEqual(r.returncode, 1)
        self.assertIn("FROZEN: release stabilisation", r.stdout)

    def test_freeze_allows_pure_deletion(self):
        self.assertEqual(gate(repo(rm)).returncode, 0)

    def test_freeze_blocks_mixed_delete_and_add(self):
        self.assertEqual(gate(repo(lambda d: (rm(d), add(d)))).returncode, 1)

    def test_freeze_allows_red_trunk_fix_trailer(self):
        self.assertEqual(gate(repo(add, "fix\n\nRed-Trunk-Fix: unit suite red")).returncode, 0)
        self.assertEqual(gate(repo(add, "fix\n\nRed-Trunk-Fix:")).returncode, 1)

    def test_bad_args_exit_2(self):
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT)], capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
