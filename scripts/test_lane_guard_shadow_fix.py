#!/usr/bin/env python3
"""lane_guard.py shadow-fix refuses Fixes/Closes/Resolves #N when the diff adds a default-off flag."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"))
import lane_guard  # noqa: E402


def git(cwd, *a):
    subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
                    "-c", "core.hooksPath=" + os.devnull, *a], check=True, capture_output=True)


class ShadowFix(unittest.TestCase):
    def run_case(self, line, body, name="a.sh"):
        with tempfile.TemporaryDirectory() as d:
            d = os.path.realpath(d)
            git(d, "init", "-q", "-b", "main")
            Path(d, "a.sh").write_text("echo hi\n")
            git(d, "add", "."), git(d, "commit", "-qm", "seed")
            git(d, "checkout", "-qb", "fix")
            Path(d, name).parent.mkdir(parents=True, exist_ok=True)
            Path(d, name).write_text("echo hi\n" + line + "\n")
            git(d, "add", "."), git(d, "commit", "-qm", "fix")
            return lane_guard.check_shadow_fix(d, "main", "fix", body)[0]

    def test_refuses_default_off_with_closer(self):
        for line in ('[ "${GUARD_ENFORCE:-0}" = 1 ] && x', 'v = os.environ.get("GUARD", "false")', 'GUARD_SHADOW=off'):
            for body in ("Fixes #12", "closes org/repo#12", "Resolves: #12", "Fixes https://github.com/acme/widgets/issues/12", "Fixes https://ghe.example.com/acme/widgets/issues/12"):
                self.assertEqual(self.run_case(line, body), lane_guard.REFUSED, (line, body))

    def test_allows_refs_or_default_on(self):
        self.assertEqual(self.run_case('[ "${G:-0}" = 1 ]', "Refs #12\n- [ ] flip"), lane_guard.OK)
        self.assertEqual(self.run_case('[ "${G:-1}" = 1 ]', "Fixes #12"), lane_guard.OK)

    def test_pipeline_path_needs_two_prod_logs(self):
        w = ".github/workflows/ci.yml"
        logs = "production run: https://example.com/runs/1\nproduction run: https://example.com/runs/2"
        self.assertEqual(self.run_case("x: 1", "Fixes #12", w), lane_guard.REFUSED)
        self.assertEqual(self.run_case("x: 1", "Fixes #12\n" + logs.split("\n")[0], w), lane_guard.REFUSED)
        self.assertEqual(self.run_case("x: 1", "Fixes #12\n" + logs, w), lane_guard.OK)
        self.assertEqual(self.run_case("x: 1", "Refs #12", w), lane_guard.OK)

    def test_two_distinct_prod_runs_pass_flag_hit_too(self):
        one = "production run: https://example.com/runs/1"
        two = one + "\nproduction run: https://example.com/runs/2"
        flag = '[ "${G:-0}" = 1 ]'
        self.assertEqual(self.run_case(flag, "Fixes #12\n" + two), lane_guard.OK)
        self.assertEqual(self.run_case(flag, "Fixes #12\n" + one + "\n" + one), lane_guard.REFUSED)

    def test_git_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d, "git")
            fake.write_text('#!/bin/sh\ncase "$*" in *name-only*) exit 1;; *) exit 0;; esac\n')
            fake.chmod(0o755)
            self.assertEqual(lane_guard.check_shadow_fix(d, "a", "b", "Fixes #1", git=str(fake))[0], lane_guard.COULD_NOT_CHECK)


if __name__ == "__main__":
    unittest.main()
