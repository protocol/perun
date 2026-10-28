#!/usr/bin/env python3
"""Lane worktree root + SubagentStop reaper + doctor rows. Throwaway repos under a temp dir only; no network; the reaper
is never pointed at a real host path."""
import contextlib, io, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / ".claude/skills/agentic-delivery/scripts"))
sys.path.insert(0, str(HERE))
import handback_cap as hc  # noqa: E402
import perun_doctor  # noqa: E402
LW = HERE.parent / ".claude/skills/agentic-delivery/scripts/lane_worktree.sh"


def git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=T", "-c", "user.email=t@example.com", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout


class Base(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.t = os.path.realpath(t.name)
        self.repo, self.root = self.t + "/proj", self.t + "/wt"
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main"); git(self.repo, "commit", "-q", "--allow-empty", "-m", "i")
        git(self.t, "clone", "-q", "--bare", self.repo, self.t + "/remote.git")
        git(self.repo, "remote", "add", "origin", self.t + "/remote.git"); git(self.repo, "fetch", "-q", "origin")
        env = mock.patch.dict(os.environ, {"PERUN_WT_ROOT": self.root, "PERUN_AGENT_ID": ""}); env.start(); self.addCleanup(env.stop)

    def mk(self, name, cwd=None, push=True, agent="", base="origin/main"):
        r = subprocess.run(["bash", str(LW), name, base], cwd=cwd or self.repo, capture_output=True, text=True,
                           env={**os.environ, "PERUN_AGENT_ID": agent})
        self.assertEqual(r.returncode, 0, r.stderr)
        p = r.stdout.strip()
        if push:
            git(p, "push", "-q", "-u", "origin", f"lane/{name}")
        return p

    def reap(self, p, agent="A", sure=True):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            return hc._reap_own_worktree(p, agent, sure), err.getvalue()


class Reap(Base):
    def test_script_puts_tree_outside_repo_and_rejects_bad_names(self):
        p = self.mk("a")
        self.assertEqual(p, self.root + "/proj/a")
        for bad in ("../x", "a/b", "..", "-x"):
            r = subprocess.run(["bash", str(LW), bad], cwd=self.repo, capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, bad)
        r = subprocess.run(["bash", str(LW), "z"], cwd=self.repo, capture_output=True, text=True, env={**os.environ, "PERUN_WT_ROOT": "/"})
        self.assertEqual(r.returncode, 2)

    def test_clean_pushed_removed_branch_deleted_others_kept(self):
        a, b = self.mk("a"), self.mk("b")
        got, _ = self.reap(a)
        self.assertEqual(got, a); self.assertFalse(os.path.exists(a)); self.assertTrue(os.path.isdir(b))
        self.assertNotIn("lane/a", git(self.repo, "branch", "--list", "lane/a")); self.assertTrue(os.path.isdir(self.repo))

    def test_dirty_kept_and_reported(self):
        a = self.mk("a"); Path(a, "x.txt").write_text("x")
        got, err = self.reap(a)
        self.assertIsNone(got); self.assertTrue(os.path.isdir(a)); self.assertIn("left in place", err)

    def test_ignored_files_kept(self):
        a = self.mk("a"); Path(a, ".git").exists()
        Path(self.repo, ".gitignore").write_text(".env\n"); git(self.repo, "add", "-A"); git(self.repo, "commit", "-q", "-m", "ig")
        git(a, "merge", "-q", "--ff-only", "main"); git(a, "push", "-q"); Path(a, ".env").write_text("secret")
        got, err = self.reap(a)
        self.assertIsNone(got); self.assertIn("ignored", err); self.assertTrue(os.path.exists(a + "/.env"))

    def test_unpushed_commit_or_no_upstream_kept(self):
        a = self.mk("a"); git(a, "commit", "-q", "--allow-empty", "-m", "new")
        self.assertIsNone(self.reap(a)[0])
        b = self.mk("b", push=False); git(b, "branch", "--unset-upstream")
        self.assertIsNone(self.reap(b)[0]); self.assertTrue(os.path.isdir(a) and os.path.isdir(b))

    def test_shared_cwd_other_agent_kept(self):
        a = self.mk("a", agent="parent")
        got, err = self.reap(a, agent="sibling")
        self.assertIsNone(got); self.assertIn("another agent", err); self.assertTrue(os.path.isdir(a))
        self.assertEqual(self.reap(a, agent="parent")[0], a)

    def test_unmarked_trees_and_main_kept(self):
        for d in (self.root + "/proj/hand", self.repo + "/.claude/worktrees/h", self.t + "/other"):
            git(self.repo, "worktree", "add", "-q", "-b", "b" + str(abs(hash(d))), d, "origin/main")
            self.assertIsNone(self.reap(d)[0]); self.assertTrue(os.path.isdir(d))
        self.assertIsNone(self.reap(self.repo)[0])

    def test_blind_scan_reports_only(self):
        a = self.mk("a")
        got, err = self.reap(a, sure=False)
        self.assertIsNone(got); self.assertIn("could not check", err); self.assertTrue(os.path.isdir(a))

    def test_unsafe_roots_refused(self):
        a = self.mk("a")
        for bad in ("/", os.path.expanduser("~"), self.t):  # root, HOME, an ancestor of the repo
            with mock.patch.dict(os.environ, {"PERUN_WT_ROOT": bad}):
                self.assertIsNone(self.reap(a)[0]); self.assertTrue(os.path.isdir(a))

    def test_symlinked_root_still_works_and_off_switch(self):
        os.makedirs(self.root); os.symlink(self.root, self.t + "/link")
        with mock.patch.dict(os.environ, {"PERUN_WT_ROOT": self.t + "/link"}):
            a = self.mk("a")
            with mock.patch.dict(os.environ, {"PERUN_REAP_WORKTREE": "0"}):
                self.assertIsNone(self.reap(a)[0])
            self.assertEqual(self.reap(a)[0], a)

    def test_bare_repo(self):
        bare = self.t + "/bare.git"; git(self.t, "clone", "-q", "--bare", self.repo, bare)
        git(bare, "config", "remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*")  # a bare clone has no tracking refs by default
        a = self.mk("a", cwd=bare, base="main")
        self.assertEqual(self.reap(a)[0], a); self.assertFalse(os.path.exists(a))

    def test_stop_hook_reaps_and_released_block_reports(self):
        a = self.mk("a", agent="L1")
        with tempfile.TemporaryDirectory() as st, mock.patch.object(hc, "STATE_DIR", st), mock.patch.dict(os.environ, {"HANDBACK_AUDIT_LEDGER": "off"}), \
                mock.patch.object(hc, "_push_running", lambda c: False), mock.patch.object(hc, "_bg_running", lambda c: None):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(hc.check({"agent_id": "L1", "cwd": a, "last_assistant_message": "status=VERIFIED"}), 0)
            self.assertTrue(os.path.isdir(a)); self.assertIn("could not check", err.getvalue())  # bg None: kept, reported
            with mock.patch.object(hc, "_bg_running", lambda c: []), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(hc.check({"agent_id": "L1", "cwd": a, "last_assistant_message": "status=VERIFIED"}), 0)
        self.assertFalse(os.path.exists(a))


class Doctor(Base):
    def test_counts_in_repo_and_out_of_tree_without_main(self):
        git(self.repo, "worktree", "add", "-q", "-b", "i", self.repo + "/wt-in", "origin/main")
        out = self.mk("out")
        inside, outside = perun_doctor.lane_worktrees(self.repo)
        self.assertEqual(inside, [self.repo + "/wt-in"]); self.assertEqual(outside, [out])
        kb, full = perun_doctor._du(inside, 30)
        self.assertTrue(full and kb > 0)
        self.assertEqual(perun_doctor._du(inside, 0), (None, False))

    def test_bad_threshold_env_does_not_crash_check(self):
        with mock.patch.dict(os.environ, {"PERUN_WT_MAX": "x", "DCR_NO_PROBE": "1"}):
            rows = perun_doctor.check(Path(self.repo), Path(self.t))
        self.assertTrue(rows)


if __name__ == "__main__":
    unittest.main()
