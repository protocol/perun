#!/usr/bin/env python3
"""Offline tests for heavy_gate.is_heavy (quote/heredoc/wrapper/light handling) and session_brief (lsof stub, time budget)."""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude/skills/agentic-delivery/scripts"))
import heavy_gate as hg  # noqa: E402
import session_brief as sb  # noqa: E402

HEAVY = [
    "pytest -q", "cd x && npm test", "echo x; (npm run build)", "a\npytest", "pytest -q 2>&1 | tail",
    "uv run pytest", "uv run --quiet pytest -q", "poetry run pytest", "pipx run pytest", "npx -y vitest",
    "pnpm exec jest", "env -i FOO=1 pytest", "FOO=1 python3 -m pytest", "python -m pytest", "npx playwright test",
    "time nice pytest",
]
NOT_HEAVY = [
    'git commit -m "fix; pytest flake"', "git commit -m 'a && npm test'",
    "git commit -F - <<'EOF'\nfix\n\npytest config\nnpm test\nEOF",
    "git commit -F - <<EOF\npytest config\nEOF\ngit status",
    "pytest --version", "pytest --help", "pytest --collect-only", "npm test --help", "jest --version",
    "playwright install", "npx playwright install chromium", "npx playwright install-deps",
    "git commit -m 'unclosed pytest", "grep jest x", "python -m http.server",
]


class IsHeavy(unittest.TestCase):
    def test_heavy(self):
        for c in HEAVY:
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_not_heavy(self):
        for c in NOT_HEAVY:
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_command_after_heredoc_still_heavy(self):
        self.assertTrue(hg.is_heavy("cat <<EOF\nx\nEOF\npytest", hg.DEFAULT_PATTERNS))

    def test_scoped_pytest_is_light(self):
        """The hold message advises a narrower run, so 1-2 files must pass while the full suite stays held (#1829)."""
        for c in ("pytest -q tests/test_one.py", "python3 -m pytest a.py b.py::t", "uv run pytest -q a.py -k name",
                  "pytest -k x.py a.py", "pytest -W ignore a.py", "pytest --cov pkg a.py", "pytest -r fE a.py",
                  "pytest --tb=short -x a.py", "pytest -o x=y a.py", "pytest --junitxml=out.xml a.py",
                  "pytest --cov-report term a.py", "pytest -kfoo a.py", "pytest a.py::t[1]","pytest -p no:cacheprovider a.py",
                  "pytest -W ignore::Warning a.py", "pytest -k a:b a.py","pytest a.py::Cls::test_x"):
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)
        for c in ("pytest -q", "pytest a.py b.py c.py", "pytest tests/", "pytest --ignore=a.py --ignore=b.py",
                  "pytest tests/ a.py", "pytest -k name", "pytest --ignore a.py --ignore b.py", "pytest --ignore x.py a.py",
                  "pytest --log-file out.py", "pytest -W x.py", "pytest --cache-dir out.py", "pytest --bogus a.py",
                  "pytest tests/*.py", "pytest *.py", "pytest tests/test_{a..z}.py", "pytest a.py:: tests/", "pytest a.py $X",
                  "pytest a.py `ls`", "pytest a.py::", "pytest -k x:: tests/ a.py",
                  "pytest a.py -k a: tests", "pytest a.py -p no: tests", "pytest a.py:: tests"):
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_wrapped_runs_are_unwrapped(self):
        """timeout/nohup/env/nice/time/stdbuf/xargs and `sh -c 'STRING'` must not hide a heavy run (#1840)."""
        for c in ("timeout 600 pytest", "timeout -s KILL 5m npm test", "nohup npm test &", "env -u FOO pytest",
                  "env X=1 pytest", "nice -n 5 pytest", "nice pytest", "time go test ./...", "stdbuf -oL pytest",
                  "xargs pytest", "find . -name '*.py' | xargs -n 1 pytest", 'bash -c "pytest"', "sh -c 'cd x && npm test'",
                  'bash -lc "cargo test"', '/bin/bash -c "go test ./..."', "bash -c 'echo \"x'",
                  "xargs -I{} pytest {}", "xargs -I {} npm test", "timeout 5 -- pytest", "/usr/bin/env pytest",
                  "/usr/bin/timeout 5 pytest", "/usr/bin/python3 -m pytest", "bash -O extglob -c pytest",
                  "bash -o pipefail -c pytest", "bash --rcfile F -c pytest", "bash +x -c pytest", "fish -c pytest",
                  "sudo -u root pytest", "sudo -u bob timeout 5 pytest", "exec -a x pytest", "time -f %e pytest",
                  "uv run --with x pytest", "setsid npm test"):
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)
        for c in ("timeout 5 ls", "nohup ./server &", "nice -n 5 make", "xargs rm", 'bash -c "echo hi"', "bash script.sh",
                  "timeout 5 pytest a.py", 'bash -c "pytest a.py"', 'git commit -m "bash -c pytest"', "echo timeout 5 pytest",
                  "xargs -I{} rm {}", "sudo -u root ls", "date +%s", "bash +x script.sh", "pytest -k a+b a.py"):
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_custom_pattern(self):
        self.assertTrue(hg.is_heavy("make check", [r"make check\b"]))


class SessionBrief(unittest.TestCase):
    def setUp(self):
        sb._deadline[0] = float("inf")  # a prior brief() leaves its deadline set

    def stub_lsof(self, d, cwd):
        f = Path(d) / "lsof"
        f.write_text('#!/bin/sh\ncase "$*" in *-iTCP*) printf "p4242\\n";; *) printf "p4242\\nn%s\\n";; esac\n' % cwd)
        f.chmod(f.stat().st_mode | stat.S_IXUSR)

    def test_dev_servers_stubbed_lsof(self):
        with tempfile.TemporaryDirectory() as d:
            self.stub_lsof(d, "/w/repo/sub")
            old, os.environ["PATH"] = os.environ["PATH"], d + os.pathsep + os.environ["PATH"]
            try:
                self.assertEqual(sb.dev_servers(["/w/repo"]), ["4242"])
                self.assertEqual(sb.dev_servers(["/w/other"]), [])
            finally:
                os.environ["PATH"] = old

    def test_dev_servers_lsof_missing(self):
        old, os.environ["PATH"] = os.environ["PATH"], "/nonexistent"
        try:
            self.assertIsNone(sb.dev_servers(["/w"]))
        finally:
            os.environ["PATH"] = old

    def test_budget_spent_skips_everything(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "PRIORITIES.md").write_text("1. #1 Do it\n")
            self.assertTrue(sb.brief(Path(d)))
            old, sb.BUDGET = sb.BUDGET, 0
            try:
                self.assertEqual(sb.brief(Path(d)), [])
                self.assertIsNone(sb._git(d, "status"))
            finally:
                sb.BUDGET = old


if __name__ == "__main__":
    unittest.main()
