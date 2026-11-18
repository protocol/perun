#!/usr/bin/env python3
"""secret_exposure_triage.first_seen never runs a program the scanned repository configures for `git log -p`.

A committed .gitattributes `diff=conv` plus a `diff.conv.textconv` in the repository config would make `git log -p` run that converter
on every matching blob and print its output instead of the blob, hiding the secret; a `log.showSignature` plus `gpg.program` in the
repository config would run that program on every signed commit. Offline, hermetic temp repo, fake secret."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SK = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts"
sys.path.insert(0, str(SK))
import secret_exposure_triage as st  # noqa: E402

SECRET = "FAKEKEY-textconv-000000000001"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "Jane Smith", "GIT_AUTHOR_EMAIL": "jane@example.com", "GIT_COMMITTER_NAME": "Jane Smith", "GIT_COMMITTER_EMAIL": "jane@example.com"}


def g(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True, env=ENV).stdout


class T(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        g(self.repo, "init", "-q", "-b", "main")

    def tearDown(self):
        self.td.cleanup()

    def test_textconv_driver_never_runs(self):
        marker, conv = self.root / "conv-ran", self.root / "conv.sh"
        conv.write_text(f"#!/bin/sh\ntouch '{marker}'\necho converted\n")
        conv.chmod(0o755)
        (self.repo / ".gitattributes").write_text("*.env diff=conv\n")
        (self.repo / "a.env").write_text(f"KEY={SECRET}\n")
        g(self.repo, "config", "diff.conv.textconv", str(conv))
        g(self.repo, "add", ".")
        g(self.repo, "commit", "-qm", "add env")
        sha = g(self.repo, "rev-parse", "HEAD").strip()
        found = st.first_seen(str(self.repo), {SECRET})
        self.assertFalse(marker.exists(), "the repository's textconv driver ran")
        self.assertEqual(found.get(SECRET, ("",))[0], sha)

    def test_gpg_program_never_runs(self):
        marker, gpg = self.root / "gpg-ran", self.root / "gpg.sh"
        gpg.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
        gpg.chmod(0o755)
        (self.repo / "a.env").write_text(f"KEY={SECRET}\n")
        g(self.repo, "add", ".")
        tree = g(self.repo, "write-tree").strip()
        sig = "gpgsig -----BEGIN PGP SIGNATURE-----\n \n AAAA\n -----END PGP SIGNATURE-----\n"  # a fake signature: git hands it to gpg.program to verify
        who = "Jane Smith <jane@example.com> 1700000000 +0000"
        raw = f"tree {tree}\nauthor {who}\ncommitter {who}\n{sig}\nsigned\n"
        sha = subprocess.run(["git", "-C", str(self.repo), "hash-object", "-t", "commit", "-w", "--stdin"], input=raw, check=True, capture_output=True, text=True, env=ENV).stdout.strip()
        g(self.repo, "update-ref", "refs/heads/main", sha)
        g(self.repo, "config", "log.showSignature", "true")
        g(self.repo, "config", "gpg.program", str(gpg))
        found = st.first_seen(str(self.repo), {SECRET})
        self.assertFalse(marker.exists(), "the repository's gpg.program ran")
        self.assertEqual(found.get(SECRET, ("",))[0], sha)


if __name__ == "__main__":
    unittest.main()
