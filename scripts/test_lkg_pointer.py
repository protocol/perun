#!/usr/bin/env python3
"""Tests for the last-known-good pointer: record, stale-age alarm in landing_watchdog, land-release.sh shadow/enforce check."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
import landing_watchdog as lw  # noqa: E402
import lkg  # noqa: E402


def git(cwd, *a):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}).stdout.strip()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = mock_env = {"PERUN_LANDING_DIR": os.path.join(self.tmp, "state")}
        old = {k: os.environ.get(k) for k in mock_env}
        os.environ.update(mock_env)
        self.addCleanup(lambda: [os.environ.pop(k) if v is None else os.environ.__setitem__(k, v) for k, v in old.items()])
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        Path(self.repo, "a").write_text("1")
        git(self.repo, "add", "a")
        git(self.repo, "commit", "-qm", "one")
        self.first = git(self.repo, "rev-parse", "HEAD")


class Record(Base):
    def test_record_head_and_read_back(self):
        rec = lkg.record(self.repo)
        self.assertEqual(rec["sha"], self.first)
        self.assertEqual(lkg.read(self.repo), rec)
        self.assertRegex(rec["utc"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_check_head_must_equal_lkg_and_reports_gap(self):
        self.assertFalse(lkg.check(self.first, self.repo)[0])  # nothing recorded
        lkg.record(self.repo)
        self.assertTrue(lkg.check(self.first, self.repo)[0])
        Path(self.repo, "a").write_text("2")
        git(self.repo, "commit", "-qam", "two")
        ok, msg = lkg.check(git(self.repo, "rev-parse", "HEAD"), self.repo)
        self.assertFalse(ok)
        self.assertIn("1 untested commits since", msg)
        git(self.repo, "checkout", "-q", "--orphan", "other")
        git(self.repo, "commit", "-qm", "root")
        self.assertIn("not a descendant of", lkg.check(git(self.repo, "rev-parse", "HEAD"), self.repo)[1])

    def test_record_rejects_unknown_sha_and_leaves_no_tmp(self):
        with self.assertRaises(Exception):
            lkg.record(self.repo, sha="deadbeef" * 5)
        lkg.record(self.repo)
        self.assertEqual([n for n in os.listdir(os.path.dirname(lkg.path(self.repo))) if n.endswith(".tmp")], [])

    def test_worktrees_share_one_pointer(self):
        wt = os.path.join(self.tmp, "wt")
        git(self.repo, "worktree", "add", "-q", "--detach", wt)
        lkg.record(self.repo)
        self.assertEqual(lkg.path(wt), lkg.path(self.repo))


class Stale(Base):
    def alarm(self, limit, hours):
        lkg.record(self.repo, now=time.time() - hours * 3600)
        import perun_policy
        orig = perun_policy.load
        perun_policy.load = lambda *a: {"lkg_stale_h": limit}
        try:
            return lw._lkg(self.repo)
        finally:
            perun_policy.load = orig

    def test_old_pointer_alarms(self):
        self.assertIn("Last-known-good is 30.0 h old (limit 24 h)", self.alarm(24, 30))

    def test_fresh_or_off_is_quiet(self):
        self.assertIsNone(self.alarm(24, 1))
        self.assertIsNone(self.alarm(0, 99))

    def test_no_pointer_and_errors_fail_open(self):
        self.assertIsNone(lw._lkg(self.repo))
        self.assertIsNone(lw._lkg("/nonexistent-dir"))


class Release(Base):
    def land(self, mode, record, extra_origin_commit=False, break_lkg=False):
        """Run land-release.sh in a clone; return (rc, stderr). The LKG, when recorded, is the first commit."""
        clone = os.path.join(self.tmp, "clone")
        git(self.tmp, "clone", "-q", self.repo, clone)
        (Path(clone) / "scripts").mkdir()
        shutil.copy(ROOT / "scripts/land-release.sh", Path(clone) / "scripts")
        shutil.copytree(SC, Path(clone) / ".claude/skills/agentic-delivery/scripts")
        (Path(clone) / ".perun").mkdir()
        (Path(clone) / ".perun/policy.json").write_text(json.dumps({"lkg_gate": mode}))
        git(clone, "add", "-A")
        git(clone, "commit", "-qm", "scaffold")
        if record:
            lkg.record(clone, sha=self.first)
        if extra_origin_commit:
            Path(self.repo, "a").write_text("2")
            git(self.repo, "commit", "-qam", "two")
        if break_lkg:
            (Path(clone) / ".claude/skills/agentic-delivery/scripts/lkg.py").write_text("raise SystemExit(7)\n")
            git(clone, "commit", "-qam", "break")
        r = subprocess.run(["bash", "scripts/land-release.sh"], cwd=clone, capture_output=True, text=True)
        shutil.rmtree(clone)
        return r.returncode, r.stderr

    def test_enforce_refuses_without_lkg_and_shadow_only_logs(self):
        rc, err = self.land("enforce", False)
        self.assertEqual(rc, 1)
        self.assertIn("no last-known-good recorded", err)
        rc, err = self.land("shadow", False)
        self.assertIn("no last-known-good recorded", err)
        self.assertIn("no changelog.d", err)  # warned, not refused: it went on to fail at the fragment check

    def test_diverged_head_reports_gap_enforce_refuses_shadow_warns(self):
        rc, err = self.land("enforce", True, extra_origin_commit=True)
        self.assertEqual(rc, 1)
        self.assertIn("1 untested commits since", err)
        rc, err = self.land("shadow", True)
        self.assertIn("1 untested commits since", err)
        self.assertIn("no changelog.d", err)

    def test_enforce_passes_when_origin_is_lkg(self):
        rc, err = self.land("enforce", True)
        self.assertNotIn("lkg gate", err)
        self.assertIn("no changelog.d", err)

    def test_off_skips(self):
        rc, err = self.land("off", False)
        self.assertNotIn("lkg gate", err)

    def test_enforce_refuses_with_rc2_when_lkg_py_crashes(self):
        rc, err = self.land("enforce", True, break_lkg=True)
        self.assertEqual(rc, 2)
        self.assertIn("lkg.py crashed (rc=7)", err)


class Policy(Base):
    def test_lkg_gate_and_stale_keys_validate_and_read(self):
        import perun_policy as pp
        self.assertEqual(pp.validate({})["lkg_gate"], "shadow")
        self.assertEqual(pp.validate({"lkg_gate": "enforce", "lkg_stale_h": 24})["lkg_stale_h"], 24)
        for bad in ({"lkg_gate": "block"}, {"lkg_stale_h": -1}):
            with self.assertRaises(Exception):
                pp.validate(bad)
        pol = Path(self.tmp, "p.json")
        pol.write_text(json.dumps({"lkg_gate": "enforce"}))
        r = subprocess.run([sys.executable, str(SC / "perun_policy.py"), "get", "lkg_gate"], capture_output=True, text=True,
                           env={**os.environ, "PERUN_POLICY": str(pol)})
        self.assertEqual(r.stdout.strip(), "enforce")


class Runner(Base):
    def run_suite(self, body):
        """Run run-ci-tests.sh in a scaffold repo whose ci-tests.d holds one test with `body`; return (rc, lkg pointer)."""
        r = os.path.join(self.tmp, "suite")
        shutil.rmtree(r, True)
        git(self.tmp, "clone", "-q", self.repo, r)
        (Path(r) / "scripts/ci-tests.d").mkdir(parents=True)
        shutil.copy(ROOT / "scripts/run-ci-tests.sh", Path(r) / "scripts")
        shutil.copytree(SC, Path(r) / ".claude/skills/agentic-delivery/scripts")
        (Path(r) / "scripts/ci-tests.d/t.sh").write_text(body)
        rc = subprocess.run(["bash", "scripts/run-ci-tests.sh"], cwd=r, capture_output=True).returncode
        return rc, lkg.read(r)

    def test_records_on_pass_not_on_fail(self):
        rc, rec = self.run_suite("false\n")
        self.assertEqual((rc, rec), (1, None))
        rc, rec = self.run_suite("true\n")
        self.assertEqual(rc, 0)
        self.assertEqual(rec["sha"], self.first)


if __name__ == "__main__":
    unittest.main()
