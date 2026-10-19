#!/usr/bin/env python3
"""handback.py: one-command lane last mile. Offline: a throwaway git repo and a stub `gh` on PATH."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".claude/skills/agentic-delivery/scripts/handback.py"
STUB = """#!/bin/sh
echo "$*" >> "$FAKE/calls.log"
case "$*" in
  *required_status_checks*) cat "$FAKE/protection.json" 2>/dev/null || exit 1 ;;
  *check-runs*) cat "$FAKE/checks.json" ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
"""


class T(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.d = Path(self.t.name)
        self.repo = self.d / "repo"
        self.repo.mkdir()
        gh = self.d / "gh"
        gh.write_text(STUB)
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.env = {**os.environ, "PATH": f"{self.d}{os.pathsep}{os.environ['PATH']}", "FAKE": str(self.d),
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "t",
                    "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
        for var in ("GH_TOKEN", "GITHUB_TOKEN"):
            self.env.pop(var, None)
        self.git("init", "-q", "-b", "main")
        self.commit("base.txt", "base\n", "base")

    def tearDown(self):
        self.t.cleanup()

    def git(self, *a):
        return subprocess.run(["git", *a], cwd=self.repo, env=self.env, capture_output=True, text=True, check=True).stdout.strip()

    def commit(self, path, text, msg):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)
        return self.git("rev-parse", "HEAD")

    def lane(self, fragment=True, text="work\n"):
        """Branch `lane` off main with one commit (plus a changelog fragment); returns its sha."""
        self.git("checkout", "-q", "-b", "lane")
        if fragment:
            self.commit("changelog.d/x.md", "### Added\n- x\n", "frag")
        return self.commit("work.txt", text, "work")

    def hb(self, sha, *extra, gate="true", cwd=None):
        cmd = [sys.executable, str(SCRIPT), "--sha", sha, "--base", "main", "--branch", "lane", "--gate-cmd", gate, *extra]
        return subprocess.run(cmd, cwd=cwd or self.repo, env=self.env, capture_output=True, text=True, stdin=subprocess.DEVNULL)

    def test_green_prints_cleanup_and_leaves_branches_alone(self):
        sha = self.lane()
        r = self.hb(sha)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("handback GREEN " + sha[:12], r.stdout)
        self.assertIn("clean_finished.sh", r.stdout)
        self.assertIn("reap_own.sh", r.stdout)
        self.assertEqual(self.git("branch", "--list", "lane"), "* lane")

    def test_red_gate_names_the_gate(self):
        r = self.hb(self.lane(), gate="false")
        self.assertEqual(r.returncode, 1)
        self.assertIn("handback RED: gate: false", r.stdout)

    def test_base_moved_is_not_a_fast_forward(self):
        sha = self.lane()
        self.git("checkout", "-q", "main")
        self.commit("other.txt", "o\n", "other")
        self.git("checkout", "-q", "lane")
        r = self.hb(sha)
        self.assertEqual(r.returncode, 1)
        self.assertIn("handback RED: ff:", r.stdout)

    def test_missing_fragment_is_red_and_skippable(self):
        sha = self.lane(fragment=False)
        r = self.hb(sha)
        self.assertEqual(r.returncode, 1)
        self.assertIn("RED: fragment:", r.stdout)
        self.assertEqual(self.hb(sha, "--fragment-dir", "").returncode, 0)

    def test_whitespace_error_is_red(self):
        r = self.hb(self.lane(text="trailing   \n"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("RED: diff:", r.stdout)

    def test_offline_by_default(self):
        self.hb(self.lane())
        self.assertFalse((self.d / "calls.log").exists())

    def test_required_checks_and_a_failing_run(self):
        sha = self.lane()
        (self.d / "protection.json").write_text(json.dumps({"checks": [{"context": "unit"}]}))

        def runs(conclusion):
            return {"total_count": 1, "check_runs": [{"id": 1, "name": "unit", "status": "completed", "conclusion": conclusion,
                    "head_sha": sha, "completed_at": "2026-01-01T00:00:00Z", "app": {"id": 1}, "check_suite": {"id": 1}}]}
        (self.d / "checks.json").write_text(json.dumps(runs("success")))
        r = self.hb(sha, "--repo", "acme/widgets")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("required checks: unit", r.stdout)
        (self.d / "checks.json").write_text(json.dumps(runs("failure")))
        r = self.hb(sha, "--repo", "acme/widgets")
        self.assertEqual(r.returncode, 1)
        self.assertIn("RED: checks:", r.stdout)

    def test_tracker_post_is_a_dry_run_unless_sent(self):
        sha = self.lane()
        body = self.d / "body.md"
        body.write_text("Lane done; gates green.\n")
        (self.d / "protection.json").write_text("{}")
        (self.d / "checks.json").write_text(json.dumps(self.runs(sha)))
        r = self.hb(sha, "--repo", "acme/widgets", "--tracker-issue", "7", "--agent", "lane-a", "--to", "owner", "--body-file", str(body))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("gh issue comment 7 --repo acme/widgets", r.stdout)
        self.assertNotIn("issue comment", (self.d / "calls.log").read_text())  # composed, not sent

    def runs(self, sha, name="unit", status="completed", conclusion="success"):
        return {"total_count": 1, "check_runs": [{"id": 1, "name": name, "status": status, "conclusion": conclusion,
                "head_sha": sha, "completed_at": "2026-01-01T00:00:00Z", "app": {"id": 1}, "check_suite": {"id": 1}}]}

    def unverified(self, sha, checks):
        (self.d / "protection.json").write_text(json.dumps({"checks": [{"context": "unit"}]}))
        (self.d / "checks.json").write_text(checks if isinstance(checks, str) else json.dumps(checks))
        r = self.hb(sha, "--repo", "acme/widgets")
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn("handback UNVERIFIED: 1 checks could not run", r.stdout)
        self.assertNotIn("GREEN", r.stdout)
        self.assertIn("ok: gates", r.stdout)  # the offline steps still passed; only the forge verdict is open

    def test_pending_check_is_unverified_not_green(self):
        sha = self.lane()
        self.unverified(sha, self.runs(sha, status="in_progress", conclusion=None))

    def test_no_run_check_is_unverified_not_green(self):
        sha = self.lane()
        self.unverified(sha, self.runs(sha, name="other"))

    def test_unreadable_checks_are_unverified_not_green(self):
        self.unverified(self.lane(), "not json")

    def test_red_gate_shows_its_stdout(self):
        r = self.hb(self.lane(), gate="echo gate-said-boom; exit 1")
        self.assertIn("gate-said-boom", r.stdout)
        self.assertIn("handback RED: gate:", r.stdout)

    def test_gate_and_git_steps_run_in_the_worktree(self):
        sha = self.lane()
        r = self.hb(sha, "--worktree", str(self.repo), gate='pwd > "$FAKE/pwd.txt"', cwd=self.d)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(os.path.realpath((self.d / "pwd.txt").read_text().strip()), os.path.realpath(self.repo))

    def test_gate_cache_is_pinned_to_the_handed_back_tree(self):
        sha = self.lane()
        gate = 'echo x >> "$FAKE/ran.log"'
        self.hb(sha, gate=gate)
        self.hb(sha, gate=gate)
        self.assertEqual(len((self.d / "ran.log").read_text().split()), 1)  # same tree: second run is cached
        self.git("checkout", "-q", "main")  # checkout no longer matches --sha: never reuse or store a PASS for it
        self.hb(sha, gate=gate)
        self.hb(sha, gate=gate)
        self.assertEqual(len((self.d / "ran.log").read_text().split()), 3)

    def test_tracker_needs_its_arguments(self):
        r = self.hb(self.lane(), "--tracker-issue", "7")
        self.assertEqual(r.returncode, 2)

    def test_script_never_runs_teardown_or_pushes(self):
        src = SCRIPT.read_text()
        for banned in ("git worktree remove", '"push"', "rm -rf"):
            self.assertNotIn(banned, src)
        code = src.split('"""', 2)[2]  # past the docstring
        for line in code.splitlines():
            if "clean_finished.sh" in line or "reap_own.sh" in line:
                self.assertTrue(line.lstrip().startswith("print("), line)  # named only to be printed


if __name__ == "__main__":
    unittest.main()
