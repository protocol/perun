"""wired_check.py: a new script named only on an orphan/unused allowlist is merged-not-wired, not wired."""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/wired_check.py"


def wired(files):
    d = tempfile.mkdtemp()
    g = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)  # noqa: E731
    g("init", "-b", "main")
    g("config", "user.email", "a@example.com")
    g("config", "user.name", "A")
    g("commit", "--allow-empty", "-m", "base")
    g("checkout", "-b", "feat")
    for p, text in files.items():
        os.makedirs(os.path.dirname(f"{d}/{p}"), exist_ok=True)
        pathlib.Path(f"{d}/{p}").write_text(text)
    g("add", ".")
    g("commit", "-m", "add")
    return subprocess.run([sys.executable, str(SCRIPT), "main", "feat", "--root", d], capture_output=True, text=True).stdout


class T(unittest.TestCase):
    def test_allowlist_line_does_not_wire(self):
        out = wired({"scripts/tool.sh": "echo hi\n", "scripts/check.sh": 'ORPHAN_ALLOW="tool.sh"\n'})
        self.assertIn("scripts/tool.sh has no caller", out)
        self.assertIn("merged-not-wired", out)

    def test_allowlist_named_file_does_not_wire(self):
        out = wired({"scripts/tool.sh": "echo hi\n", "scripts/unused-allowlist.json": '["tool.sh"]\n'})
        self.assertIn("merged-not-wired", out)

    def test_real_caller_still_wires_even_with_an_allowlist_entry(self):
        out = wired({"scripts/tool.sh": "echo hi\n", "scripts/run.sh": "bash scripts/tool.sh\n",
                     "scripts/unused-allowlist.json": '["tool.sh"]\n'})
        self.assertNotIn("scripts/tool.sh has no caller", out)  # (run.sh, the caller, is itself new and unwired)

    def test_plain_unwired_has_no_allowlist_note(self):
        out = wired({"scripts/tool.sh": "echo hi\n"})
        self.assertIn("has no caller", out)
        self.assertNotIn("merged-not-wired", out)


if __name__ == "__main__":
    unittest.main()
