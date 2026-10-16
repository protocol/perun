#!/usr/bin/env python3
"""lane_guard.py seeds the gitignored .banlist.local.txt from the main checkout into a new lane worktree: plain
copy, never a symlink, never an overwrite, only when git ignores the path, only after an OK result."""
import contextlib
import io
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"))
import lane_guard  # noqa: E402
import lane_liveness  # noqa: E402

B = ".banlist.local.txt"
PRIVATE = "Acme Capital\nJane Smith\n"


def git(cwd, *a):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + os.devnull, *a],
                   check=True, capture_output=True)


class Seed(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.addCleanup(self._d.cleanup)
        self.tmp = Path(os.path.realpath(self._d.name))
        self.main, self.wt = self.tmp / "main", self.tmp / "wt"
        self.main.mkdir()
        git(self.main, "init", "-q", "-b", "main")
        (self.main / ".gitignore").write_text(B + "\n")
        git(self.main, "add", ".gitignore")
        git(self.main, "commit", "-q", "-m", "seed")
        git(self.main, "worktree", "add", "-q", "-b", "lane-a", str(self.wt))
        (self.main / B).write_text(PRIVATE)
        os.chmod(self.main / B, 0o600)
        saved = lane_liveness.foreign_cwd_pids
        lane_liveness.foreign_cwd_pids = lambda root: (set(), "stub")  # occupancy is not under test
        self.addCleanup(setattr, lane_liveness, "foreign_cwd_pids", saved)
        self.addCleanup(os.chdir, os.getcwd())

    def run_guard(self, cwd=None, branch="lane-a"):
        os.chdir(cwd or self.wt)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = lane_guard.main(["--expect-branch", branch])
        return rc, out.getvalue().strip()

    def test_copies_plain_file_when_missing(self):
        rc, line = self.run_guard()
        self.assertEqual(rc, 0, line)
        self.assertTrue(line.startswith("LANE_GUARD OK:") and "\n" not in line)
        self.assertIn(f"copied {B} from the main checkout", line)
        dst = self.wt / B
        self.assertFalse(dst.is_symlink())
        self.assertEqual(dst.read_text(), PRIVATE)
        self.assertEqual(stat.S_IMODE(dst.stat().st_mode), 0o600)
        self.assertEqual((self.main / B).read_text(), PRIVATE)  # source untouched

    def test_never_overwrites_existing_file(self):
        (self.wt / B).write_text("mine\n")
        rc, line = self.run_guard()
        self.assertEqual(rc, 0)
        self.assertNotIn("copied", line)
        self.assertEqual((self.wt / B).read_text(), "mine\n")

    def test_never_follows_or_replaces_a_symlink(self):
        os.symlink(str(self.tmp / "nowhere"), self.wt / B)  # dangling
        rc, line = self.run_guard()
        self.assertEqual(rc, 0)
        self.assertNotIn("copied", line)
        self.assertTrue((self.wt / B).is_symlink())
        self.assertFalse((self.tmp / "nowhere").exists())

    def test_second_run_is_a_no_op(self):
        self.run_guard()
        (self.wt / B).write_text("edited in the lane\n")
        rc, line = self.run_guard()
        self.assertNotIn("copied", line)
        self.assertEqual((self.wt / B).read_text(), "edited in the lane\n")

    def test_nothing_to_copy_when_main_has_none(self):
        (self.main / B).write_text("")
        os.rename(self.main / B, self.tmp / "elsewhere")
        rc, line = self.run_guard()
        self.assertEqual(rc, 0)
        self.assertFalse((self.wt / B).exists())

    def test_skipped_when_git_does_not_ignore_the_path(self):
        (self.main / ".gitignore").write_text("")
        git(self.main, "commit", "-q", "-am", "stop ignoring")
        git(self.wt, "merge", "-q", "main")
        rc, line = self.run_guard()
        self.assertEqual(rc, 0)
        self.assertNotIn("copied", line)
        self.assertFalse((self.wt / B).exists())  # git add -A would have staged a private file

    def test_refused_guard_copies_nothing(self):
        rc, line = self.run_guard(branch="other-lane")
        self.assertEqual(rc, 1)
        self.assertIn("REFUSE", line)
        self.assertFalse((self.wt / B).exists())

    def test_main_checkout_is_refused_and_untouched(self):
        rc, line = self.run_guard(cwd=self.main)
        self.assertEqual(rc, 1)
        self.assertEqual((self.main / B).read_text(), PRIVATE)


if __name__ == "__main__":
    unittest.main()
