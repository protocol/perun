#!/usr/bin/env python3
"""Tests: invisible_chars.py skips a dangling symlink, a folder path (a submodule folder), a FIFO and a missing path before the open, with no row; a
regular file it cannot read gives one `unreadable: <reason>` not-checked row (the committed_personal_data.py wording); readable files and a
file name with a hidden character are still scanned. Hermetic temp dirs; skipped when run as root (chmod does not block root)."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / ".claude" / "skills" / "deep-code-review" / "scripts" / "invisible_chars.py"


def run(cwd, *paths):
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=cwd, input="\n".join(paths) + "\n", capture_output=True, text=True, timeout=60).stdout.splitlines()


class Unreadable(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
        self.addCleanup(subprocess.run, ["rm", "-rf", self.d])

    def test_dangling_symlink_folder_and_missing_path_give_no_row(self):
        os.symlink("gone.txt", os.path.join(self.d, "dangling.txt"))
        os.mkdir(os.path.join(self.d, "sub"))
        os.mkfifo(os.path.join(self.d, "pipe.txt"))  # skipped before the open, so it cannot hang the scan
        self.assertEqual(run(self.d, "dangling.txt", "sub", "missing.txt", "pipe.txt"), [])

    @unittest.skipIf(os.geteuid() == 0, "root reads mode-000 files")
    def test_failed_read_of_a_regular_file_gives_one_unreadable_row(self):
        p = os.path.join(self.d, "locked.txt")
        Path(p).write_text("Acme\n")
        os.chmod(p, 0)
        self.addCleanup(os.chmod, p, 0o600)
        self.assertEqual(run(self.d, "locked.txt"), ["locked.txt\t0\tnot-checked\tunreadable: Permission denied"])

    def test_readable_file_with_a_hidden_character_is_still_reported(self):
        Path(self.d, "a.txt").write_text("Acme" + chr(0x202E) + "\n")
        out = run(self.d, "a.txt")
        self.assertEqual(len(out), 1)
        self.assertIn("\thidden-unicode\t", out[0])


if __name__ == "__main__":
    unittest.main()
