#!/usr/bin/env python3
"""Tests: lkg.py records the HEAD blob of scripts/run-ci-tests.sh, refuses a stale working-tree runner, rejects receipts lacking provenance."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude/skills/agentic-delivery/scripts"))
import lkg  # noqa: E402

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True, env=GIT_ENV).stdout.strip()


class Provenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.environ["PERUN_LANDING_DIR"] = os.path.join(self.tmp, "state")
        self.addCleanup(os.environ.pop, "PERUN_LANDING_DIR")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.repo, "scripts"))
        git(self.repo, "init", "-q", "-b", "main")
        self.runner = Path(self.repo, "scripts/run-ci-tests.sh")
        self.runner.write_text("exit 0\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "one")
        self.head = git(self.repo, "rev-parse", "HEAD")

    def test_records_head_blob_and_check_accepts(self):
        rec = lkg.record(self.repo)
        self.assertEqual(rec["runner"], git(self.repo, "rev-parse", "HEAD:scripts/run-ci-tests.sh"))
        self.assertTrue(lkg.check(self.head, self.repo)[0])

    def test_stale_working_tree_runner_refused(self):
        self.runner.write_text("exit 0  # old copy\n")
        with self.assertRaisesRegex(ValueError, "stale runner"):
            lkg.record(self.repo)
        self.assertIsNone(lkg.read(self.repo))

    def test_receipt_without_provenance_rejected(self):
        lkg.record(self.repo)
        rec = lkg.read(self.repo)
        del rec["runner"]
        import json
        Path(lkg.path(self.repo)).write_text(json.dumps(rec))
        ok, msg = lkg.check(self.head, self.repo)
        self.assertFalse(ok)
        self.assertIn("runner provenance missing", msg)

    def test_git_failure_fails_closed(self):
        with self.assertRaises(RuntimeError):
            lkg.runner_blob("deadbeef" * 5, self.repo)

    def test_repo_without_runner_skips(self):
        git(self.repo, "rm", "-q", "scripts/run-ci-tests.sh")
        git(self.repo, "commit", "-qm", "two")
        self.assertEqual(lkg.record(self.repo)["runner"], "")


if __name__ == "__main__":
    unittest.main()
