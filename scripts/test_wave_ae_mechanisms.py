#!/usr/bin/env python3
"""Tests: unique run dir, SHA-bound verdict, strict wired/run-record hand-back check, vendored-copy drift (each with fail-closed paths)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SD = ROOT / ".claude/skills/agentic-delivery/scripts"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


def run(*a, cwd=None, env=None):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, env=env or ENV)


def git(cwd, *a):
    return run("git", *a, cwd=cwd).stdout.strip()


class WaveAE(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.d = Path(self.t.name)

    def test_run_ci_tests_run_dir(self):
        d = self.d / "rd"
        d.mkdir()
        r = run("bash", str(ROOT / "scripts/run-ci-tests.sh"), env={**ENV, "PERUN_RUN_DIR": str(d)})  # refuses before running any test
        self.assertEqual(r.returncode, 1)
        self.assertIn("already exists", r.stderr)

    def test_run_dir_unique(self):
        env = {**ENV, "PERUN_HEAVY_WAIT_SECS": "5", "PERUN_LANDING_DIR": str(self.d / "s"), "PERUN_HEAVY_DIR": str(self.d / "h")}
        rd = self.d / "run1"
        a = run(sys.executable, str(SD / "stage_run.py"), "--hook", "--run-dir", str(rd), "--", "true", env=env)
        self.assertEqual(a.returncode, 0, a.stderr)
        self.assertTrue(rd.is_dir())
        b = run(sys.executable, str(SD / "stage_run.py"), "--hook", "--run-dir", str(rd), "--", "true", env=env)
        self.assertEqual(b.returncode, 1)
        self.assertIn("already exists", b.stderr)

    def test_verdict_sha_bound(self):
        repo = self.d / "r"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(repo, "commit", "-q", "--allow-empty", "-m", "a")
        old = git(repo, "rev-parse", "HEAD")
        v = self.d / "v.json"
        v.write_text(json.dumps({"sha": old, "status": "pass"}))
        self.assertEqual(run(sys.executable, str(SD / "lkg.py"), "verdict", str(v), cwd=repo).returncode, 0)
        git(repo, "commit", "-q", "--allow-empty", "-m", "b")
        r = run(sys.executable, str(SD / "lkg.py"), "verdict", str(v), cwd=repo)
        self.assertEqual((r.returncode, "rerun" in r.stdout), (1, True))
        for bad in ("{}", "not json"):
            v.write_text(bad)
            self.assertEqual(run(sys.executable, str(SD / "lkg.py"), "verdict", str(v), cwd=repo).returncode, 1)
        self.assertEqual(run(sys.executable, str(SD / "lkg.py"), "verdict", str(self.d / "none"), cwd=repo).returncode, 1)
        head = git(repo, "rev-parse", "HEAD")
        for rec, rc in (({"sha": head}, 1), ({"sha": head, "status": "fail"}, 1), ({"sha": head, "status": "pass"}, 0)):  # a sha alone is not green
            v.write_text(json.dumps(rec))
            self.assertEqual(run(sys.executable, str(SD / "lkg.py"), "verdict", str(v), cwd=repo).returncode, rc, rec)

    def test_strict_needs_caller_and_run_record(self):
        repo = self.d / "w"
        (repo / "scripts").mkdir(parents=True)
        git(repo, "init", "-q", "-b", "main")
        (repo / "README").write_text("x")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "base")
        (repo / "scripts/newtool.py").write_text("print(1)\n")
        (repo / "Makefile").write_text("all:\n\tpython3 scripts/newtool.py\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "add")
        wc = [sys.executable, str(SD / "wired_check.py"), "HEAD~1", "HEAD", "--root", str(repo), "--strict"]
        log = self.d / "runs.log"
        self.assertEqual(run(*wc, "--runs", str(log)).returncode, 1)  # missing record: fail closed
        log.write_text("2026-01-01 ran other.py\n")
        self.assertEqual(run(*wc, "--runs", str(log)).returncode, 1)  # no line for this script
        log.write_text("2026-01-01 ran newtool.py rc=0\n")
        self.assertEqual(run(*wc, "--runs", str(log)).returncode, 0)
        log.write_text("2026-01-01 ran stage_newtool.py rc=0\n")  # substring of another name is not a run of this one
        self.assertEqual(run(*wc, "--runs", str(log)).returncode, 1)
        log.write_text("ran newtool.py\n")
        self.assertEqual(run(sys.executable, str(SD / "wired_check.py"), "HEAD", "HEAD", "--root", str(repo), "--strict", "--runs", str(self.d / "missing")).returncode, 1)  # no new script, missing record: still fails
        (repo / "Makefile").unlink()
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "drop caller")
        base = git(repo, "rev-parse", "HEAD~2")
        r = run(sys.executable, str(SD / "wired_check.py"), base, "HEAD", "--root", str(repo), "--strict", "--runs", str(log))
        self.assertEqual(r.returncode, 1)  # unwired
        self.assertEqual(run(sys.executable, str(SD / "wired_check.py"), "HEAD~1", "HEAD", "--strict").returncode, 1)  # no --runs: usage

    def test_vendor_drift(self):
        src, tgt = self.d / "src", self.d / "tgt"
        for root in (src, tgt):
            (root / ".claude/skills/foo").mkdir(parents=True)
        s = src / ".claude/skills"
        t = tgt / ".claude/skills"
        (s / "foo/a.md").write_text("A")
        (s / "foo/b.md").write_text("B")
        (s / "bar").mkdir()
        (s / "bar/c.md").write_text("C")  # not vendored: skipped
        (t / "foo/a.md").write_text("A")
        (t / "foo/b.md").write_text("B")
        vd = [sys.executable, str(SD / "vendor_drift.py"), str(tgt), "--src", str(s)]
        self.assertEqual(run(*vd).returncode, 0)
        (t / "foo/a.md").write_text("A edited")
        (t / "foo/b.md").unlink()
        (t / "foo/x.md").write_text("X")
        r = run(*vd)
        self.assertEqual(r.returncode, 1)
        for line in ("DRIFT foo/a.md", "MISSING foo/b.md", "EXTRA foo/x.md"):
            self.assertIn(line, r.stdout)
        self.assertEqual(run(sys.executable, str(SD / "vendor_drift.py"), str(self.d / "nope"), "--src", str(s)).returncode, 1)
        (t / "foo/a.md").write_text("A")
        (t / "foo/b.md").write_text("B")
        (t / "foo/x.md").unlink()
        (t / "foo/__pycache__").mkdir()
        (t / "foo/__pycache__/m.pyc").write_text("c")
        (t / "foo/.DS_Store").write_text("d")
        self.assertEqual(run(*vd).returncode, 0)  # junk files are not drift
        r = run(*vd, "--skills", "foo,bar")
        self.assertEqual((r.returncode, "MISSING bar/" in r.stdout), (1, True))  # a deleted vendored skill is drift
        import shutil
        shutil.rmtree(t / "foo")
        self.assertEqual(run(*vd).returncode, 1)  # zero overlap: nothing compared is not clean


if __name__ == "__main__":
    unittest.main()
