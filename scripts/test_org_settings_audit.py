#!/usr/bin/env python3
"""Offline tests for org_settings_audit.py: org checks pass, fail and 403 (never a pass), per-repo reuse, and the curl
getter end to end against a stub `curl` on PATH (token on stdin only, never argv). Fictional acme org, no network."""
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
import org_settings_audit as osa  # noqa: E402

O = "/orgs/acme"
FORBIDDEN = OSError("Resource not accessible by personal access token (HTTP 403)")
GOOD = {O: {"two_factor_requirement_enabled": True},
        O + "/actions/permissions/workflow": {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False},
        O + "/actions/permissions": {"enabled_repositories": "all", "allowed_actions": "selected"},
        O + "/installations": {"installations": [{"permissions": {"issues": "write"}}]},
        O + "/outside_collaborators": [], O + "/actions/runners": {"runners": []}, O + "/repos": []}


def fake(**over):
    d = dict(GOOD, **over)

    def get(path, params=None):
        v = d.get(path, FORBIDDEN)
        if isinstance(v, Exception):
            raise v
        return v
    return get


def checks(rows):
    return {r["check"]: r["severity"] for r in rows}


def deny(path, params=None):
    raise FORBIDDEN


class T(unittest.TestCase):
    def test_pass(self):
        org, repos = osa.audit("acme", fake())
        self.assertEqual({r["severity"] for r in org}, {"info"})
        self.assertEqual(repos, {})

    def test_fail(self):
        bad = {O: {"two_factor_requirement_enabled": False},
               O + "/actions/permissions/workflow": {"default_workflow_permissions": "write", "can_approve_pull_request_reviews": True},
               O + "/actions/permissions": {"enabled_repositories": "all", "allowed_actions": "all"},
               O + "/outside_collaborators": [{"login": "jane"}], O + "/actions/runners": {"runners": [{"id": 1}]}}
        org, _ = osa.audit("acme", fake(**bad))
        c = checks(org)
        self.assertEqual(c["2FA requirement is off"], "high")
        self.assertEqual(c["org default workflow token can write"], "medium")
        self.assertEqual(c["org allows all actions"], "medium")
        self.assertEqual(c["1 outside collaborator(s)"], "low")
        self.assertEqual(c["1 org self-hosted runner(s)"], "medium")
        self.assertEqual(org[0]["severity"], "high")

    def test_403_is_not_checked_with_scope(self):
        org, _ = osa.audit("acme", deny)
        self.assertEqual(len(org), 2)  # org unreadable + repo list unreadable
        self.assertTrue(all(r["severity"] == "not-checked" and "token that has" in r["fix"] for r in org))
        org, _ = osa.audit("acme", fake(**{O: {"login": "acme"}, O + "/actions/runners": FORBIDDEN}))
        c = checks(org)
        self.assertEqual(c["2FA requirement: not checked (needs owner access (admin:org))"], "not-checked")
        self.assertIn("self-hosted runners: not checked (needs admin:org (fine-grained: Self-hosted runners read))", c)
        self.assertFalse(any(r["severity"] == "info" and "2FA" in r["check"] for r in org))

    def test_repos_reuse_and_cap(self):
        g = fake(**{O + "/repos": [{"full_name": "acme/a"}, {"full_name": "acme/b"}]})
        org, repos = osa.audit("acme", g, max_repos=1)
        self.assertEqual(list(repos), ["acme/a"])
        self.assertTrue(any("capped at 1" in r["check"] for r in org))
        self.assertEqual(repos["acme/a"][0]["severity"], "not-checked")  # repo read 403, not a pass

    def test_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(osa.main(["acme", "--json"], get=fake()), 0)
        self.assertEqual(json.loads(out.getvalue())["summary"], {"repos": 0, "findings": 0, "not_checked": 0})
        self.assertEqual(osa.main(["bad/org"], get=fake()), 2)

    def test_curl_stub(self):
        with tempfile.TemporaryDirectory() as t:
            stub = Path(t, "curl")
            stub.write_text('#!/bin/sh\necho "$@" >> "$STUB_LOG"\ncat >> "$STUB_LOG"\n'
                            'printf \'{"message":"Resource not accessible"}\\n403\'\n')
            stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
            env = {"PATH": t + os.pathsep + os.environ["PATH"], "STUB_LOG": str(Path(t, "log")), "TOK": "ghp_fake0123456789"}
            out = io.StringIO()
            with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(out):
                self.assertEqual(osa.main(["acme", "--token-env", "TOK", "--json"]), 0)
            log = Path(t, "log").read_text()
            argv_lines = [ln for ln in log.splitlines() if ln.startswith("-sS")]
            self.assertTrue(argv_lines and not any("ghp_fake" in ln for ln in argv_lines))
            self.assertIn("Authorization: Bearer ghp_fake0123456789", log)  # arrived on stdin
            summ = json.loads(out.getvalue())["summary"]
            self.assertEqual(summ["findings"], 0)
            self.assertGreater(summ["not_checked"], 0)


if __name__ == "__main__":
    unittest.main()
