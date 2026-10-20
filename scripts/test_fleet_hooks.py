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

    def test_narrow_pytest_not_heavy(self):
        for c in ["pytest -q tests/a.py", "pytest tests/a.py tests/b.py", "pytest tests/a.py::t", "pytest -k foo",
                  "pytest -k foo tests", "uv run pytest -x tests/a.py", "python -m pytest tests/a.py -k foo"]:
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_wide_pytest_still_heavy(self):
        for c in ["pytest", "pytest tests", "pytest -q", "pytest a.py b.py c.py", "pytest tests/a.py tests", "pytest --tb short tests/a.py tests/b.py"]:
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_command_after_heredoc_still_heavy(self):
        self.assertTrue(hg.is_heavy("cat <<EOF\nx\nEOF\npytest", hg.DEFAULT_PATTERNS))

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
