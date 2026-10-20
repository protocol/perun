#!/usr/bin/env python3
"""Tests for the long-job lease (job_lease.py) and the queue lines waiters print (issue #1574).

Covers: the lease serializes two runs in one repo and fails closed on timeout; each run gets a unique PERUN_RUN_SUFFIX;
serial_gate, _lock.sh and train_land.sh waiters print "queued"/"waiting" lines at the PERUN_QUEUE_NOTE_SECS interval.
Everything lives in temp dirs; no signals, no process-table matching, no host-wide effects. Run: python3 scripts/test_job_lease.py
"""
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SC = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"
ENV = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "PYTHONDONTWRITEBYTECODE": "1"}
ENV.pop("PERUN_RUN_SUFFIX", None)


def lease(repo, *args, env=None, **kw):
    return subprocess.run([sys.executable, str(SC / "job_lease.py"), *args], cwd=repo, capture_output=True, text=True,
                          env={**ENV, **(env or {})}, **kw)


class JobLease(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True, env=ENV)

    def test_suffix_unique_and_identifier_safe(self):
        a, b = (lease(self.repo, "suffix").stdout.strip() for _ in range(2))
        self.assertNotEqual(a, b)
        self.assertRegex(a, r"^[0-9]+_[0-9a-f]{6}$")

    def test_run_propagates_exit_code_and_exports_suffix(self):
        out = self.repo / "out"
        r = lease(self.repo, "run", "--", sys.executable, "-c",
                  f"import os,sys; open({str(out)!r},'w').write(os.environ['PERUN_RUN_SUFFIX']); sys.exit(7)")
        self.assertEqual(r.returncode, 7)
        self.assertRegex(out.read_text(), r"^[0-9]+_[0-9a-f]{6}$")

    def test_second_run_waits_prints_queue_line_and_never_runs_on_timeout(self):
        ready, release, ran = (self.repo / n for n in ("ready", "release", "ran"))
        hold = (f"import os,time; open({str(ready)!r},'w').close()\n"
                f"while not os.path.exists({str(release)!r}): time.sleep(0.05)")
        first = subprocess.Popen([sys.executable, str(SC / "job_lease.py"), "run", "--", sys.executable, "-c", hold],
                                 cwd=self.repo, env=ENV)
        try:
            for _ in range(200):
                if ready.exists():
                    break
                time.sleep(0.05)
            self.assertTrue(ready.exists(), "first run never took the lease")
            r = lease(self.repo, "run", "--timeout", "1", "--", sys.executable, "-c", f"open({str(ran)!r},'w')",
                      env={"PERUN_QUEUE_NOTE_SECS": "0.2"})
            self.assertEqual(r.returncode, 124)
            self.assertIn("queued", r.stderr)
            self.assertFalse(ran.exists(), "command ran without the lease")
            other = lease(self.repo, "run", "--name", "other", "--", sys.executable, "-c", "pass")
            self.assertEqual(other.returncode, 0, "a different lease name must not block")
        finally:
            release.touch()
            first.wait(timeout=30)
        self.assertEqual(first.returncode, 0)
        self.assertEqual(lease(self.repo, "run", "--", sys.executable, "-c", "pass").returncode, 0)

    def test_fails_closed_without_repo_command_or_safe_name(self):
        with tempfile.TemporaryDirectory() as nogit:
            r = lease(nogit, "run", "--", sys.executable, "-c", "print('ran')", env={"GIT_CEILING_DIRECTORIES": nogit})
            self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertEqual(lease(self.repo, "run").returncode, 2)
        self.assertEqual(lease(self.repo, "run", "--name", "../x", "--", "true").returncode, 2)


class QueueLines(unittest.TestCase):
    def test_lock_sh_waiter_repeats_its_line(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "l.lock"
            d.mkdir()
            (d / "pid").write_text(str(os.getpid()))  # a live holder: this test process
            (d / "ts").write_text(str(int(time.time())))
            r = subprocess.run(["bash", "-c", f'. "{SC}/_lock.sh"; lock_take "{d}" 3 30'], capture_output=True,
                               text=True, env={**ENV, "PERUN_QUEUE_NOTE_SECS": "1"})
            self.assertEqual(r.returncode, 1)
            self.assertGreaterEqual(len(re.findall(r"^waiting on lock", r.stderr, re.M)), 2, r.stderr)

    def test_train_land_lease_wait_prints_queue_line(self):
        with tempfile.TemporaryDirectory() as t:
            repo = Path(t) / "repo"
            repo.mkdir()
            git = ["git", "-c", "user.email=t@example.com", "-c", "user.name=T"]
            subprocess.run(git + ["init", "-q"], cwd=repo, check=True, env=ENV)
            subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "base"], cwd=repo, check=True, env=ENV)
            hv = Path(t) / "hv"
            hv.mkdir()
            (hv / "heavy.exclusive").write_text(f"{os.getpid()} {int(time.time())}")  # a live holder
            r = subprocess.run(["bash", str(SC / "train_land.sh"), "tl", "1", "3"], cwd=repo, capture_output=True, text=True,
                               env={**ENV, "PERUN_HEAVY_DIR": str(hv / "heavy"), "LEASE_WAIT_SECS": "3", "VERIFY_CMD": "true", "UNION_DIRS": str(repo),
                                    "PERUN_QUEUE_NOTE_SECS": "1"})
            self.assertEqual(r.returncode, 4, r.stderr)
            self.assertRegex(r.stderr, r"queued \d+s: another gate holds the exclusive heavy lease")


if __name__ == "__main__":
    unittest.main()
