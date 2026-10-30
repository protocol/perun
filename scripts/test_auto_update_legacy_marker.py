#!/usr/bin/env python3
"""Tests for the legacy-install path of perun_auto_update.py (`.dcr-install-flags` but no `.perun-install.json`)
and for install.sh always recording a remote in the marker. Offline: fixtures live under $TMPDIR."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_auto_update import au, ROOT, fake_remote  # noqa: E402, F401

SKILL = ".claude/skills/deep-code-review/SKILL.md"
FRONT = '---\nname: deep-code-review\nmetadata:\n  author: x\n  version: "1.2.0"\n---\n# body\nversion: "9.9.9"\n'


def legacy_install(base: Path, front: str = FRONT, flags: bool = True) -> Path:
    """A repo as an old install left it: skill + .dcr-install-flags, no .perun-install.json."""
    t = base / "legacy"
    (t / ".claude/skills/deep-code-review").mkdir(parents=True)
    (t / SKILL).write_text(front)
    if flags:
        (t / ".claude/.dcr-install-flags").write_text("--with-delivery\n")
    subprocess.run(["git", "init", "-q", str(t)], check=True, capture_output=True)
    return t


class LegacyMarkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["XDG_CACHE_HOME"] = str(self.tmp / "cache")
        os.environ.pop("PERUN_POLICY", None)
        self.remote = fake_remote(self.tmp)
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(au, "CANONICAL_REMOTE", str(self.remote))
        p.start()
        self.addCleanup(p.stop)

    def log(self):
        f = au.cache() / "auto-update.log"
        return f.read_text() if f.is_file() else ""

    def test_legacy_install_updates_to_newest_tag(self):
        proj = legacy_install(self.tmp)
        self.assertEqual(au.run(proj), 0)
        self.assertEqual((proj / ".claude/ran").read_text().strip(), "1 v1.10.0")
        self.assertIn("legacy install", self.log())
        self.assertNotIn("no readable install marker", self.log())

    def test_version_is_read_from_frontmatter_not_body(self):
        self.assertEqual(au.legacy_marker(legacy_install(self.tmp)), {"version": "1.2.0", "remote": str(self.remote)})

    def test_unclosed_frontmatter_is_not_scanned_for_version(self):
        proj = legacy_install(self.tmp, '---\nname: deep-code-review\n# body, no closing fence\nversion: "1.2.0"\n')
        self.assertIsNone(au.legacy_marker(proj))
        self.assertEqual(au.run(proj), 0)
        self.assertFalse((proj / ".claude/ran").exists())
        self.assertIn("skip: no readable install marker", self.log())

    def test_foreign_cache_clone_origin_is_a_skip(self):
        other = fake_remote(self.tmp / "other")
        src = au.cache() / "src"
        subprocess.run(["git", "clone", "-q", "--no-checkout", str(other), str(src)], check=True, capture_output=True)
        proj = legacy_install(self.tmp)
        self.assertEqual(au.run(proj), 0)
        self.assertFalse((proj / ".claude/ran").exists())
        self.assertIn("is not the canonical remote", self.log())

    def test_canonical_cache_clone_origin_updates(self):
        src = au.cache() / "src"
        subprocess.run(["git", "clone", "-q", "--no-checkout", str(self.remote), str(src)], check=True, capture_output=True)
        proj = legacy_install(self.tmp)
        self.assertEqual(au.run(proj), 0)
        self.assertEqual((proj / ".claude/ran").read_text().strip(), "1 v1.10.0")

    def test_legacy_already_newest_is_up_to_date(self):
        proj = legacy_install(self.tmp, FRONT.replace("1.2.0", "1.10.0"))
        self.assertEqual(au.run(proj), 0)
        self.assertFalse((proj / ".claude/ran").exists())
        self.assertIn("up to date at 1.10.0", self.log())

    def test_no_flags_file_is_not_an_install(self):
        proj = legacy_install(self.tmp, flags=False)
        self.assertEqual(au.run(proj), 0)
        self.assertFalse((proj / ".claude/ran").exists())
        self.assertIn("skip: no readable install marker", self.log())

    def test_unreadable_version_is_a_skip(self):
        proj = legacy_install(self.tmp, "---\nname: deep-code-review\n---\n")
        self.assertEqual(au.run(proj), 0)
        self.assertFalse((proj / ".claude/ran").exists())
        self.assertIn("skip: no readable install marker", self.log())

    def test_corrupt_existing_marker_is_not_replaced_by_legacy(self):
        proj = legacy_install(self.tmp)
        (proj / ".claude/.perun-install.json").write_text("{not json")
        self.assertEqual(au.run(proj), 0)
        self.assertFalse((proj / ".claude/ran").exists())

    def test_safety_skips_still_apply_to_legacy(self):
        proj = legacy_install(self.tmp)
        (proj / ".git/MERGE_HEAD").write_text("x\n")
        self.assertEqual(au.run(proj), 0)
        self.assertFalse((proj / ".claude/ran").exists())
        self.assertIn("skip: MERGE_HEAD present", self.log())


class InstallRemoteFallbackTests(unittest.TestCase):
    def test_marker_remote_falls_back_to_canonical_without_a_git_origin(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        src = tmp / "src"  # a copy with no .git: the tarball/plugin case
        # docs/bench is ~90k files / ~400 MB (the copy alone took ~5 min); install.sh never reads it
        skip = lambda d, names: {n for n in names if n in (".git", "worktrees", "__pycache__") or (n == "bench" and Path(d) == ROOT / "docs")}
        shutil.copytree(ROOT, src, ignore=skip)
        repo = tmp / "repo"
        repo.mkdir()
        env = {k: v for k, v in os.environ.items() if k != "PERUN_REMOTE"} | {"DCR_NO_PROBE": "1"}  # no sandbox probe: it calls github.com
        p = subprocess.run(["bash", str(src / "install.sh"), str(repo)], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        m = json.loads((repo / ".claude/.perun-install.json").read_text())
        self.assertEqual(m["remote"], au.CANONICAL_REMOTE)


if __name__ == "__main__":
    unittest.main()
