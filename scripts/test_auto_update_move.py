#!/usr/bin/env python3
"""Tests for the repository move: a marker or cache clone whose remote is the pre-move home migrates to the
canonical remote, and only those two URLs are accepted. Offline: the canonical remote is a local git repo."""
import json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_auto_update import au, fake_installed, fake_remote  # noqa: E402

OLD = "https://github.com/remigiusz-antczak/deep-code-review.git"
NEW = "https://github.com/protocol/perun.git"


class MoveTests(unittest.TestCase):
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

    def set_marker_remote(self, proj, url):
        mf = proj / ".claude/.perun-install.json"
        m = json.loads(mf.read_text())
        m["remote"] = url
        mf.write_text(json.dumps(m))

    def test_constants(self):
        self.assertEqual(au.LEGACY_REMOTE, OLD)
        src = (Path(au.__file__)).read_text()
        self.assertIn(f'CANONICAL_REMOTE = "{NEW}"', src)

    def test_is_canonical_accepts_only_the_two_urls(self):
        with mock.patch.object(au, "CANONICAL_REMOTE", NEW):
            for ok in (NEW, OLD, NEW[:-4], OLD[:-4], OLD[:-4] + "/"):
                self.assertTrue(au.is_canonical(ok), ok)
            for bad in ("", "https://github.com/evil/perun.git", NEW + "x", "https://github.com/protocol/perun-fork.git",
                        "https://github.com/remigiusz-antczak/other.git", "git@github.com:protocol/perun.git"):
                self.assertFalse(au.is_canonical(bad), bad)

    def test_marker_with_old_remote_migrates_to_canonical(self):
        proj = fake_installed(self.tmp, self.remote)
        self.set_marker_remote(proj, OLD)  # OLD is unreachable offline: success proves the fetch used CANONICAL_REMOTE
        self.assertEqual(au.run(proj), 0, self.log())
        self.assertEqual((proj / ".claude/ran").read_text().strip(), "1 v1.10.0")

    def test_foreign_marker_remote_is_not_rewritten(self):
        proj = fake_installed(self.tmp, self.remote)
        self.set_marker_remote(proj, str(self.tmp / "nowhere"))
        self.assertEqual(au.run(proj), 0)
        self.assertFalse((proj / ".claude/ran").exists())
        self.assertIn("cannot list tags", self.log())

    def test_legacy_install_accepts_cache_clone_with_old_origin(self):
        src = au.cache() / "src"
        subprocess.run(["git", "clone", "-q", "--no-checkout", str(self.remote), str(src)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(src), "remote", "set-url", "origin", OLD], check=True, capture_output=True)
        proj = self.tmp / "legacy"
        (proj / ".claude/skills/deep-code-review").mkdir(parents=True)
        (proj / ".claude/skills/deep-code-review/SKILL.md").write_text('---\nname: deep-code-review\nmetadata:\n  version: "1.2.0"\n---\n')
        (proj / ".claude/.dcr-install-flags").write_text("--with-delivery\n")
        subprocess.run(["git", "init", "-q", str(proj)], check=True, capture_output=True)
        self.assertEqual(au.run(proj), 0, self.log())
        self.assertEqual((proj / ".claude/ran").read_text().strip(), "1 v1.10.0")


if __name__ == "__main__":
    unittest.main()
