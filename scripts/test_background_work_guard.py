#!/usr/bin/env python3
"""Tests for the background-work guard in handback_cap.py (SubagentStop): a lane that hands back while a test or build
started from its worktree is still running gets a warning (default) or a block (policy/env `block`).

The process list is injected, so the matching, exclusion and mode logic are deterministic; one live-process case uses a
real child and skips itself when this host cannot scan cwds (no lsof, no /proc).
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
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
import handback_cap as hc  # noqa: E402
import perun_policy as pp  # noqa: E402

ME = 500
# pid -> (ppid, command): 100 host (ancestor of the hook), 500 the hook, 501 its ps child, 200/201/202/203 lane jobs
TABLE = {
    100: (1, "claude --agent lane"),
    ME: (100, "python3 handback_cap.py"),
    501: (ME, "ps -axo pid=,ppid=,command= pytest"),
    200: (100, "/venv/bin/python -m pytest -x tests/"),
    201: (100, "node vite --port 5173"),
    202: (100, "npm run dev"),
    203: (100, "npm test"),
    204: (100, "vim notes.txt"),
}


def run_check(data, mode, bg, env=None):
    """check() with the scan stubbed; returns (rc, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with tempfile.TemporaryDirectory() as st, mock.patch.object(hc, "STATE_DIR", st), \
            mock.patch.dict(os.environ, {"PERUN_BACKGROUND_GUARD": mode, "HANDBACK_AUDIT_LEDGER": "off", **(env or {})}), \
            mock.patch.object(hc, "_push_running", lambda cwd: False), \
            mock.patch.object(hc, "_bg_running", bg), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = hc.check({"agent_id": "L1", "cwd": "/w", "last_assistant_message": "status=VERIFIED", **data})
    return rc, out.getvalue(), err.getvalue()


class Matching(unittest.TestCase):
    def test_finds_test_and_build_runners_only(self):
        found = hc._bg_found(TABLE, {200, 201, 202, 203, 204}, ME)
        self.assertEqual([p for p, _ in found], [200, 203])

    def test_excludes_own_ancestors_and_descendants(self):
        self.assertEqual(hc._bg_found(TABLE, {100, ME, 501}, ME), [])

    def test_pid_missing_from_table_is_ignored(self):
        self.assertEqual(hc._bg_found(TABLE, {999}, ME), [])

    def test_ancestor_cycle_terminates(self):
        self.assertEqual(hc._bg_found({1: (2, "a"), 2: (1, "b"), ME: (1, "x")}, {1}, ME), [])

    def test_ps_output_parses_and_skips_junk(self):
        text = "    1     0 /sbin/launchd\n  812   400 python3 -m pytest -x\nbad line\n  x  1 y\n"
        self.assertEqual(hc._ps_table(text), {1: (0, "/sbin/launchd"), 812: (400, "python3 -m pytest -x")})

    def test_runner_regex(self):
        for cmd in ("pytest", "cargo test", "go build ./...", "yarn build", "bash scripts/test_x.sh", "python3 -m unittest"):
            self.assertTrue(hc.BG_RE.search(cmd), cmd)
        for cmd in ("npm run dev", "next dev", "vim latest.txt", "cargo run", "git status"):
            self.assertIsNone(hc.BG_RE.search(cmd), cmd)


class Modes(unittest.TestCase):
    LIVE = staticmethod(lambda cwd: [(200, "pytest -x tests/")])

    def test_warn_names_pid_and_command_and_does_not_block(self):
        rc, out, _ = run_check({}, "warn", self.LIVE)
        self.assertEqual(rc, 0)
        msg = json.loads(out)["systemMessage"]
        self.assertIn("pid 200", msg)
        self.assertIn("pytest -x tests/", msg)

    def test_block_exits_2_naming_pid_and_command(self):
        rc, out, err = run_check({}, "block", self.LIVE)
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn("pid 200", err)
        self.assertIn("pytest -x tests/", err)

    def test_block_releases_after_max_age(self):
        with tempfile.TemporaryDirectory() as st, mock.patch.object(hc, "STATE_DIR", st), \
                mock.patch.dict(os.environ, {"PERUN_BACKGROUND_GUARD": "block", "HANDBACK_AUDIT_LEDGER": "off"}), \
                mock.patch.object(hc, "_push_running", lambda cwd: False), \
                mock.patch.object(hc, "_bg_running", self.LIVE), contextlib.redirect_stderr(io.StringIO()):
            d = {"agent_id": "L2", "cwd": "/w", "last_assistant_message": "status=VERIFIED"}
            self.assertEqual(hc.check(d), 2)
            self.assertEqual(hc.check(d), 2)
            os.utime(hc._state_path("L2") + ".bg", (0, 0))
            self.assertEqual(hc.check(d), 0)

    def test_off_never_scans(self):
        def boom(cwd):
            raise AssertionError("scanned")
        self.assertEqual(run_check({}, "off", boom)[0], 0)

    def test_nothing_running_is_silent(self):
        self.assertEqual(run_check({}, "block", lambda cwd: []), (0, "", ""))

    def test_blind_scan_fails_open_and_says_so(self):
        rc, out, err = run_check({}, "block", lambda cwd: None)
        self.assertEqual((rc, out), (0, ""))
        self.assertIn("COULD_NOT_CHECK", err)

    def test_exempt_agent_type_skips(self):
        self.assertEqual(run_check({"agent_type": "Explore"}, "block", self.LIVE)[0], 0)

    def test_many_matches_are_capped_in_the_message(self):
        rc, out, _ = run_check({}, "warn", lambda cwd: [(i, "make") for i in range(1, 6)])
        self.assertIn("+2 more", json.loads(out)["systemMessage"])


class ModeSource(unittest.TestCase):
    def test_policy_key_validates_and_defaults_to_warn(self):
        self.assertEqual(pp.validate({})["background_guard"], "warn")
        self.assertEqual(pp.validate({"background_guard": "block"})["background_guard"], "block")
        with self.assertRaises(ValueError):
            pp.validate({"background_guard": "kill"})

    def test_env_overrides_policy_and_bad_env_is_ignored(self):
        with mock.patch.dict(os.environ, {"PERUN_BACKGROUND_GUARD": "off"}):
            self.assertEqual(hc._bg_mode(), "off")
        with tempfile.TemporaryDirectory() as d:
            pol = Path(d) / "policy.json"
            pol.write_text('{"background_guard": "block"}')
            with mock.patch.dict(os.environ, {"PERUN_BACKGROUND_GUARD": "bogus", "PERUN_POLICY": str(pol)}):
                self.assertEqual(hc._bg_mode(), "block")
            with mock.patch.dict(os.environ, {"PERUN_BACKGROUND_GUARD": "", "PERUN_POLICY": str(Path(d) / "missing.json")}):
                self.assertEqual(hc._bg_mode(), "warn")  # unreadable policy fails open to the default


class Scan(unittest.TestCase):
    def test_non_worktree_cwd_reports_none_running(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".git").mkdir()  # a shared checkout: .git is a directory
            self.assertEqual(hc._bg_running(d), [])

    def test_missing_cwd_is_could_not_check(self):
        self.assertIsNone(hc._bg_running(""))
        self.assertIsNone(hc._bg_running("/nonexistent-dir-xyz"))

    def test_live_runner_in_a_linked_worktree_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".git").write_text("gitdir: /elsewhere\n")  # a linked worktree has a .git FILE
            sub = Path(d) / "pkg"
            sub.mkdir()
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)", "pytest"], cwd=d)
            try:
                got = hc._bg_running(str(sub))
                if got is None:
                    self.skipTest("host cannot scan process cwds (no lsof, no /proc)")
                self.assertIn(child.pid, [p for p, _ in got])
            finally:
                child.kill()
                child.wait()
            self.assertNotIn(child.pid, [p for p, _ in (hc._bg_running(d) or [])])


if __name__ == "__main__":
    unittest.main()
