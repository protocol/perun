#!/usr/bin/env python3
"""Install UX regressions (temp repos only): doctor exit on a fresh install, no growing backups, complete and safe uninstall.

Principle under test: nothing is deleted unless it is provably an unmodified, shipped Perun copy inside the target."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import perun_doctor, perun_marker, perun_uninstall  # noqa: E402

HAS_JQ = shutil.which("jq") is not None
os.environ["DCR_NO_PROBE"] = "1"


def install(repo, *flags):
    p = subprocess.run(["bash", str(ROOT / "install.sh"), *flags, str(repo)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p


def uninstall(repo, *a):
    return subprocess.run([sys.executable, str(ROOT / "scripts/perun_uninstall.py"), str(repo), *a], capture_output=True, text=True)


def tree(repo):
    return sorted(str(p.relative_to(repo)) for p in Path(repo).rglob("*"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo, self.home = self.tmp / "r", self.tmp / "h"
        self.repo.mkdir(); self.home.mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, True)


class DoctorFreshInstall(Base):
    def test_fresh_default_install_exits_zero(self):
        install(self.repo)
        self.assertEqual(perun_doctor.main([str(self.repo), "--home", str(self.home)]), 0)
        r = {c: s for s, c, _ in perun_doctor.check(self.repo, self.home)}
        self.assertEqual((r["janitor/scheduler"], r["policy file"]), ("INFO", "INFO"))  # optional add-ons: shown, never failing

    def test_real_problem_still_fails(self):
        install(self.repo)
        (self.repo / ".claude/skills/deep-code-review/VERSION").write_text("0.0.1\n")
        self.assertEqual(perun_doctor.main([str(self.repo), "--home", str(self.home)]), 1)


class BoundedBackups(Base):
    def backups(self, host=".claude"):
        d = self.repo / host / "skill-backups"
        return sorted(p.name for p in d.iterdir()) if d.is_dir() else []

    def test_unchanged_rerun_keeps_no_backup(self):
        install(self.repo)
        install(self.repo)
        install(self.repo)
        self.assertEqual([self.backups(h) for h in (".claude", ".cursor", ".agents")], [[], [], []])

    def test_changed_reruns_never_delete_a_backup(self):  # review repro 2: pruning used to destroy user edits
        orig = self.repo / ".claude/skills/deep-code-review"
        orig.mkdir(parents=True)
        (orig / "SKILL.md").write_text("mine\n")  # pre-Perun copy: no VERSION file
        install(self.repo, "--minimal")
        seen = {self.backups()[0]: "mine\n"}
        for i in range(3):
            (orig / "SKILL.md").write_text(f"my edit {i}\n")  # a changed copy each time, so each re-run has something to back up
            install(self.repo, "--minimal")
            seen[[b for b in self.backups() if b not in seen][0]] = f"my edit {i}\n"
        self.assertEqual(self.backups(), sorted(seen))  # all four are still there, none replaced
        for name, text in seen.items():
            self.assertEqual((self.repo / ".claude/skill-backups" / name / "SKILL.md").read_text(), text)

    def test_symlinked_backup_root_is_refused(self):  # review repro 1: a symlinked skill-backups dir must never be written through
        ext = self.tmp / "ext"
        (ext / "deep-code-review-20260101-000000").mkdir(parents=True)
        (ext / "deep-code-review-20260101-000000/keep.txt").write_text("user data\n")
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/skill-backups").symlink_to(ext)
        orig = self.repo / ".claude/skills/deep-code-review"
        orig.mkdir(parents=True)
        (orig / "SKILL.md").write_text("mine\n")
        p = subprocess.run(["bash", str(ROOT / "install.sh"), "--minimal", str(self.repo)], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("symlink", p.stderr)
        self.assertEqual((ext / "deep-code-review-20260101-000000/keep.txt").read_text(), "user data\n")
        self.assertEqual(sorted(x.name for x in ext.iterdir()), ["deep-code-review-20260101-000000"])  # nothing moved into it
        self.assertEqual((orig / "SKILL.md").read_text(), "mine\n")  # the user's skill was not moved or replaced

    def test_dedupe_never_follows_a_symlink(self):
        dest = self.tmp / "dest"
        (dest).mkdir()
        (dest / "SKILL.md").write_text("same\n")
        userdir = self.tmp / "userdir"
        userdir.mkdir()
        (userdir / "SKILL.md").write_text("same\n")  # identical content: still the user's directory
        root = self.tmp / "root"
        root.mkdir()
        (root / "foo-20260101-000000").symlink_to(userdir)
        out = perun_marker.drop_identical_backup(root, root / "foo-20260101-000000", dest)
        self.assertIn("kept", out)
        self.assertEqual((userdir / "SKILL.md").read_text(), "same\n")
        real = root / "bar-20260101-000000"
        real.mkdir()
        (real / "SKILL.md").write_text("same\n")
        (real / "link").symlink_to(userdir)  # a symlink inside the backup: not a plain shipped copy
        self.assertIn("kept", perun_marker.drop_identical_backup(root, real, dest))
        self.assertTrue(userdir.is_dir())

    def test_prune_ignores_foreign_dirs(self):
        install(self.repo, "--minimal")
        keep = self.repo / ".claude/skill-backups/deep-code-review-notes"
        keep.mkdir(parents=True)
        (keep / "VERSION").write_text("x\n")
        (self.repo / ".claude/skills/deep-code-review/SKILL.md").write_text("changed\n")
        install(self.repo, "--minimal")
        self.assertTrue(keep.is_dir())


@unittest.skipUnless(HAS_JQ, "jq needed to apply the operating layer")
class CompleteUninstall(Base):
    def run_cycle(self, *flags, pre=None):
        for rel, text in (pre or {}).items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text)
        before = tree(self.repo)
        install(self.repo, *flags)
        install(self.repo, *flags)  # re-run: marker must still cover everything
        p = uninstall(self.repo, "--apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        return before, p

    def test_default_install_leaves_nothing(self):
        before, _ = self.run_cycle()
        self.assertEqual(tree(self.repo), before)

    def test_full_install_leaves_nothing(self):
        before, _ = self.run_cycle("--full")
        self.assertEqual(tree(self.repo), before)

    def test_preexisting_files_survive_untouched(self):
        pre = {"AGENTS.md": "# Mine\n\nkeep me\n", ".claude/settings.local.json": json.dumps({"model": "opus", "sandbox": {"enabled": False}}), ".claude/skills/deep-code-review/SKILL.md": "mine\n"}
        before, _ = self.run_cycle("--full", pre=pre)
        self.assertEqual((self.repo / "AGENTS.md").read_text(), "# Mine\n\nkeep me\n")
        self.assertEqual(json.loads((self.repo / ".claude/settings.local.json").read_text()), {"model": "opus", "sandbox": {"enabled": False}})
        self.assertEqual((self.repo / ".claude/skills/deep-code-review/SKILL.md").read_text(), "mine\n")  # original restored
        self.assertEqual(tree(self.repo), before)  # no .bak, no skill-backups, no empty dirs

    def test_user_changed_files_are_kept_and_listed(self):
        install(self.repo, "--full")
        (self.repo / ".claude/house-defaults.md").write_text("edited\n")
        (self.repo / ".claude/commands/review.md").write_text("edited\n")
        p = uninstall(self.repo, "--apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((self.repo / ".claude/house-defaults.md").read_text(), "edited\n")
        self.assertTrue((self.repo / ".claude/commands/review.md").exists())

    def test_original_backup_kept_when_skill_not_restored(self):
        orig = self.repo / ".claude/skills/deep-code-review"
        orig.mkdir(parents=True)
        (orig / "SKILL.md").write_text("mine\n")
        install(self.repo, "--minimal")
        (orig / "my-notes.md").write_text("added\n")  # user file inside the skill dir: dir is not fully removed
        p = uninstall(self.repo, "--apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("kept: user content", p.stdout)
        kept = [b for b in (self.repo / ".claude/skill-backups").iterdir()]
        self.assertEqual((kept[0] / "SKILL.md").read_text(), "mine\n")

    def test_preinstall_copy_with_version_file_and_edited_backup_survive(self):  # review repro 3
        orig = self.repo / ".claude/skills/deep-code-review"
        orig.mkdir(parents=True)
        (orig / "SKILL.md").write_text("mine\n")
        (orig / "VERSION").write_text("9.9.9\n")  # looks like a Perun copy by name, but it is not a shipped one
        install(self.repo, "--minimal")
        (b,) = list((self.repo / ".claude/skill-backups").iterdir())
        (b / "SKILL.md").write_text("edited in the backup\n")
        p = uninstall(self.repo, "--apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((orig / "SKILL.md").read_text(), "edited in the backup\n")  # moved back, content untouched
        self.assertEqual((orig / "VERSION").read_text(), "9.9.9\n")

    def test_backup_with_a_non_shipped_file_is_kept_and_a_shipped_one_is_removed(self):
        install(self.repo, "--minimal")
        sk = self.repo / ".claude/skills/deep-code-review"
        bdir = self.repo / ".claude/skill-backups"
        bdir.mkdir()
        shipped_copy, user_copy = bdir / "deep-code-review-20260101-000000", bdir / "deep-code-review-20260102-000000"
        shutil.copytree(sk, shipped_copy)
        shutil.copytree(sk, user_copy)
        (user_copy / "notes.md").write_text("mine\n")
        mf = self.repo / perun_marker.MARKER
        m = json.loads(mf.read_text())
        m["backups"] = [f".claude/skill-backups/{shipped_copy.name}", f".claude/skill-backups/{user_copy.name}"]
        mf.write_text(json.dumps(m))
        p = uninstall(self.repo, "--apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(shipped_copy.exists())  # byte-identical shipped copy: removed
        self.assertEqual((user_copy / "notes.md").read_text(), "mine\n")  # extra user file: whole backup kept
        self.assertIn(f"{user_copy.name}: kept: user content", p.stdout.replace(".claude/skill-backups/", ""))

    def test_edited_perun_backup_is_kept_not_restored_as_preinstall(self):
        install(self.repo, "--minimal")
        (self.repo / ".claude/skills/deep-code-review/SKILL.md").write_text("my edit\n")
        install(self.repo, "--minimal")  # backs up the edited copy
        p = uninstall(self.repo, "--apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse((self.repo / ".claude/skills/deep-code-review").exists())  # nothing pre-existed: no skill restored
        (b,) = list((self.repo / ".claude/skill-backups").iterdir())
        self.assertEqual((b / "SKILL.md").read_text(), "my edit\n")
        self.assertIn("kept: user content", p.stdout)

    def test_marker_path_outside_repo_is_refused(self):
        install(self.repo, "--minimal")
        victim = self.tmp / "victim.txt"
        victim.write_text("precious\n")
        m = json.loads((self.repo / perun_marker.MARKER).read_text())
        m["files"]["../victim.txt"] = perun_marker.sha(victim)
        (self.repo / perun_marker.MARKER).write_text(json.dumps(m))
        p = uninstall(self.repo, "--apply")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("outside", p.stderr)
        self.assertEqual(victim.read_text(), "precious\n")
        self.assertTrue((self.repo / ".claude/skills/deep-code-review").exists())  # nothing else touched

    def test_symlinked_parent_is_refused(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "f.txt").write_text("precious\n")
        (self.repo / "link").symlink_to(outside)
        self.assertFalse(perun_uninstall.inside(self.repo, "link/f.txt"))
        self.assertFalse(perun_uninstall.inside(self.repo, "/etc/hosts"))
        self.assertFalse(perun_uninstall.inside(self.repo, "a/../b"))
        self.assertTrue(perun_uninstall.inside(self.repo, ".claude/x"))

    def _marker(self, **edit):
        mf = self.repo / perun_marker.MARKER
        m = json.loads(mf.read_text())
        m.update(edit)
        mf.write_text(json.dumps(m))

    def test_traversal_absolute_and_bad_shaped_marker_keys_abort(self):  # review repro 4
        install(self.repo, "--minimal")
        outer = self.tmp / "outer"
        (outer / "emptyvictim").mkdir(parents=True)
        good = (self.repo / perun_marker.MARKER).read_text()
        for bad in ({"skills": {"../outer": {}}}, {"skills": {".": {}}}, {"skills": {str(outer): {}}},
                    {"backups": ["../outer/emptyvictim"]}, {"files": {"/etc/hosts": "x"}}, {"files": {"a/../../outer/x": "x"}}):
            self._marker(**bad)
            p = uninstall(self.repo, "--apply")
            self.assertNotEqual(p.returncode, 0, bad)
            self.assertIn("outside", p.stderr)
            self.assertTrue((outer / "emptyvictim").is_dir())
            self.assertTrue((self.repo / ".claude/skills/deep-code-review").exists())  # nothing else touched
            (self.repo / perun_marker.MARKER).write_text(good)

    def test_symlinked_skill_dir_is_skipped_and_never_walked(self):
        install(self.repo, "--minimal")
        sk = self.repo / ".claude/skills/deep-code-review"
        ext = self.tmp / "ext"
        shutil.copytree(sk, ext)  # an exact shipped copy, outside the repo
        shutil.rmtree(sk)
        sk.symlink_to(ext)
        p = uninstall(self.repo, "--apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("symlink", p.stdout)
        self.assertTrue((ext / "SKILL.md").exists())
        self.assertTrue(sk.is_symlink())

    def test_symlinked_backup_dir_is_kept(self):
        install(self.repo, "--minimal")
        userdir = self.tmp / "userdir"
        userdir.mkdir()
        (userdir / "SKILL.md").write_text("user\n")
        (self.repo / ".claude/skill-backups").mkdir()
        link = self.repo / ".claude/skill-backups/deep-code-review-20260101-000000"
        link.symlink_to(userdir)
        self._marker(backups=[".claude/skill-backups/deep-code-review-20260101-000000"])
        p = uninstall(self.repo, "--apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual((userdir / "SKILL.md").read_text(), "user\n")
        self.assertTrue(link.is_symlink())
        self.assertIn("kept: user content", p.stdout)


class Hardening(Base):
    """Non-blocking edges from the re-review: forged marker paths, symlinked sweeps, pycache in the dedupe compare."""

    def _marker(self, **edit):
        mf = self.repo / perun_marker.MARKER
        m = json.loads(mf.read_text())
        m.update(edit)
        mf.write_text(json.dumps(m))

    def test_forged_files_and_agent_paths_are_rejected(self):  # (a)
        install(self.repo, "--minimal")
        app = self.repo / "src/app.py"
        app.parent.mkdir()
        app.write_text("print(1)\n")
        cfg = self.repo / ".git/config"
        cfg.parent.mkdir()
        cfg.write_text("[core]\n")
        for edit in ({"files": {"src/app.py": perun_marker.sha(app)}}, {"files": {".git/config": perun_marker.sha(cfg)}},
                     {"agent": {"path": "src/app.py", "sha": perun_marker.sha(app)}}, {"files": {"AGENTS.md": "x"}}):
            good = (self.repo / perun_marker.MARKER).read_text()
            self._marker(**edit)
            p = uninstall(self.repo, "--apply")
            self.assertNotEqual(p.returncode, 0, edit)
            self.assertEqual((app.read_text(), cfg.read_text()), ("print(1)\n", "[core]\n"))
            (self.repo / perun_marker.MARKER).write_text(good)

    def test_dot_and_dotdot_are_not_skill_or_backup_names(self):  # (a)
        for rel in (".claude/skills/.", ".claude/skills/..", "../skills/x", ".claude/skill-backups/..-20260101-000000", ".claude/skill-backups/.-20260101-000000"):
            self.assertFalse(perun_uninstall.SKILL_RE.match(rel) or perun_uninstall.BACKUP_RE.match(rel), rel)
        self.assertTrue(perun_uninstall.SKILL_RE.match(".claude/skills/deep-code-review"))
        self.assertTrue(perun_uninstall.BACKUP_RE.match(".claude/skill-backups/deep-code-review-20260101-000000-2"))

    def test_marker_without_shipped_hashes_keeps_every_file(self):  # (a): no legacy fallback to the marker's own hashes
        install(self.repo, "--minimal")
        m = json.loads((self.repo / perun_marker.MARKER).read_text())
        del m["shipped"]
        (self.repo / perun_marker.MARKER).write_text(json.dumps(m))
        before = tree(self.repo / ".claude/skills")
        p = uninstall(self.repo, "--apply")
        self.assertEqual(p.returncode, 0, p.stderr)
        # skills/INDEX.md is a recorded loose file (hash-checked like a command), not a skill file
        self.assertEqual([x for x in tree(self.repo / ".claude/skills") if x != "INDEX.md"], [x for x in before if x != "INDEX.md"])
        self.assertIn("KEEP", p.stdout)

    def test_sweeps_never_follow_a_symlink(self):  # (b)
        ext = self.tmp / "ext"
        (ext / "skills/x").mkdir(parents=True)
        (self.repo / ".claude").symlink_to(ext)  # a symlinked parent
        perun_uninstall.prune_empty(self.repo, [".claude/skills/x"])
        self.assertTrue((ext / "skills/x").is_dir())
        ext2 = self.tmp / "ext2"
        (ext2 / "sub").mkdir(parents=True)
        (self.repo / "top").symlink_to(ext2)  # a symlinked top
        perun_uninstall.sweep(self.repo, "top")
        self.assertTrue((ext2 / "sub").is_dir())
        real = self.repo / "real"
        (real / "empty").mkdir(parents=True)
        (real / "link").symlink_to(ext2)  # a symlink inside a real top: its target is not descended
        perun_uninstall.sweep(self.repo, "real")
        self.assertTrue((ext2 / "sub").is_dir())
        self.assertFalse((real / "empty").exists())

    def test_dedupe_compares_pycache_files_too(self):  # (c)
        dest, new = self.tmp / "dest", self.tmp / "root/foo-20260101-000000"
        for d in (dest, new):
            (d / "__pycache__").mkdir(parents=True)
            (d / "SKILL.md").write_text("same\n")
            (d / "__pycache__/data.txt").write_text("same\n")
        (new / "__pycache__/data.txt").write_text("different\n")  # a non-.pyc file under __pycache__
        self.assertIn("kept", perun_marker.drop_identical_backup(self.tmp / "root", new, dest))
        self.assertEqual((new / "__pycache__/data.txt").read_text(), "different\n")
        (new / "__pycache__/data.txt").write_text("same\n")
        (new / "__pycache__/extra.pyc").write_text("x")  # an extra entry
        self.assertIn("kept", perun_marker.drop_identical_backup(self.tmp / "root", new, dest))
        (new / "__pycache__/extra.pyc").unlink()
        self.assertIn("not kept", perun_marker.drop_identical_backup(self.tmp / "root", new, dest))
        self.assertFalse(new.exists())


class SettingsTree(unittest.TestCase):
    def test_added_and_strip_roundtrip(self):
        have = {"sandbox": {"enabled": False, "network": {"allowedDomains": ["mine.example.com"]}}, "permissions": {"deny": ["Bash(a)"]}}
        tpl = {"sandbox": {"enabled": True, "x": 1, "network": {"allowedDomains": ["mine.example.com", "github.com"]}}, "permissions": {"deny": ["Bash(a)", "Bash(b)"], "allow": ["Bash(c)"]}}
        add = perun_marker.added(have["sandbox"], tpl["sandbox"]), perun_marker.added(have["permissions"], tpl["permissions"])
        self.assertEqual(add[0], {"x": 1, "network": {"allowedDomains": ["github.com"]}})  # existing enabled=False wins: not recorded
        self.assertEqual(add[1], {"deny": ["Bash(b)"], "allow": ["Bash(c)"]})
        now = {"sandbox": {"enabled": False, "x": 1, "network": {"allowedDomains": ["mine.example.com", "github.com"]}}, "permissions": {"deny": ["Bash(a)", "Bash(b)"], "allow": ["Bash(c)"]}}
        perun_uninstall.strip(now["sandbox"], add[0]); perun_uninstall.strip(now["permissions"], add[1])
        self.assertEqual(now, have)


if __name__ == "__main__":
    unittest.main()
