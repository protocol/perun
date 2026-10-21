#!/usr/bin/env python3
"""Replay: an applied operating-layer install arms ceo_altitude_guard.py (role ceo, warn) by default.

Bug: the policy default role is `off`, so the guard counted but never warned even when installed. Each case installs
into a fresh temp repo and runs the installed hook command as the host wires it (no PERUN_ROLE, no PERUN_POLICY).
Fixture paths are fictional (/work/acme-app).
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTICE = "CEO-altitude guard now warns (role=ceo); opt out: perun_policy set role off"
DELEGATE = "delegate: spawn a lane with the brief"


@unittest.skipUnless(shutil.which("jq") and shutil.which("bash"), "install.sh needs jq and bash")
class DefaultWarn(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ceo-default-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def env(self, **extra):
        base = {k: v for k, v in os.environ.items() if k not in ("PERUN_POLICY", "PERUN_ROLE")}
        return {**base, "DCR_NO_PROBE": "1", "CLAUDE_CONFIG_DIR": str(self.tmp / "home"), **extra}

    def install(self, name, *flags, **env):
        target = self.tmp / name
        (target / ".claude").mkdir(parents=True, exist_ok=True)
        (self.tmp / "home").mkdir(exist_ok=True)
        (target / ".claude/settings.local.json").write_text("{}")
        p = subprocess.run(["bash", str(ROOT / "install.sh"), "--with-delivery", "--apply-operating-layer", *flags, str(target)],
                           capture_output=True, text=True, env=self.env(**env))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.out = p.stdout
        return target

    def second_edit_output(self, target):
        hooks = json.loads((target / ".claude/settings.local.json").read_text())["hooks"]["PreToolUse"]
        cmd = next(h["command"] for e in hooks for h in e["hooks"] if "ceo_altitude_guard.py" in h["command"])
        env = self.env(CLAUDE_PROJECT_DIR=str(target), PERUN_CEO_DIR=str(self.tmp / "state"))
        out = ""
        for _ in range(2):  # the 2nd direct source edit in one turn is the first flag
            payload = {"session_id": "s1", "prompt_id": "p1", "hook_event_name": "PreToolUse", "cwd": str(target),
                       "tool_name": "Edit", "tool_input": {"file_path": "/work/acme-app/x.py"}}
            p = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, env=env, cwd=target,
                               input=json.dumps(payload))
            self.assertEqual(p.returncode, 0, p.stderr)
            out = p.stdout
        return out

    def test_fresh_install_warns_on_second_main_session_edit(self):
        target = self.install("fresh")
        self.assertEqual(json.loads((target / ".perun/policy.json").read_text())["role"], "ceo")
        self.assertIn(NOTICE, self.out)
        self.assertIn(DELEGATE, self.second_edit_output(target))

    def test_role_off_stays_silent(self):
        target = self.install("off", "--policy", "role=off")
        self.assertEqual(self.second_edit_output(target), "")

    def test_existing_policy_role_is_kept(self):
        target = self.tmp / "keep"
        (target / ".perun").mkdir(parents=True)
        (target / ".perun/policy.json").write_text('{"role": "off"}')
        self.install("keep")
        self.assertEqual(json.loads((target / ".perun/policy.json").read_text())["role"], "off")
        self.assertNotIn(NOTICE, self.out)

    def test_env_role_at_install_writes_no_role(self):
        target = self.install("env", PERUN_ROLE="off")
        policy = target / ".perun/policy.json"
        self.assertNotIn("role", json.loads(policy.read_text()) if policy.exists() else {})
        self.assertNotIn(NOTICE, self.out)

    def test_policy_flag_role_prints_no_notice(self):
        self.install("flag", "--policy", "role=ceo-strict")
        self.assertNotIn(NOTICE, self.out)


if __name__ == "__main__":
    unittest.main()
