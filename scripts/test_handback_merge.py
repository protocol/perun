#!/usr/bin/env python3
"""handback.py --merge-pr: dry run by default, --apply merges only after GREEN. Offline: stub `gh` on PATH."""
import json
import stat
import subprocess
import sys
import unittest

import test_handback as th

STUB = th.STUB.replace("  *required_status", '  "pr merge"*) exit "$(cat "$FAKE/merge_rc" 2>/dev/null || echo 0)" ;;\n  "pr view"*) cat "$FAKE/pr.json" ;;\n  *required_status')


class M(unittest.TestCase):
    setUp, tearDown, git, commit, lane, runs = (th.T.setUp, th.T.tearDown, th.T.git, th.T.commit, th.T.lane, th.T.runs)

    def hb(self, sha, *extra, status="success", gate="true", pr_head=None, pr_base="main", protection=True):
        (self.d / "gh").write_text(STUB)
        (self.d / "gh").chmod((self.d / "gh").stat().st_mode | stat.S_IEXEC)
        (self.d / "protection.json").write_text(json.dumps({"checks": [{"context": "unit"}]}) if protection else "not json")
        (self.d / "checks.json").write_text(json.dumps(self.runs(sha, status="completed" if status != "pending" else "in_progress",
                                                                 conclusion=None if status == "pending" else status)))
        (self.d / "pr.json").write_text(json.dumps({"baseRefName": pr_base, "headRefOid": pr_head or sha}))
        cmd = [sys.executable, str(th.SCRIPT), "--sha", sha, "--base", "main", "--branch", "lane", "--gate-cmd", gate,
               "--repo", "acme/widgets", "--merge-pr", "7", *extra]
        return subprocess.run(cmd, cwd=self.repo, env=self.env, capture_output=True, text=True, stdin=subprocess.DEVNULL)

    def merged(self):
        return (self.d / "calls.log").exists() and "pr merge 7" in (self.d / "calls.log").read_text()

    def test_dry_run_prints_the_pinned_merge_and_does_not_merge(self):
        sha = self.lane()
        r = self.hb(sha)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(f"gh pr merge 7 --repo acme/widgets --merge --match-head-commit {sha}", r.stdout)
        self.assertIn("git push origin --delete lane", r.stdout)
        self.assertFalse(self.merged())

    def test_apply_merges_when_green(self):
        sha = self.lane()
        r = self.hb(sha, "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.merged())
        log = (self.d / "calls.log").read_text()
        self.assertIn(f"--match-head-commit {sha}", log)  # pinned to the full handed-back sha
        self.assertIn("--repo acme/widgets", log)
        self.assertEqual(self.git("branch", "--list", "lane"), "* lane")  # branch and worktree untouched

    def test_apply_does_not_merge_a_red_check(self):
        r = self.hb(self.lane(), "--apply", status="failure")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(self.merged())

    def refused(self, code, *extra, **kw):
        r = self.hb(self.lane(), "--apply", *extra, **kw)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        self.assertFalse(self.merged())
        return r

    def test_apply_refuses_pending_checks(self):
        self.assertIn("UNVERIFIED", self.refused(3, status="pending").stdout)

    def test_apply_refuses_unreadable_protection(self):
        self.assertIn("UNVERIFIED", self.refused(3, protection=False).stdout)

    def test_apply_refuses_a_failing_gate(self):
        self.assertIn("RED: gate", self.refused(1, gate="false").stdout)

    def test_apply_refuses_a_guard_failure(self):
        self.assertIn("RED: guard", self.refused(1, "--branch", "nope").stdout)

    def test_apply_refuses_a_pr_at_another_head(self):
        self.assertIn("RED: merge:", self.refused(1, pr_head="0" * 40).stdout)

    def test_apply_refuses_without_a_review_receipt_when_enforced(self):
        (self.d / "policy.json").write_text(json.dumps({"review_gate": "enforce"}))
        self.env["PERUN_POLICY"] = str(self.d / "policy.json")
        self.env["REVIEW_DIR"] = str(self.d / "reviews")
        r = self.refused(1)
        self.assertIn("no independent review receipt", r.stdout)

    def test_apply_without_merge_pr_is_a_usage_error(self):
        r = subprocess.run([sys.executable, str(th.SCRIPT), "--sha", self.lane(), "--base", "main", "--branch", "lane",
                            "--gate-cmd", "true", "--apply"], cwd=self.repo, env=self.env, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_apply_refuses_a_pr_for_another_base(self):
        self.assertIn("RED: merge:", self.refused(1, pr_base="release").stdout)

    def test_apply_refuses_a_short_sha(self):
        sha = self.lane()
        r = self.hb(sha[:12], "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertFalse(self.merged())

    def test_failed_merge_is_red(self):
        (self.d / "merge_rc").write_text("1")
        r = self.hb(self.lane(), "--apply")
        self.assertEqual(r.returncode, 1)
        self.assertIn("handback RED: merge:", r.stdout)

    def test_merge_needs_repo(self):
        cmd = [sys.executable, str(th.SCRIPT), "--sha", "x", "--base", "main", "--branch", "lane", "--gate-cmd", "true", "--merge-pr", "7"]
        r = subprocess.run(cmd, cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
