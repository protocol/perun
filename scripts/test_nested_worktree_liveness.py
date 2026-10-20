#!/usr/bin/env python3
"""A lane's process scan counts only its own git worktree: a test running in a worktree nested under the lane's
checkout is another lane's, while a submodule's files still belong to the checkout that contains it."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"))
import lane_liveness as ll  # noqa: E402


class NestedWorktree(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.main = os.path.realpath(self.tmp.name)
        self.wt = os.path.join(self.main, "wt-x")  # linked worktree: `.git` is a file
        self.sm = os.path.join(self.main, "vendor", "sm")  # submodule: `.git` file points into .../modules/
        os.makedirs(os.path.join(self.main, ".git"))
        os.makedirs(self.wt)
        os.makedirs(self.sm)
        Path(self.wt, ".git").write_text("gitdir: /r/.git/worktrees/wt-x\n")
        Path(self.sm, ".git").write_text("gitdir: ../../.git/modules/sm\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_nested_worktree_is_not_the_outer_tree(self):
        self.assertFalse(ll.same_tree(self.wt, self.main))
        self.assertTrue(ll.same_tree(self.wt, self.wt))

    def test_subdir_and_submodule_are_the_same_tree(self):
        self.assertTrue(ll.same_tree(os.path.join(self.main, "src"), self.main))
        self.assertTrue(ll.same_tree(self.sm, self.main))

    def test_no_git_tree_falls_back_to_containment(self):
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            self.assertTrue(ll.same_tree(os.path.join(d, "a"), d))
            self.assertFalse(ll.same_tree(os.path.dirname(d), d))

    def test_cwd_pids_skips_a_test_running_in_a_nested_worktree(self):
        out = f"p{os.getpid()}\nn{self.main}\np901\nn{self.wt}\np902\nn{self.sm}\n"
        proc = mock.Mock(returncode=0, stdout=out)
        with mock.patch.object(ll.subprocess, "run", return_value=proc):
            pids, _ = ll._cwd_pids_via_lsof(self.main)
        self.assertEqual(pids, {os.getpid(), 902})

    def test_lane_start_occupancy_ignores_a_nested_worktree_but_not_a_subdir(self):
        # lane_guard's lane-start check: a process in another lane's nested worktree is not in this tree's way.
        sub = os.path.join(self.main, "src")
        os.makedirs(sub)
        out = f"p{os.getpid()}\nn{self.main}\np901\nn{self.wt}\np902\nn{sub}\n"
        proc = mock.Mock(returncode=0, stdout=out)
        with mock.patch.object(ll.subprocess, "run", return_value=proc), \
                mock.patch("shutil.which", return_value="/usr/bin/lsof"), \
                mock.patch.object(ll, "process_ancestors", return_value=set()):
            pids, _ = ll.foreign_cwd_pids(self.main)
        self.assertEqual(pids, {902})


if __name__ == "__main__":
    unittest.main()
