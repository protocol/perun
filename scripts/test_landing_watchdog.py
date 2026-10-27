#!/usr/bin/env python3
"""Tests for landing_watchdog.py: stall, no stall, no green PR, throttle, off mode, fail-open, the policy keys and the
operating-layer wiring (install into a scratch repo, then fire the hook exactly as wired).

Fixtures are synthetic (a throwaway bare origin plus clone with backdated commits, a fake `gh` script on PATH); the
real gh, the real policy file and the real cache are never touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
sys.path.insert(0, str(ROOT / "scripts"))
import landing_watchdog as lw  # noqa: E402
import perun_doctor  # noqa: E402
import perun_policy as pp  # noqa: E402

FAKE_GH = """#!/bin/sh
echo x >> "$FAKE_GH_COUNT"
[ -n "$FAKE_GH_FAIL" ] && { echo "gh: boom" >&2; exit 1; }
cat "$FAKE_GH_JSON"
"""
OK = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}
GREEN = {"isDraft": False, "isCrossRepository": False, "mergeable": "MERGEABLE", "statusCheckRollup": [OK, {"__typename": "StatusContext", "state": "SUCCESS"}]}
NOT_GREEN = [
    {"isDraft": True, "statusCheckRollup": [OK]},
    {"isDraft": False, "isCrossRepository": False, "mergeable": "MERGEABLE", "statusCheckRollup": []},
    {"isDraft": False, "isCrossRepository": False, "mergeable": "MERGEABLE", "statusCheckRollup": [OK, {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""}]},
    {"isDraft": False, "isCrossRepository": False, "mergeable": "MERGEABLE", "statusCheckRollup": [OK, {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}]},
    {"isDraft": False, "isCrossRepository": False, "mergeable": "MERGEABLE", "statusCheckRollup": [{"__typename": "StatusContext", "state": "PENDING"}]},
]


def git(cwd, *args, **env):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env={**os.environ, **env})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lw-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin, self.cache, self.count, self.prs = self.tmp / "bin", self.tmp / "cache", self.tmp / "count", self.tmp / "prs.json"
        self.bin.mkdir()
        (self.bin / "gh").write_text(FAKE_GH)
        (self.bin / "gh").chmod(0o755)
        self.origin, self.repo = self.tmp / "origin.git", self.tmp / "acme-app"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.origin), str(self.repo)], check=True, capture_output=True)
        git(self.repo, "config", "user.email", "jane@example.com")
        git(self.repo, "config", "user.name", "Jane Smith")
        self.commit(minutes_ago=300)
        git(self.repo, "push", "-q", "origin", "HEAD:main")
        git(self.repo, "fetch", "-q", "origin")
        git(self.repo, "remote", "set-head", "origin", "main")
        self.set_prs([GREEN])
        self.env = {"PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}", "PERUN_LANDING_DIR": str(self.cache),
                    "FAKE_GH_COUNT": str(self.count), "FAKE_GH_JSON": str(self.prs)}
        p = mock.patch.dict(os.environ, self.env)
        p.start()
        self.addCleanup(p.stop)
        for k in ("PERUN_POLICY", "PERUN_LANDING_WATCHDOG", "FAKE_GH_FAIL"):
            os.environ.pop(k, None)

    def commit(self, minutes_ago):
        (self.repo / f"f{time.time_ns()}").write_text("x")
        git(self.repo, "add", "-A")
        d = f"{int(time.time()) - minutes_ago * 60} +0000"
        git(self.repo, "commit", "-q", "-m", "work", GIT_COMMITTER_DATE=d, GIT_AUTHOR_DATE=d)

    def push(self):
        git(self.repo, "push", "-q", "origin", "HEAD:main")

    def set_prs(self, prs):
        self.prs.write_text(json.dumps(prs))

    def gh_calls(self):
        return len(self.count.read_text().split()) if self.count.exists() else 0

    def prompt(self, now=None):
        return lw.hook({"hook_event_name": "UserPromptSubmit", "cwd": str(self.repo)}, now=now)


class Signal(Base):
    def test_stall_emits_the_one_line(self):
        self.assertEqual(self.prompt(), "Landing stalled: 0 merged to main in 60 min, 1 green PRs waiting. "
                                        "Fix landing before starting new work.")

    def test_recent_landing_is_no_stall(self):
        self.commit(minutes_ago=10)
        self.push()
        self.assertIsNone(self.prompt())

    def test_landing_stall_min_is_the_window(self):
        self.commit(minutes_ago=90)
        self.push()
        with mock.patch.object(lw, "settings", return_value=("warn", 120)):
            self.assertIsNone(self.prompt())
        shutil.rmtree(self.cache)
        with mock.patch.object(lw, "settings", return_value=("warn", 30)):
            self.assertIn("in 30 min", self.prompt())

    def test_a_stale_local_origin_ref_is_refreshed_before_judging(self):
        """A stale local origin ref must not fake a stall: the hook fetches first."""
        other = self.tmp / "other"
        subprocess.run(["git", "clone", "-q", str(self.origin), str(other)], check=True, capture_output=True)
        git(other, "config", "user.email", "jane@example.com")
        git(other, "config", "user.name", "Jane Smith")
        (other / "g").write_text("y")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "landed elsewhere")
        git(other, "push", "-q", "origin", "HEAD:main")
        self.assertIsNone(self.prompt())

    def test_no_green_pr_is_no_stall(self):
        for pr in NOT_GREEN:
            with self.subTest(pr=pr):
                shutil.rmtree(self.cache, ignore_errors=True)
                self.set_prs([pr])
                self.assertIsNone(self.prompt())
        shutil.rmtree(self.cache, ignore_errors=True)
        self.set_prs([])
        self.assertIsNone(self.prompt())

    def test_counts_only_green_prs(self):
        self.set_prs([GREEN, NOT_GREEN[0], GREEN, NOT_GREEN[3]])
        self.assertIn("2 green PRs waiting", self.prompt())

    def test_cli_check_exit_codes(self):
        run = lambda: subprocess.run([sys.executable, str(SC / "landing_watchdog.py"), "check"], cwd=self.repo,  # noqa: E731
                                     capture_output=True, text=True, env=os.environ)
        p = run()
        self.assertEqual((p.returncode, p.stdout.startswith("Landing stalled")), (1, True), p.stdout + p.stderr)
        self.set_prs([])
        p = run()
        self.assertEqual((p.returncode, p.stdout.startswith("landing ok")), (0, True), p.stdout)
        os.environ["FAKE_GH_FAIL"] = "1"
        p = run()
        self.assertEqual((p.returncode, p.stdout.startswith("landing unknown")), (2, True), p.stdout)


class Throttle(Base):
    def test_one_gh_call_per_window_and_the_verdict_is_replayed(self):
        t = time.time()
        first = self.prompt(now=t)
        self.assertTrue(first)
        for i in range(1, 5):
            self.assertEqual(self.prompt(now=t + i * 60), first)
        self.assertEqual(self.gh_calls(), 1)
        self.assertEqual(self.prompt(now=t + 16 * 60), first)
        self.assertEqual(self.gh_calls(), 2)

    def test_recovery_shows_after_the_window(self):
        t = time.time()
        self.assertTrue(self.prompt(now=t))
        self.commit(minutes_ago=1)
        self.push()
        self.assertTrue(self.prompt(now=t + 60), "cached stall is replayed inside the window")
        self.assertIsNone(self.prompt(now=t + 16 * 60))

    def test_failing_remote_is_not_retried_every_prompt(self):
        os.environ["FAKE_GH_FAIL"] = "1"
        t = time.time()
        with self.assertRaises(RuntimeError):
            self.prompt(now=t)
        for i in range(1, 4):
            self.assertIsNone(self.prompt(now=t + i))
        self.assertEqual(self.gh_calls(), 1)

    def test_a_policy_window_change_rechecks(self):
        t = time.time()
        self.assertTrue(self.prompt(now=t))
        with mock.patch.object(lw, "settings", return_value=("warn", 30)):
            self.assertIn("in 30 min", self.prompt(now=t + 60))
        self.assertEqual(self.gh_calls(), 2)


class Modes(Base):
    def test_off_via_env_makes_no_calls(self):
        os.environ["PERUN_LANDING_WATCHDOG"] = "off"
        self.assertIsNone(self.prompt())
        self.assertEqual(self.gh_calls(), 0)
        self.assertFalse(self.cache.exists())

    def test_off_via_policy(self):
        pol = self.tmp / "policy.json"
        pol.write_text(json.dumps({"landing_watchdog": "off"}))
        os.environ["PERUN_POLICY"] = str(pol)
        self.assertEqual(lw.settings(), ("off", 60))
        self.assertIsNone(self.prompt())
        pol.write_text(json.dumps({"landing_stall_min": 15}))
        self.assertEqual(lw.settings(), ("warn", 15))
        os.environ["PERUN_LANDING_WATCHDOG"] = "warn"
        pol.write_text(json.dumps({"landing_watchdog": "off"}))
        self.assertEqual(lw.settings()[0], "warn", "env beats policy")

    def test_other_events_are_ignored(self):
        self.assertIsNone(lw.hook({"hook_event_name": "Stop", "cwd": str(self.repo)}))
        self.assertEqual(self.gh_calls(), 0)

    def test_policy_keys_validate(self):
        self.assertEqual(pp.validate({})["landing_watchdog"], "warn")
        self.assertEqual(pp.validate({})["landing_stall_min"], 60)
        self.assertEqual(pp.validate({"landing_stall_min": 5, "landing_watchdog": "off"})["landing_stall_min"], 5)
        for bad in ({"landing_watchdog": "block"}, {"landing_stall_min": 0}, {"landing_stall_min": True}, {"landing_stall_min": "60"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pp.validate(bad)


class FailOpen(Base):
    def hook_run(self, stdin, cwd=None, env=None):
        return subprocess.run([sys.executable, str(SC / "landing_watchdog.py")], input=stdin, capture_output=True,
                              text=True, cwd=cwd or self.repo, env=env or os.environ)

    def silent(self, p):
        self.assertEqual((p.returncode, p.stdout), (0, ""), p.stderr)

    def test_the_hook_prints_additional_context_json(self):
        p = self.hook_run(json.dumps({"hook_event_name": "UserPromptSubmit", "cwd": str(self.repo)}))
        out = json.loads(p.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        self.assertTrue(out["additionalContext"].startswith("Landing stalled: 0 merged to main in 60 min"))

    def test_gh_failure(self):
        os.environ["FAKE_GH_FAIL"] = "1"
        self.silent(self.hook_run(json.dumps({"cwd": str(self.repo)})))

    def test_no_gh_on_path(self):
        only = self.tmp / "onlygit"
        only.mkdir()
        (only / "git").symlink_to(shutil.which("git"))
        self.silent(self.hook_run(json.dumps({"cwd": str(self.repo)}), env={**os.environ, "PATH": str(only)}))

    def test_no_remote(self):
        solo = self.tmp / "solo"
        subprocess.run(["git", "init", "-q", str(solo)], check=True)
        self.silent(self.hook_run(json.dumps({"cwd": str(solo)})))
        self.assertEqual(self.gh_calls(), 0)

    def test_not_a_repo(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        self.silent(self.hook_run(json.dumps({"cwd": str(plain)}), cwd=plain))

    def test_failed_fetch_stays_silent_rather_than_guess(self):
        git(self.repo, "remote", "set-url", "origin", str(self.tmp / "gone.git"))
        self.silent(self.hook_run(json.dumps({"cwd": str(self.repo)})))
        self.assertEqual(self.gh_calls(), 0)

    def test_bad_stdin_and_unwritable_cache(self):
        self.silent(self.hook_run("not json"))
        self.silent(self.hook_run(""))
        blocker = self.tmp / "blocker"
        blocker.write_text("file, not dir")
        self.silent(self.hook_run(json.dumps({"cwd": str(self.repo)}), env={**os.environ, "PERUN_LANDING_DIR": str(blocker / "x")}))

    def test_garbage_gh_output(self):
        self.prs.write_text("<html>")
        self.silent(self.hook_run(json.dumps({"cwd": str(self.repo)})))

    def test_default_branch_falls_back_without_origin_head(self):
        git(self.repo, "remote", "set-head", "origin", "-d")
        self.assertEqual(lw.default_branch(str(self.repo)), "main")


class Spawn(Base):
    """PreToolUse Agent|Task: the same line reaches autonomous runs that spawn lanes without a user prompt."""

    def run_hook(self, **data):
        p = subprocess.run([sys.executable, str(SC / "landing_watchdog.py")], capture_output=True, text=True, cwd=self.repo,
                           input=json.dumps({"hook_event_name": "PreToolUse", "cwd": str(self.repo), **data}), env=os.environ)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_spawn_emits_the_line_as_pretooluse_context(self):
        for tool in ("Agent", "Task"):
            with self.subTest(tool=tool):
                out = json.loads(self.run_hook(tool_name=tool))["hookSpecificOutput"]
                self.assertEqual(out["hookEventName"], "PreToolUse")
                self.assertTrue(out["additionalContext"].startswith("Landing stalled: 0 merged to main in 60 min"))
                self.assertNotIn("permissionDecision", out)

    def test_subagent_spawn_is_silent(self):
        self.assertEqual(self.run_hook(tool_name="Agent", agent_id="a1"), "")
        self.assertEqual(self.gh_calls(), 0)

    def test_other_tools_are_silent(self):
        for tool in ("Bash", "Edit", "Read"):
            self.assertEqual(self.run_hook(tool_name=tool), "")
        self.assertEqual(self.gh_calls(), 0)

    def test_off_mode_is_silent(self):
        os.environ["PERUN_LANDING_WATCHDOG"] = "off"
        self.assertEqual(self.run_hook(tool_name="Agent"), "")
        self.assertEqual(self.gh_calls(), 0)

    def test_prompt_and_spawn_share_one_throttled_probe(self):
        t = time.time()
        line = self.prompt(now=t)
        self.assertEqual(lw.hook({"hook_event_name": "PreToolUse", "tool_name": "Agent", "cwd": str(self.repo)}, now=t + 60), line)
        self.assertEqual(self.gh_calls(), 1)


class Wiring(unittest.TestCase):
    def test_policy_doctor_and_template(self):
        self.assertIn("landing_watchdog.py", perun_doctor.HOOK_SCRIPTS)
        tpl = json.loads((ROOT / ".claude/skills/agentic-delivery/templates/operating-layer.settings.json").read_text())
        ups = [h["command"] for e in tpl["hooks"]["UserPromptSubmit"] for h in e["hooks"]]
        self.assertEqual(sum("landing_watchdog.py" in c for c in ups), 1)
        spawn = [e for e in tpl["hooks"]["PreToolUse"] if "landing_watchdog.py" in json.dumps(e)]
        self.assertEqual([e["matcher"] for e in spawn], ["Agent|Task"])

    @unittest.skipUnless(shutil.which("jq") and shutil.which("git"), "install.sh needs jq and git")
    def test_install_wires_the_hook_and_the_installed_hook_fires(self):
        t = Base("setUp")
        t.setUp()
        self.addCleanup(t.doCleanups)
        target, home = t.repo, t.tmp / "home"
        (target / ".claude").mkdir(exist_ok=True)
        home.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("PERUN_POLICY", "PERUN_LANDING_WATCHDOG")}
        env |= {"DCR_NO_PROBE": "1", "CLAUDE_CONFIG_DIR": str(home)}
        p = subprocess.run(["bash", str(ROOT / "install.sh"), "--with-delivery", "--apply-operating-layer", str(target)],
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        hooks = json.loads((target / ".claude/settings.local.json").read_text())["hooks"]
        cmds = [h["command"] for e in hooks["UserPromptSubmit"] for h in e["hooks"] if "landing_watchdog.py" in h["command"]]
        self.assertEqual(len(cmds), 1)
        ups = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "inst1", "cwd": str(target)})
        run = lambda **e: subprocess.run(["bash", "-c", cmds[0]], input=ups, capture_output=True, text=True,  # noqa: E731
                                         env={**env, "CLAUDE_PROJECT_DIR": str(target), **e}, cwd=target).stdout
        self.assertIn("Landing stalled", json.loads(run())["hookSpecificOutput"]["additionalContext"], "installed default is warn")
        shutil.rmtree(t.cache)
        self.assertEqual(run(PERUN_LANDING_WATCHDOG="off"), "")


if __name__ == "__main__":
    unittest.main()
