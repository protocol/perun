#!/usr/bin/env python3
"""Tests for premise_check.py: MERGED/CLOSED/OPEN per number and absent-at-HEAD flags for a cited path or symbol.

`gh` is stubbed (no network); the "HEAD" is a throwaway git repo in a temp dir. Run: python3 scripts/test_premise_check.py
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SC = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SC))
import premise_check as pc  # noqa: E402

DOCS = {
    1: {"state": "closed", "pull_request": {"merged_at": "2026-10-01T00:00:00Z"}},
    2: {"state": "closed", "pull_request": {"merged_at": None}},
    3: {"state": "open", "pull_request": {"merged_at": None}},
    4: {"state": "open", "body": "Fix `src/a.py` and `real_fn()`; see `docs/` and --flag."},
    5: {"state": "open", "body": "Fix `src/gone.py`, `gone_fn()`, `real_fn()` and `src/a.py`."},
    6: {"state": "closed", "body": "old"},
    7: {"state": "open", "body": "See `a.py`, `src/a.py.` and `real_fn()`."},
}


def fake_gh(args, timeout):
    n = int(args[-1].rsplit("/", 1)[1])
    if n == 8:
        return 1, json.dumps(DOCS[3]), "rate limited"
    return (0, json.dumps(DOCS[n]), "") if n in DOCS else (1, "", "not found")


class PremiseCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        r = self.root = self.tmp.name
        (Path(r) / "src").mkdir()
        (Path(r) / "docs").mkdir()
        (Path(r) / "src/a.py").write_text("def real_fn(x):\n    pass\n")
        (Path(r) / "docs/x.md").write_text("x\n")
        for cmd in (["init", "-q"], ["add", "."], ["-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "i"]):
            subprocess.run(["git", "-C", r, *cmd], check=True, capture_output=True)
        self.old = pc.sc._gh
        pc.sc._gh = fake_gh
        self.addCleanup(setattr, pc.sc, "_gh", self.old)

    def line(self, n):
        return pc.line("o/r", n, self.root, 5)

    def test_pr_states(self):
        self.assertEqual(self.line(1), ("#1 PR MERGED", True))
        self.assertEqual(self.line(2), ("#2 PR CLOSED", True))
        self.assertEqual(self.line(3), ("#3 PR OPEN", False))

    def test_issue_premise_present(self):
        self.assertEqual(self.line(4), ("#4 ISSUE OPEN", False))

    def test_issue_premise_absent(self):
        self.assertEqual(self.line(5), ("#5 ISSUE OPEN; absent at HEAD: src/gone.py, gone_fn()", True))

    def test_closed_issue_and_unreadable(self):
        self.assertEqual(self.line(6), ("#6 ISSUE CLOSED", True))
        self.assertEqual(self.line(99), ("#99 UNREADABLE", True))
        self.assertEqual(self.line(8), ("#8 UNREADABLE", True))  # gh failed even though its output parses

    def test_bare_name_trailing_punctuation_and_call_suffix(self):
        self.assertEqual(self.line(7), ("#7 ISSUE OPEN", False))

    def test_other_repo_skips_head_check(self):
        self.assertEqual(pc.line("o/r", 5, None, 5), ("#5 ISSUE OPEN", False))

    def test_main_exit_codes(self):
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.root)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(pc.main(["--repo", "o/r", "3", "4"]), 0)
            self.assertEqual(pc.main(["--repo", "o/r", "3", "1"]), 1)
        self.assertEqual(out.getvalue(), "#3 PR OPEN\n#4 ISSUE OPEN\n#3 PR OPEN\n#1 PR MERGED\n")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pc.main(["--repo", "bad", "3"]), 3)
            self.assertEqual(pc.main(["x"]), 3)


if __name__ == "__main__":
    unittest.main()
