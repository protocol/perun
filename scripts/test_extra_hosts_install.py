#!/usr/bin/env python3
"""--with-extra-hosts: every host root gets the skill, doctor is clean (and sees drift there), uninstall leaves 0 files.

Fixture repo and HOME live under $TMPDIR. Principle: nothing is deleted unless it is an unmodified shipped copy."""
import os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import perun_doctor  # noqa: E402

os.environ["DCR_NO_PROBE"] = "1"
os.environ["DCR_COPY_HOSTS"] = "1"  # this file tests the real-copy path; symlinked hosts are in test_install_canonical_global.py
# Hosts whose skill root was confirmed from the vendor docs on 2026-10-16 (URLs in docs/standards-index.md).
NEW_HOSTS = (".cline", ".roo", ".factory")
DOCS_HOSTS = (".opencode", ".kiro", ".windsurf") + NEW_HOSTS  # plus Amp, which reads .agents and .claude (already default)
EXTRA = (".gemini", ".opencode", ".github", ".windsurf", ".hermes", ".kiro") + NEW_HOSTS


def run(*cmd):
    return subprocess.run(list(map(str, cmd)), capture_output=True, text=True)


def install(repo, *flags):
    p = run("bash", ROOT / "install.sh", *flags, repo)
    assert p.returncode == 0, p.stderr
    return p


def tree(repo):
    return sorted(str(p.relative_to(repo)) for p in Path(repo).rglob("*"))


def uninstall(repo):
    return run(sys.executable, ROOT / "scripts/perun_uninstall.py", repo, "--apply")


class ExtraHosts(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=os.environ.get("TMPDIR") or None))
        self.repo, self.home = self.tmp / "r", self.tmp / "h"
        self.repo.mkdir(); self.home.mkdir()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def skill(self, host):
        return self.repo / host / "skills/deep-code-review"

    def test_each_host_gets_valid_skill(self):
        install(self.repo, "--with-extra-hosts")
        for h in EXTRA:
            md = (self.skill(h) / "SKILL.md").read_text()
            self.assertRegex(md, r"(?m)^name: deep-code-review$", h)  # name must match the directory per every host's docs

    def test_default_install_has_no_extra_hosts(self):
        install(self.repo)
        self.assertFalse(any((self.repo / h).exists() for h in NEW_HOSTS))

    def test_doctor_clean_then_sees_drift_in_new_host(self):
        install(self.repo, "--with-extra-hosts")
        self.assertEqual(perun_doctor.main([str(self.repo), "--home", str(self.home)]), 0)
        for h in NEW_HOSTS:
            f = self.skill(h) / "SKILL.md"
            f.write_text(f.read_text() + "\nedit\n")
        rows = {c: d for _, c, d in perun_doctor.check(self.repo, self.home)}
        for h in NEW_HOSTS:
            self.assertIn(f"{h}/skills/deep-code-review/SKILL.md", rows["drifted copies"])

    def test_install_doctor_uninstall_leaves_nothing(self):
        before = tree(self.repo)
        install(self.repo, "--with-extra-hosts")
        install(self.repo, "--with-extra-hosts")  # re-run adds no backup
        self.assertEqual(perun_doctor.main([str(self.repo), "--home", str(self.home)]), 0)
        self.assertEqual(uninstall(self.repo).returncode, 0)
        self.assertEqual(tree(self.repo), before)

    def test_preexisting_copy_restored_and_edited_copy_kept(self):
        for h in NEW_HOSTS:
            d = self.skill(h)
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text("mine\n")
        before = tree(self.repo)
        install(self.repo, "--with-extra-hosts")
        self.assertEqual(uninstall(self.repo).returncode, 0)
        for h in NEW_HOSTS:
            self.assertEqual((self.skill(h) / "SKILL.md").read_text(), "mine\n")
        self.assertEqual(tree(self.repo), before)
        install(self.repo, "--with-extra-hosts")
        edited = self.skill(".cline") / "SKILL.md"
        edited.write_text("user edit\n")
        self.assertEqual(uninstall(self.repo).returncode, 0)
        self.assertEqual(edited.read_text(), "user edit\n")  # modified file is never deleted

    def test_docs_validated_hosts_are_recorded(self):
        idx = (ROOT / "docs/standards-index.md").read_text()
        sec = idx.split("2026-10-16) — agent skill roots", 1)[1]
        for h in DOCS_HOSTS:
            self.assertRegex(sec, re.escape(h + "/skills"), h)


if __name__ == "__main__":
    unittest.main()
