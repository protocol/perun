#!/usr/bin/env python3
"""Tests for the updater's stale-lock, installed-over-committed and repeated-skip handling (perun_auto_update.py)."""
import hashlib, json, os, sys, tempfile, time, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_auto_update import au, sh, fake_remote, fake_installed  # noqa: E402

COMMIT = ("git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm")
SKILL = ".claude/skills/deep-code-review/SKILL.md"
NEW = b"name: deep-code-review\nnew\n"


class StaleLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["XDG_CACHE_HOME"] = str(self.tmp / "cache")
        os.environ.pop("PERUN_POLICY", None)
        self.proj = fake_installed(self.tmp, fake_remote(self.tmp))

    def marker(self):
        return json.loads((self.proj / ".claude/.perun-install.json").read_text())

    def log(self):
        f = au.cache() / "auto-update.log"
        return f.read_text() if f.is_file() else ""

    def linked_lock(self, age):
        d = self.proj / ".git/worktrees/lane1"
        d.mkdir(parents=True)
        (d / "MERGE_HEAD").write_text("x\n")
        os.utime(d / "MERGE_HEAD", (time.time() - age,) * 2)
        return d

    def test_stale_linked_lock_is_ignored_and_logged_fresh_still_blocks(self):
        d = self.linked_lock(2 * 86400)
        self.assertEqual(au.blocker(self.proj, self.marker()), "")
        self.assertIn(f"ignoring stale MERGE_HEAD in {d}", self.log())
        os.utime(d / "MERGE_HEAD", None)
        self.assertIn("MERGE_HEAD present in", au.blocker(self.proj, self.marker()))

    def test_stale_lock_in_own_git_dir_still_blocks(self):
        (self.proj / ".git/MERGE_HEAD").write_text("x\n")
        os.utime(self.proj / ".git/MERGE_HEAD", (time.time() - 5 * 86400,) * 2)
        self.assertIn("MERGE_HEAD present in", au.blocker(self.proj, self.marker()))

    def test_old_rebase_dir_with_a_fresh_child_still_blocks(self):
        d = self.proj / ".git/worktrees/lane1/rebase-merge"
        d.mkdir(parents=True)
        (d / "done").write_text("x\n")
        os.utime(d, (time.time() - 2 * 86400,) * 2)
        self.assertIn("rebase-merge present in", au.blocker(self.proj, self.marker()))
        for q in (d / "done", d):
            os.utime(q, (time.time() - 2 * 86400,) * 2)
        self.assertEqual(au.blocker(self.proj, self.marker()), "")

    def test_subdirectory_target_installed_over_older_commit_is_not_dirty(self):
        repo = self.tmp / "mono repo"
        repo.mkdir()
        sh("git", "init", "-q", cwd=repo)
        sub = repo / "app one"
        os.rename(self.proj, sub)
        sh("git", "init", "-q", cwd=repo)
        import shutil
        shutil.move(str(sub / ".git"), str(self.tmp / "old.git"))
        self.proj = sub
        self.assertEqual(au.blocker(sub, self.install_over_old_commit()), "")

    def install_over_old_commit(self):
        sh("git", "add", "-A", cwd=self.proj)
        sh(*COMMIT, "old", cwd=self.proj)
        (self.proj / SKILL).write_bytes(NEW)
        m = self.marker()
        m["skills"][".claude/skills/deep-code-review"]["SKILL.md"] = hashlib.sha256(NEW).hexdigest()
        (self.proj / ".claude/.perun-install.json").write_text(json.dumps(m))
        return m

    def test_installed_over_older_commit_is_not_dirty(self):
        self.assertEqual(au.blocker(self.proj, self.install_over_old_commit()), "")

    def test_user_edit_and_settings_change_still_block(self):
        m = self.install_over_old_commit()
        (self.proj / SKILL).write_text("user edit\n")
        self.assertIn("dirty Perun-managed file", au.blocker(self.proj, m))
        (self.proj / SKILL).write_bytes(NEW)
        (self.proj / ".claude/settings.local.json").write_text("{}\n")
        sh("git", "add", "-f", ".claude/settings.local.json", cwd=self.proj)
        sh(*COMMIT, "s", cwd=self.proj)
        (self.proj / ".claude/settings.local.json").write_text('{"a": 1}\n')
        self.assertIn("uncommitted changes: .claude/settings.local.json", au.blocker(self.proj, m))

    def test_three_same_reason_skips_warn_and_a_clear_run_resets(self):
        (self.proj / ".git/MERGE_HEAD").write_text("x\n")
        for _ in range(2):
            au.run(self.proj)
        self.assertIsNone(au.behind_warn(self.proj))
        au.run(self.proj)
        w = au.behind_warn(self.proj)
        self.assertTrue(w.startswith("WARN:") and "skipped 3 runs in a row: MERGE_HEAD present" in w, w)
        (self.proj / ".git/MERGE_HEAD").unlink()
        au.run(self.proj)
        self.assertIsNone(au.behind_warn(self.proj))


if __name__ == "__main__":
    unittest.main()
