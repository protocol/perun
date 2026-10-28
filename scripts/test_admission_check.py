#!/usr/bin/env python3
"""Tests: admission_check.py flags a batch class missing at admission, a stale or ownerless selection map, and fails closed on bad input."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

AC = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/admission_check.py"
NOW = 1_000_000
OK = {"batch_classes": ["typecheck", "unit", "e2e"], "admission_classes": ["typecheck", "unit", "e2e"], "map_owner": "lane-a",
      "map_refreshed": NOW - 3600, "map_max_age_h": 24}


def run(cfg, raw=None):
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "a.json"
        if cfg is not None:
            f.write_text(raw if raw is not None else json.dumps(cfg))
        r = subprocess.run([sys.executable, str(AC), "--file", str(f), "--now", str(NOW)], capture_output=True, text=True)
        return r.returncode, r.stdout


class Admission(unittest.TestCase):
    def test_complete_config_passes(self):
        self.assertEqual(run(OK), (0, "admission ok\n"))

    def test_missing_e2e_class_flagged(self):
        rc, out = run({**OK, "admission_classes": ["typecheck", "unit"]})
        self.assertEqual((rc, out), (1, "MISSING e2e\n"))

    def test_stale_map_and_no_owner_flagged(self):
        rc, out = run({**OK, "map_refreshed": NOW - 25 * 3600, "map_owner": " "})
        self.assertEqual(rc, 1)
        self.assertIn("MAP-NO-OWNER", out)
        self.assertIn("MAP-STALE 25.0h > 24h", out)

    def test_null_owner_and_future_date_rejected(self):
        self.assertEqual(run({**OK, "map_owner": None})[0], 1)
        self.assertIn("MAP-NO-OWNER", run({**OK, "map_owner": None})[1])
        self.assertEqual(run({**OK, "map_refreshed": NOW + 3600})[0], 2)

    def test_fail_closed(self):
        self.assertEqual(run(None)[0], 2)  # missing file
        self.assertEqual(run(OK, raw="not json")[0], 2)
        self.assertEqual(run({k: v for k, v in OK.items() if k != "map_owner"})[0], 2)  # missing key
        self.assertEqual(run({**OK, "admission_classes": []})[0], 2)  # empty list is not a pass
        self.assertEqual(run({**OK, "map_refreshed": "garbage"})[0], 2)


ROOT = Path(__file__).resolve().parent.parent
TL = ROOT / ".claude/skills/agentic-delivery/scripts/train_land.sh"


def git(cwd, *a):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})


class Wiring(unittest.TestCase):
    """The base branch's batch_classes decide, and train_land.sh refuses the train (exit 2) on a failing admission or host gate."""

    def setup_repo(self, d, base_cfg, pr_cfg, extra=None):
        git(d, "init", "-q", "-b", "main")
        (Path(d) / ".claude").mkdir()
        for name, c in {".claude/admission.json": base_cfg, **(extra or {})}.items():
            (Path(d) / name).write_text(json.dumps(c))
        git(d, "add", "-A")
        git(d, "commit", "-qm", "base")
        git(d, "update-ref", "refs/remotes/origin/main", "HEAD")
        (Path(d) / ".claude/admission.json").write_text(json.dumps(pr_cfg))
        git(d, "commit", "-aqm", "pr", "--allow-empty")

    def train(self, d):
        env = {**os.environ, "VERIFY_CMD": "true", "UNION_DIRS": ".", "LOG_DIR": d, "TRAIN_UNIQUE_RUN": "off"}
        return subprocess.run(["bash", str(TL), "t", "1", "2"], cwd=d, env=env, capture_output=True, text=True)

    def test_pr_cannot_drop_a_batch_class_and_train_refuses(self):
        fresh = {**OK, "map_refreshed": time.time() - 60}
        weak = {**fresh, "batch_classes": ["typecheck", "unit"], "admission_classes": ["typecheck", "unit"]}
        with tempfile.TemporaryDirectory() as d:
            self.setup_repo(d, {**fresh, "admission_classes": ["typecheck", "unit"]}, weak)
            r = subprocess.run([sys.executable, str(AC), "--base", "origin/main"], cwd=d, capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout), (1, "MISSING e2e\n"))  # base says e2e is a batch class
            t = self.train(d)
            self.assertEqual(t.returncode, 2, t.stderr)
            self.assertIn("admission_check failed", t.stderr)

    def test_train_refuses_when_pr_deletes_admission_config_the_base_has(self):
        with tempfile.TemporaryDirectory() as d:
            self.setup_repo(d, {**OK, "map_refreshed": time.time() - 60}, {})
            (Path(d) / ".claude/admission.json").unlink()
            git(d, "commit", "-aqm", "rm")
            t = self.train(d)
            self.assertEqual(t.returncode, 2, t.stderr)
            self.assertIn("admission_check failed", t.stderr)

    def test_train_refuses_on_unaccepted_host(self):
        ok = {**OK, "map_refreshed": time.time() - 60}
        with tempfile.TemporaryDirectory() as d:
            self.setup_repo(d, ok, ok, {".claude/host-accept.json": {"operator_reset": {"verified": False}, "auto_reset": {}, "mem_caps": {}}})
            t = self.train(d)
            self.assertEqual(t.returncode, 2, t.stderr)
            self.assertIn("host_accept failed", t.stderr)


if __name__ == "__main__":
    unittest.main()
