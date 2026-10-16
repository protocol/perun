#!/usr/bin/env python3
"""Offline tests: always-on host rules, heavy_gate 3-deny bypass, operating-layer template has no MODEL_FORCE."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
TPL = ROOT / ".claude/skills/agentic-delivery/templates/operating-layer.settings.json"
sys.path.insert(0, str(SC))
from subagent_start_inject import HOST_RULES, LANE_RULES  # noqa: E402


def run(script, payload, **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("PERUN_", "HOUSE_"))}
    e.update(env)
    r = subprocess.run([sys.executable, str(SC / script)], input=json.dumps(payload), capture_output=True, text=True, env=e)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else {}


class HostRules(unittest.TestCase):
    def test_rules_short_and_specific(self):
        self.assertLessEqual(len(HOST_RULES.splitlines()), 3)
        self.assertIn("sleep N", HOST_RULES)
        self.assertIn("cd X &&", HOST_RULES)

    def test_subagent_start_without_house_file(self):
        o = run("subagent_start_inject.py", {"hook_event_name": "SubagentStart", "agent_type": "x"})
        self.assertEqual(o["hookSpecificOutput"]["additionalContext"], LANE_RULES + "\n" + HOST_RULES)

    def test_session_brief_always_injects(self):
        with tempfile.TemporaryDirectory() as d:  # not a git repo, no PRIORITIES.md: no report lines
            o = run("session_brief.py", {"cwd": d}, CLAUDE_PROJECT_DIR=d, PERUN_SOURCE=d)
        self.assertTrue(o["hookSpecificOutput"]["additionalContext"].endswith(HOST_RULES))


class Bypass(unittest.TestCase):
    def test_fourth_deny_allowed_with_warn_then_resets(self):
        with tempfile.TemporaryDirectory() as d:
            env = dict(PERUN_HEAVY_DIR=str(Path(d) / "heavy"), PERUN_GATE_LOAD1="99", PERUN_GATE_CORES="2",
                       PERUN_GATE_FREE_RAM_PCT="50", HOME=d, XDG_CACHE_HOME=d)
            p = {"cwd": d, "tool_input": {"command": "pytest -q"}}
            for _ in range(3):
                self.assertEqual(run("heavy_gate.py", p, **env)["hookSpecificOutput"]["permissionDecision"], "deny")
            o = run("heavy_gate.py", p, **env)["hookSpecificOutput"]
            self.assertNotIn("permissionDecision", o)
            self.assertIn("WARN", o["additionalContext"])
            self.assertEqual(run("heavy_gate.py", p, **env)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_old_denies_expire_and_other_command_independent(self):
        import heavy_gate as hg
        with tempfile.TemporaryDirectory() as d:
            os.environ["PERUN_HEAVY_DIR"] = str(Path(d) / "heavy")
            try:
                for i in range(3):
                    hg._bypass("pytest", "/w", True, now=1000 + i)
                self.assertFalse(hg._bypass("pytest", "/w", False, now=1000 + hg.WINDOW + 10))
                for i in range(3):
                    hg._bypass("pytest", "/w", True, now=5000 + i)
                self.assertFalse(hg._bypass("npm test", "/w", False, now=5010))
                self.assertTrue(hg._bypass("pytest", "/w", False, now=5010))
            finally:
                os.environ.pop("PERUN_HEAVY_DIR")


class Hardening(unittest.TestCase):
    def test_exclusive_lease_never_bypassed(self):
        with tempfile.TemporaryDirectory() as d:
            lease = Path(d) / "heavy"
            env = dict(PERUN_HEAVY_DIR=str(lease), PERUN_GATE_LOAD1="0", PERUN_GATE_CORES="8",
                       PERUN_GATE_FREE_RAM_PCT="80", HOME=d, XDG_CACHE_HOME=d)
            subprocess.run([sys.executable, str(SC / "perun_policy.py"), "heavy-exclusive"], env={**os.environ, **env},
                           capture_output=True)
            p = {"cwd": d, "tool_input": {"command": "pytest -q"}}
            for _ in range(5):
                o = run("heavy_gate.py", p, **env)["hookSpecificOutput"]
                self.assertEqual(o.get("permissionDecision"), "deny")
                self.assertIn("gate running", o["permissionDecisionReason"])

    def test_corrupt_ledger_fails_open_to_deny(self):
        import heavy_gate as hg
        with tempfile.TemporaryDirectory() as d:
            os.environ["PERUN_HEAVY_DIR"] = str(Path(d) / "heavy")
            try:
                (Path(d) / "heavy-denies.json").write_text("{not json")
                self.assertFalse(hg._bypass("pytest", "/w", False, now=1))
            finally:
                os.environ.pop("PERUN_HEAVY_DIR")

    def test_whitespace_normalized_key(self):
        import heavy_gate as hg
        with tempfile.TemporaryDirectory() as d:
            os.environ["PERUN_HEAVY_DIR"] = str(Path(d) / "heavy")
            try:
                for c in ("pytest  -q", "pytest -q", " pytest\t-q"):
                    hg._bypass(c, "/w", True, now=10)
                self.assertTrue(hg._bypass("pytest -q", "/w", False, now=11))
            finally:
                os.environ.pop("PERUN_HEAVY_DIR")

    def test_brief_import_failure_keeps_report_lines(self):
        with tempfile.TemporaryDirectory() as d:
            sc = Path(d) / "sc"
            sc.mkdir()
            for f in SC.glob("*.py"):
                (sc / f.name).write_text(f.read_text())
            (sc / "subagent_start_inject.py").write_text("raise ImportError('x')\n")
            (Path(d) / "PRIORITIES.md").write_text("1. Ship thing #7\n")
            r = subprocess.run([sys.executable, str(sc / "session_brief.py")], input=json.dumps({"cwd": d}),
                               capture_output=True, text=True, env={**os.environ, "CLAUDE_PROJECT_DIR": d})
            self.assertEqual(r.returncode, 0)
            ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("PRIORITIES.md", ctx)
            self.assertNotIn("Host rules", ctx)


class Template(unittest.TestCase):
    def test_no_force_pin(self):
        env = json.loads(TPL.read_text())["env"]
        self.assertEqual(env["CLAUDE_CODE_SUBAGENT_MODEL"], "sonnet")
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL_FORCE", env)


if __name__ == "__main__":
    unittest.main()
