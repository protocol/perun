"""flake_holder.py: names the open PR holding a flaky test's file; warn-only; silent when not a flake fix."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/flake_holder.py"
PRS = [{"number": 7, "headRefName": "other", "files": [{"path": "tests/test_a.py"}]},
       {"number": 8, "headRefName": "mine", "files": [{"path": "tests/test_a.py"}]}]


class T(unittest.TestCase):
    def repo(self, subject):
        d = tempfile.mkdtemp()
        g = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)  # noqa: E731
        g("init", "-b", "mine")
        g("config", "user.email", "a@example.com")
        g("config", "user.name", "A")
        g("commit", "--allow-empty", "-m", "base")
        os.makedirs(f"{d}/tests")
        pathlib.Path(f"{d}/tests/test_a.py").write_text("x\n")
        g("add", ".")
        g("commit", "-m", subject)
        return d

    def run_(self, d, gh_out, rc=0):
        gh = pathlib.Path(d, "gh.sh")  # inside the repo dir but untracked: fine for a read-only diff
        gh.write_text(f"#!/bin/sh\necho \"$*\" > {d}/args.txt\ncat <<'EOF'\n{gh_out}\nEOF\nexit {rc}\n")
        gh.chmod(0o755)
        r = subprocess.run([sys.executable, str(SCRIPT), "HEAD~1", "HEAD"], cwd=d, capture_output=True, text=True,
                           env={**os.environ, "PERUN_GH": str(gh)})
        return r

    def test_names_holder_and_skips_own_branch(self):
        r = self.run_(self.repo("fix flaky test_a"), json.dumps(PRS))
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout.count("WARN"), 1)
        self.assertIn("tests/test_a.py is also changed by open PR #7 (other)", r.stdout)

    def test_pr_list_limit_is_1000_not_100(self):
        d = self.repo("fix flaky test_a")
        self.run_(d, "[]")
        self.assertIn("--limit 1000", pathlib.Path(d, "args.txt").read_text())

    def test_silent_when_not_a_flake_fix(self):
        self.assertEqual(self.run_(self.repo("add feature"), json.dumps(PRS)).stdout, "")

    def test_fail_open_on_gh_error_or_garbage(self):
        d = self.repo("deflake it: flakiness")
        self.assertEqual((self.run_(d, "", 1).returncode, self.run_(d, "", 1).stdout), (0, ""))
        self.assertEqual((self.run_(d, "not json").returncode, self.run_(d, "not json").stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
