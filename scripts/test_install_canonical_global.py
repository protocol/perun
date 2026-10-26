#!/usr/bin/env python3
"""Tests: canonical skill copy + host symlinks, drift row for copy fallback, stale-global command, non-git/global target."""
import os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / ".claude/skills/agentic-delivery/scripts"))
import perun_doctor, perun_auto_update, sandbox_probe  # noqa: E402

SKILL = "deep-code-review"


def install(repo, env=None):
    return subprocess.run(["bash", str(ROOT / "install.sh"), str(repo)], capture_output=True, text=True, env={**os.environ, **(env or {})})


def rows(repo, home):
    with mock.patch.dict(os.environ, {"DCR_NO_PROBE": "1"}):
        return {c: (s, d) for s, c, d in perun_doctor.check(Path(repo), Path(home))}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo, self.home = self.tmp / "r", self.tmp / "h"
        self.repo.mkdir(); self.home.mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, True)


class CanonicalCopy(Base):
    def test_hosts_symlink_to_claude_and_rerun_is_idempotent(self):
        p = install(self.repo)
        self.assertEqual(p.returncode, 0, p.stderr)
        for host in (".cursor", ".agents"):
            d = self.repo / host / "skills" / SKILL
            self.assertTrue(d.is_symlink())
            self.assertEqual(os.readlink(d), f"../../.claude/skills/{SKILL}")
            self.assertTrue((d / "SKILL.md").is_file())
        self.assertEqual(install(self.repo).returncode, 0)
        for host in (".cursor", ".agents"):
            self.assertTrue((self.repo / host / "skills" / SKILL).is_symlink())
            self.assertEqual(list((self.repo / host / "skill-backups").glob("*")) if (self.repo / host / "skill-backups").is_dir() else [], [])
        self.assertEqual(rows(self.repo, self.home)["drifted copies"][0], "OK")

    def test_copy_fallback_and_doctor_reports_drift(self):
        self.assertEqual(install(self.repo, {"DCR_COPY_HOSTS": "1"}).returncode, 0)
        d = self.repo / ".agents/skills" / SKILL
        self.assertFalse(d.is_symlink())
        self.assertEqual(rows(self.repo, self.home)["drifted copies"][0], "OK")
        (d / "SKILL.md").write_text("tampered\n")
        s, detail = rows(self.repo, self.home)["drifted copies"]
        self.assertEqual(s, "WARN")
        self.assertIn("differs from .claude copy", detail)

    def test_copy_mode_over_existing_link_leaves_no_backup(self):
        self.assertEqual(install(self.repo).returncode, 0)
        for _ in range(2):
            self.assertEqual(install(self.repo, {"DCR_COPY_HOSTS": "1"}).returncode, 0)
        d = self.repo / ".cursor/skills" / SKILL
        self.assertFalse(d.is_symlink())
        self.assertEqual(sorted(p.name for p in (self.repo / ".cursor/skill-backups").glob("*")) if (self.repo / ".cursor/skill-backups").is_dir() else [], [])

    def test_doctor_flags_dangling_host_symlink(self):
        self.assertEqual(install(self.repo).returncode, 0)
        shutil.rmtree(self.repo / ".claude/skills" / SKILL)
        s, d = rows(self.repo, self.home)["drifted copies"]
        self.assertEqual(s, "WARN")
        self.assertIn("dangling symlink", d)

    def test_uninstall_removes_host_symlinks(self):
        self.assertEqual(install(self.repo).returncode, 0)
        p = subprocess.run([sys.executable, str(ROOT / "scripts/perun_uninstall.py"), "--apply", str(self.repo)], capture_output=True, text=True)
        self.assertFalse((self.repo / ".cursor/skills" / SKILL).is_symlink(), p.stdout + p.stderr)


class GlobalTarget(Base):
    def test_stale_global_prints_one_copy_paste_command(self):
        v = self.home / ".claude/skills" / SKILL / "VERSION"
        v.parent.mkdir(parents=True)
        v.write_text("0.0.1\n")
        s, d = rows(self.repo, self.home)["global copy"]
        self.assertEqual(s, "WARN")
        self.assertIn(f"bash {ROOT}/scripts/update-installed.sh {self.home}", d)
        self.assertEqual(d.count("update-installed.sh"), 1)

    def test_non_git_or_global_target_skips_git_probe(self):
        def boom():
            raise RuntimeError
        item = ("git", boom, "git cannot run in this repo", "fix")
        env = {k: v for k, v in os.environ.items() if k != "DCR_NO_PROBE"}
        names = lambda a, b: {c: s for s, c, _ in perun_doctor.check(a, b)}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(sandbox_probe, "checks", return_value=[item]):
            self.assertNotIn("sandbox git", names(self.repo, self.home))  # tmp dir is not a git repo
            subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
            self.assertEqual(names(self.repo, self.home)["sandbox git"], "WARN")  # a real repo is still probed
            self.assertNotIn("sandbox git", names(self.repo, self.repo))  # target is the global home

    def test_dir_nested_in_a_parent_repo_counts_as_non_git(self):
        subprocess.run(["git", "init", "-q", str(self.tmp)], check=True)  # self.repo and self.home are subdirs of this repo
        def boom():
            raise RuntimeError
        env = {k: v for k, v in os.environ.items() if k != "DCR_NO_PROBE"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(sandbox_probe, "checks", return_value=[("git", boom, "c", "f")]):
            self.assertNotIn("sandbox git", {c for _, c, _ in perun_doctor.check(self.repo, self.home)})
        (self.home / ".claude").mkdir()
        (self.home / ".claude/.perun-install.json").write_text('{"version": "1.0.0"}')
        v = self.home / perun_auto_update.VER
        v.parent.mkdir(parents=True)
        v.write_text("1.0.0\n")
        self.assertEqual(perun_auto_update.update_pr(self.home), "pr skip: target is not a git repo (global install)")

    def test_updater_skips_pr_for_non_git_target(self):
        (self.home / ".claude").mkdir()
        (self.home / ".claude/.perun-install.json").write_text('{"version": "1.0.0"}')
        v = self.home / perun_auto_update.VER
        v.parent.mkdir(parents=True)
        v.write_text("1.0.0\n")
        self.assertEqual(perun_auto_update.update_pr(self.home), "pr skip: target is not a git repo (global install)")


if __name__ == "__main__":
    unittest.main()
