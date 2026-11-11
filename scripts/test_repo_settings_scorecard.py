#!/usr/bin/env python3
"""Offline tests for the `--scorecard` row of repo_settings_audit.py: a public repository gets an info row with the
aggregate score (stored in the --json rows), a private one, a reply with no `private` field, a missing `scorecard`
binary and a failed, non-numeric or negative-score run are `not checked` rows (never blank, never a score), and without
the flag no scorecard row appears. A stub `scorecard` binary on PATH covers the real subprocess call. Synthetic data
only (fictional acme/widgets), no network."""
import contextlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude/skills/agentic-delivery/scripts"))
import repo_settings_audit as rsa  # noqa: E402

SLUG = "acme/widgets"


def get_for(private):
    """A fake `get`: the repository reply carries `private`; every other endpoint is a 404 (those rows are not under test)."""
    def get(path, params=None):
        if path == "/repos/" + SLUG:
            return {"name": "widgets", "permissions": {"admin": False}} | ({} if private is None else {"private": private})
        raise OSError("Not Found (HTTP 404)")
    return get


def sc_rows(private, run):
    return [r for r in rsa.audit(SLUG, get_for(private), run) if r["check"].startswith("scorecard")]


class ScorecardRow(unittest.TestCase):
    def test_public_repo_gets_score_row(self):
        (r,) = sc_rows(False, lambda s: (7.3, None))
        self.assertEqual((r["check"], r["severity"]), ("scorecard: aggregate score 7.3/10", "info"))
        self.assertIn("github.com/" + SLUG, r["fix"])

    def test_private_repo_is_not_checked(self):
        called = []
        (r,) = sc_rows(True, lambda s: called.append(s))
        self.assertEqual((r["check"], r["severity"]), ("scorecard: not checked (private repository)", "not-checked"))
        self.assertEqual(called, [])

    def test_missing_private_field_is_not_checked(self):
        (r,) = sc_rows(None, lambda s: (1, None))
        self.assertEqual(r["severity"], "not-checked")

    def test_failed_run_is_not_checked(self):
        (r,) = sc_rows(False, lambda s: (None, ("scorecard run failed", "x")))
        self.assertEqual(r["check"], "scorecard: not checked (scorecard run failed)")

    def test_no_flag_no_row(self):
        self.assertEqual([r for r in rsa.audit(SLUG, get_for(False)) if "scorecard" in r["check"]], [])


class RunScorecard(unittest.TestCase):
    def stub(self, body):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        d = td.name
        p = os.path.join(d, "scorecard")
        Path(p).write_text("#!/bin/sh\n" + body + "\n")
        os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
        return mock.patch.dict(os.environ, {"PATH": d + os.pathsep + os.path.dirname(sys.executable)})

    def test_reads_top_level_score_and_passes_repo(self):
        with self.stub('echo "$@" >"$0.args"; echo \'{"score": 6.5, "checks": []}\''):
            self.assertEqual(rsa.run_scorecard(SLUG), (6.5, None))
            args = Path(os.environ["PATH"].split(os.pathsep)[0], "scorecard.args").read_text().strip()
        self.assertEqual(args, "--repo=github.com/acme/widgets --format=json")

    def test_bad_runs_are_errors(self):
        for body in ("exit 1", "echo '{\"score\": 5}'; exit 2", "echo not-json", "echo '{}'", "echo '{\"score\": -1}'", "echo '{\"score\": true}'", "echo '{\"score\": \"7\"}'"):
            with self.stub(body):
                score, e = rsa.run_scorecard(SLUG)
                self.assertIsNone(score, body)
                self.assertEqual(e[0], "scorecard run failed", body)

    def test_not_installed(self):
        with mock.patch.dict(os.environ, {"PATH": tempfile.gettempdir() + "/none-" + str(os.getpid())}):
            score, e = rsa.run_scorecard(SLUG)
        self.assertEqual((score, e[0]), (None, "scorecard not installed"))


class Cli(unittest.TestCase):
    def test_flag_stores_rows_in_json(self):
        out = io.StringIO()
        with mock.patch.object(rsa, "run_scorecard", lambda s: (8, None)), contextlib.redirect_stdout(out):
            self.assertEqual(rsa.main([SLUG, "--json", "--scorecard"], get_for(False)), 0)
        self.assertIn({"repo": SLUG, "check": "scorecard: aggregate score 8/10", "severity": "info",
                       "fix": "run `scorecard --repo=github.com/acme/widgets` for the per-check breakdown"}, json.loads(out.getvalue())["rows"])


if __name__ == "__main__":
    unittest.main()
