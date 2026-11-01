#!/usr/bin/env python3
"""Tests for landing_watchdog.py: stall, no stall, no green PR, throttle, off mode, fail-open, the policy keys, the train
liveness and decision-effect lines and the operating-layer wiring (install into a scratch repo, then fire the hook exactly as wired).

Fixtures are synthetic (a throwaway bare origin plus clone with backdated commits, a fake `gh` script on PATH); the
real gh, the real policy file and the real cache are never touched.
"""
import json
import os
import shlex
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
import train_yield as ty  # noqa: E402

FAKE_GH = """#!/bin/sh
echo x >> "$FAKE_GH_COUNT"
[ -n "$FAKE_GH_FAIL" ] && { echo "gh: boom" >&2; exit 1; }
[ "$2" = graphql ] && exec cat "$FAKE_GH_GQL"
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


def stage(state="PENDING"):
    """The train's progress marker as `gh pr list --json statusCheckRollup` exports it (checked on gh 2.99.0): context, state, start time and target, no description."""
    return {"__typename": "StatusContext", "context": "perun/train-stage", "state": state, "targetUrl": "", "startedAt": "1970-01-01T00:16:40Z"}


def status(desc, **kw):
    """The same marker as the GraphQL API returns it, with the description and createdAt (epoch 1000) that `gh pr list` leaves out."""
    return {"__typename": "StatusContext", "context": "perun/train-stage", "state": "PENDING", "description": desc, "createdAt": "1970-01-01T00:16:40Z", **kw}


def iso(t):
    """An epoch second as the ISO time GitHub puts in createdAt."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))


def reply(*prs):
    """The GraphQL reply for the markers query: each item is one open PR's context nodes on its last commit (None = a commit with no checks)."""
    return json.dumps({"data": {"repository": {"pullRequests": {"nodes": [
        {"commits": {"nodes": [{"commit": {"statusCheckRollup": None if c is None else {"contexts": {"nodes": c}}}}]}} for c in prs]}}}})


def git(cwd, *args, **env):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env={**os.environ, **env})


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="lw-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin, self.cache, self.count, self.prs, self.gql = self.tmp / "bin", self.tmp / "cache", self.tmp / "count", self.tmp / "prs.json", self.tmp / "gql.json"
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
                    "FAKE_GH_COUNT": str(self.count), "FAKE_GH_JSON": str(self.prs), "FAKE_GH_GQL": str(self.gql)}
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

    def set_stages(self, *prs):
        self.gql.write_text(reply(*prs))

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


class TrainStageIsNotACheck(unittest.TestCase):
    """green() ignores the train's own progress marker (pending while a run is live, failure after a skip); any other pending status still blocks."""

    def pr(self, *rolls):
        return {**GREEN, "statusCheckRollup": list(rolls)}

    def test_a_marker_beside_a_passing_check_run_counts_green_in_every_state(self):
        for state in ("PENDING", "FAILURE", "ERROR", "SUCCESS"):
            with self.subTest(state=state):
                self.assertTrue(lw.green(self.pr(OK, stage(state))))

    def test_a_pending_status_with_another_context_still_blocks(self):
        other = {"__typename": "StatusContext", "context": "ci/other", "state": "PENDING"}
        self.assertFalse(lw.green(self.pr(OK, other)))
        self.assertFalse(lw.green(self.pr(OK, stage(), other)))

    def test_the_marker_alone_is_not_a_check(self):
        self.assertFalse(lw.green(self.pr(stage())))

    def test_only_a_status_context_is_exempt(self):
        run = {"__typename": "CheckRun", "name": "perun/train-stage", "status": "IN_PROGRESS", "conclusion": ""}
        self.assertFalse(lw.green(self.pr(OK, run)))

    def test_the_constant_is_the_one_merge_train_posts(self):
        import merge_train
        self.assertEqual(lw.TRAIN_STAGE, merge_train.STAGE_CONTEXT)


class TrainMarks(unittest.TestCase):
    """_marks: stage, time, eta and run id from the marker's description; what cannot be read is skipped, never guessed."""

    def test_reads_stage_time_eta_and_run(self):
        stages = [status("gating run=ab12cd34 at=1000 eta<=1200s"),
                  status("landing run=ab12cd34 at=1001"),
                  status("queued run=ff00ff00"),  # no at=: the status createdAt (epoch 1000)
                  status("queued run=ee11ee11 at=2000", createdAt="1970-01-01T01:00:00Z"),  # at= beats createdAt
                  status("gating at=5")]  # no run id
        self.assertEqual(lw._marks(stages), [("ab12cd34", "gating", 1000, 1200), ("ab12cd34", "landing", 1001, 0), ("ff00ff00", "queued", 1000, 0),
                                             ("ee11ee11", "queued", 2000, 0), ("?", "gating", 5, 0)])

    def test_a_marker_with_no_stage_word_or_no_time_is_skipped(self):
        def drop(r, key):
            return {k: v for k, v in r.items() if k != key}
        for r in (status(""), status("  "), drop(status("x"), "description"), drop(status("gating run=x"), "createdAt"),
                  status("gating run=x", createdAt="yesterday"), status("gating run=x", createdAt=None), status("gating run=x", createdAt=5),
                  status("gating run=x at=99999999999999999999", createdAt=None)):
            with self.subTest(marker=r):
                self.assertEqual(lw._marks([r]), [])

    def test_a_hand_made_status_cannot_grow_a_line_or_overflow_a_number(self):
        self.assertEqual(lw._marks([status("gating run=" + "a" * 40 + " at=5 eta<=999999999999s")]), [("a" * 16, "gating", 5, 0)])

    def test_a_made_up_eta_is_capped_at_a_day(self):
        for eta, want in (("999999999", 86400), ("86401", 86400), ("86400", 86400), ("100", 100)):
            with self.subTest(eta=eta):
                self.assertEqual(lw._marks([status(f"gating run=x at=5 eta<={eta}s")]), [("x", "gating", 5, want)])

    def test_a_time_more_than_5_min_ahead_of_the_clock_falls_back_to_the_status_created_at(self):
        now = 1_800_000_000
        self.assertEqual(lw._marks([status(f"gating run=x at={now + 300}")], now=now), [("x", "gating", now + 300, 0)], "5 min ahead is clock skew: trusted")
        self.assertEqual(lw._marks([status(f"gating run=x at={now + 301}", createdAt=iso(now - 600))], now=now), [("x", "gating", now - 600, 0)])
        self.assertEqual(lw._marks([status("gating run=x at=9999999999", createdAt=iso(now - 600))], now=now), [("x", "gating", now - 600, 0)])
        nothing = {k: v for k, v in status("gating run=x at=9999999999").items() if k != "createdAt"}
        for r in (status("gating run=x at=9999999999", createdAt=None), nothing):
            with self.subTest(marker=r):
                self.assertEqual(lw._marks([r], now=now), [], "no createdAt to fall back to: skipped, not guessed")


class TrainStages(unittest.TestCase):
    """_stages: `gh pr list` leaves out a status's description, so one `gh api graphql` call reads the markers, and only while the list shows one."""

    LISTED = [{"statusCheckRollup": [OK, stage()]}]

    def stages(self, out, prs=None):
        with mock.patch.object(lw, "_run", return_value=out) as run:
            return lw._stages(self.LISTED if prs is None else prs, "main", "/nonexistent"), run

    def test_no_marker_in_the_list_means_no_call(self):
        other = {"__typename": "StatusContext", "context": "ci/other", "state": "PENDING"}
        for prs in ([], [GREEN], [{"statusCheckRollup": None}], [{}], [{"statusCheckRollup": [OK, other]}]):
            with self.subTest(prs=prs):
                got, run = self.stages(reply([status("gating run=x at=5")]), prs)
                self.assertEqual(got, [])
                run.assert_not_called()

    def test_a_marker_in_the_list_means_one_call_that_returns_only_markers(self):
        mine, later = status("gating run=ab12cd34 at=1000"), status("landing run=ab12cd34 at=1001")
        other, lookalike = {**status("x"), "context": "ci/other"}, {**status("gating run=x at=5"), "__typename": "CheckRun"}
        got, run = self.stages(reply([{"__typename": "CheckRun"}, mine, other], [lookalike], None, [later]))
        self.assertEqual(got, [mine, later])
        run.assert_called_once()
        args = run.call_args[0][0]
        self.assertEqual(args[:4], ["gh", "api", "graphql", "-f"])
        self.assertTrue(args[4].startswith("query=query("))
        self.assertEqual(args[5:], ["-f", "base=main", "-F", "owner={owner}", "-F", "repo={repo}"])

    def test_the_query_asks_for_the_open_prs_into_the_branch_and_the_text_gh_drops(self):
        for want in ("states:OPEN", "baseRefName:$base", "first:100", "commits(last:1)", "...on StatusContext{context,description,createdAt}"):
            self.assertIn(want, lw.STAGES_Q)
        self.assertEqual(lw.STAGES_Q.count("{"), lw.STAGES_Q.count("}"))

    def test_a_failing_call_or_an_odd_reply_gives_nothing(self):
        for out in ("not json", "[]", "{}", '{"data": null}', '{"data": {"repository": null}}', reply(5)):
            with self.subTest(out=out):
                self.assertEqual(self.stages(out)[0], [])
        for exc in (RuntimeError("gh api failed"), subprocess.TimeoutExpired("gh", 30)):
            with self.subTest(exc=exc), mock.patch.object(lw, "_run", side_effect=exc):
                self.assertEqual(lw._stages(self.LISTED, "main", "/nonexistent"), [])


class RunLiveness(unittest.TestCase):
    """_runs: (stuck line, idle minutes). The last train activity is the newest marker of any run or a landing; only a live marker that is itself the last activity can
    be stuck, and an old outcome or landing is idle time for the stall line."""

    NOW = 1_800_000_000
    NONE = (None, None)

    def runs(self, marks, landed=None, minutes=60):
        return lw._runs(marks, landed, minutes, now=self.NOW)

    def mark(self, stage, age_min, eta=0, run="r1"):
        return (run, stage, self.NOW - age_min * 60, eta)

    @staticmethod
    def stuck(run, stage, k, x, y):
        return f"Train run stuck: run {run} posted {stage} on {k} PRs {x} min ago (expected <= {y} min), no outcome since. Check the train runner, not the PRs."

    def test_stuck_fires_a_minute_past_1_5x_the_default_and_not_a_minute_before(self):
        self.assertEqual(lw.LIVE, ("queued", "gating", "landing"))
        for st in lw.LIVE:
            with self.subTest(stage=st):
                self.assertEqual(self.runs([self.mark(st, 91)]), (self.stuck("r1", st, 1, 91, 60), None))
                self.assertEqual(self.runs([self.mark(st, 89)]), self.NONE)
        self.assertEqual(self.runs([self.mark("gating", 90)]), self.NONE, "exactly 1.5x is not older than 1.5x")

    def test_stuck_uses_the_eta_the_marker_carries(self):
        self.assertEqual(self.runs([self.mark("gating", 31, eta=1200)]), (self.stuck("r1", "gating", 1, 31, 20), None))
        self.assertEqual(self.runs([self.mark("gating", 29, eta=1200)]), self.NONE)
        self.assertEqual(self.runs([self.mark("gating", 100, eta=7200)]), self.NONE, "a longer eta moves the line out")
        self.assertEqual(self.runs([self.mark("gating", 181, eta=7200)]), (self.stuck("r1", "gating", 1, 181, 120), None))
        self.assertEqual(self.runs([self.mark("gating", 140, eta=3600)]), (self.stuck("r1", "gating", 1, 140, 60), None))

    def test_an_outcome_is_never_stuck_and_wins_a_tie_in_time(self):
        for outcome in ("done", "failed", "skipped", "deferred", "odd"):
            with self.subTest(outcome=outcome):
                self.assertEqual(self.runs([self.mark(outcome, 500)]), (None, 500))
        for pair in ([self.mark("gating", 200), self.mark("skipped", 200)], [self.mark("skipped", 200), self.mark("gating", 200)]):
            self.assertEqual(self.runs(pair), (None, 200), "the outcome is the newer of a tie")

    def test_a_newer_marker_of_any_run_supersedes_a_live_one(self):
        # a run id is minted per `merge_train.py stage` call, not per train: one train posts queued, gating and landing under three ids
        train = [self.mark("queued", 200, run="10529-3e"), self.mark("gating", 170, run="10574-e7"), self.mark("landing", 140, run="10617-70")]
        self.assertEqual(self.runs(train), (self.stuck("10617-70", "landing", 1, 140, 60), None), "the newest marker names the run; the older ones are history")
        self.assertEqual(self.runs([self.mark("gating", 300, run="a1"), self.mark("queued", 10, run="b2")]), self.NONE)
        self.assertEqual(self.runs([self.mark("gating", 300, run="a1"), self.mark("done", 100, run="b2")]), (None, 100))
        dead = [self.mark("gating", 10 * 24 * 60, eta=10800, run="dead"), self.mark("done", 10, run="new")]
        self.assertEqual(self.runs(dead), self.NONE, "a dead run's marker on a PR no later train re-posted is superseded, however old")

    def test_k_counts_the_markers_of_that_run_and_stage(self):
        marks = [self.mark("gating", 140), self.mark("gating", 141), self.mark("queued", 150)]
        self.assertEqual(self.runs(marks), (self.stuck("r1", "gating", 2, 140, 60), None))
        self.assertEqual(self.runs([self.mark("gating", 140), self.mark("gating", 141, run="r2")])[0], self.stuck("r1", "gating", 1, 140, 60), "another run is not counted")

    def test_a_landing_after_a_live_marker_supersedes_it_and_one_before_does_not(self):
        live = [self.mark("gating", 140)]
        self.assertEqual(self.runs(live, landed=self.NOW - 141 * 60), (self.stuck("r1", "gating", 1, 140, 60), None))
        self.assertEqual(self.runs(live, landed=self.NOW - 20 * 60), self.NONE, "a landing since: a hand merge or a train, the repo is moving")
        self.assertEqual(self.runs(live, landed=self.NOW - 139 * 60), (None, 139.0), "superseded, so not stuck; the landing itself is old enough to be idle time")
        self.assertEqual(self.runs(live, landed=self.NOW - 140 * 60), (None, 140.0), "an outcome wins a tie in time")

    def test_a_landing_time_ahead_of_the_clock_is_ignored_so_it_cannot_mute_a_stuck_run(self):
        live = [self.mark("gating", 140)]
        self.assertEqual(self.runs(live, landed=self.NOW + 300), self.NONE, "5 min ahead is clock skew: trusted, a landing since")
        self.assertEqual(self.runs(live, landed=self.NOW + 301), (self.stuck("r1", "gating", 1, 140, 60), None))
        self.assertEqual(self.runs([self.mark("done", 500)], landed=self.NOW + 10 ** 6), (None, 500), "idle time stays measured from the marker")

    def test_idle_is_the_age_of_the_last_activity_past_the_larger_of_1_5x_expected_and_the_check_window(self):
        for eta, minutes, limit in ((0, 60, 90), (7200, 60, 180), (0, 120, 120)):
            with self.subTest(eta=eta, minutes=minutes):
                self.assertEqual(self.runs([self.mark("done", limit + 1, eta=eta)], minutes=minutes), (None, limit + 1))
                self.assertEqual(self.runs([self.mark("done", limit - 1, eta=eta)], minutes=minutes), self.NONE)

    def test_idle_looks_at_the_newest_marker_of_every_run(self):
        self.assertEqual(self.runs([self.mark("done", 500, run="a"), self.mark("done", 10, run="b")]), self.NONE)

    def test_a_landing_is_the_last_activity_when_it_is_the_newest(self):
        old = [self.mark("skipped", 3 * 24 * 60)]
        self.assertEqual(self.runs(old, landed=self.NOW - 10 * 60), self.NONE, "a repo that merges, with a skipped marker from days ago")
        self.assertEqual(self.runs(old, landed=self.NOW - 200 * 60), (None, 200), "idle time counts from the landing, not from the old marker")
        self.assertEqual(self.runs(old), (None, 3 * 24 * 60), "no landing time known: the marker alone")

    def test_a_stuck_last_marker_has_no_idle_time_and_a_live_one_not_yet_stuck_has_none_either(self):
        self.assertEqual(self.runs([self.mark("gating", 140)]), (self.stuck("r1", "gating", 1, 140, 60), None))
        self.assertEqual(self.runs([self.mark("gating", 30)]), self.NONE)

    def test_a_made_up_eta_cannot_hide_a_dead_run_for_ever(self):
        marks = lw._marks([status(f"gating run=x at={self.NOW - 37 * 3600} eta<=999999999s")], now=self.NOW)
        self.assertEqual(self.runs(marks), (self.stuck("x", "gating", 1, 2220, 1440), None))

    def test_a_future_time_cannot_mute_the_alarm(self):
        now, far = self.NOW, self.NOW + 10 ** 6
        stale = status(f"gating run=b at={now - 200 * 60}")
        for future in (status(f"done run=a at={far}", createdAt=iso(now - 300 * 60)), status(f"done run=a at={far}", createdAt=None)):
            with self.subTest(future=future):  # it falls back to a createdAt older than the stale run, or is skipped: either way the stale run is the last
                self.assertEqual(self.runs(lw._marks([future, stale], now=now)), (self.stuck("b", "gating", 1, 200, 60), None))
        lone = status(f"queued run=x at={far}", createdAt=iso(now - 200 * 60))
        self.assertEqual(self.runs(lw._marks([lone], now=now)), (self.stuck("x", "queued", 1, 200, 60), None))

    def test_no_markers_is_silent(self):
        self.assertEqual(self.runs([]), self.NONE)
        self.assertEqual(self.runs([], landed=self.NOW - 10 ** 6), self.NONE, "a landing alone is not a train")


class RunLinesThroughAll(unittest.TestCase):
    """_all with canned probe results (no git, no network): where the stuck line and the idle clause land, and the probe tuple's optional tail."""

    STALL = "Landing stalled: 0 merged to main in 60 min, 2 green PRs waiting. Fix landing before starting new work."
    CLAUSE = " No train run in {} min: start the train or check its runner."

    def setUp(self):
        self.now = int(time.time())
        p = mock.patch.multiple(lw, _lkg=lambda c: None, _red=lambda c: None, _installer=lambda c: None, _train_yield=lambda c: None, _decision=lambda c: None,
                                flow_limits=lambda: (0, 0), age_limits=lambda: (0, 0), lane_cfg=lambda: (0, {}))
        p.start()
        self.addCleanup(p.stop)

    def all(self, merged, marks=(), landed=None, k=2):
        return lw._all("/x", ("main", merged, k, k, [], list(marks), landed), 60, 0, (0, 0), (0, {}))

    def stuck(self, run, k, x):
        return f"Train run stuck: run {run} posted gating on {k} PRs {x} min ago (expected <= 60 min), no outcome since. Check the train runner, not the PRs."

    def test_a_healthy_repo_with_an_old_skipped_marker_is_quiet(self):
        marks = [("old1", "skipped", self.now - 3 * 86400, 0)]
        self.assertIsNone(self.all(5, marks))
        self.assertIsNone(self.all(5, marks, landed=self.now - 10 * 60))

    def test_the_clause_rides_the_stall_line_and_only_when_the_last_activity_is_an_old_outcome(self):
        old = [("old1", "skipped", self.now - 200 * 60, 0)]
        self.assertEqual(self.all(0, old), self.STALL + self.CLAUSE.format(200))
        self.assertIsNone(self.all(0, old, k=0), "no green PR waiting: no stall line, so no clause")
        self.assertEqual(self.all(0), self.STALL, "no markers: a repo without trains never gets the clause")
        self.assertEqual(self.all(0, [("o", "done", self.now - 80 * 60, 0)]), self.STALL, "a fresh outcome (trains run but fail) gets none")
        self.assertEqual(self.all(0, old, landed=self.now - 70 * 60), self.STALL, "a landing newer than the marker is fresh enough")

    def test_stuck_and_the_clause_never_fire_together(self):
        live = [("r1", "gating", self.now - 140 * 60, 3600)]
        self.assertEqual(self.all(0, live).splitlines(), [self.STALL, self.stuck("r1", 1, 140)])
        self.assertEqual(self.all(5, live), self.stuck("r1", 1, 140), "stuck does not need a stall line")
        self.assertIsNone(self.all(5, live, landed=self.now - 20 * 60), "a landing since supersedes the live marker")

    def test_the_probe_tuple_may_stop_early(self):
        for tail in ((), ([],), ([], []), ([], [], None)):
            with self.subTest(length=4 + len(tail)):
                self.assertEqual(lw._all("/x", ("main", 0, 2, 2, *tail), 60, 0, (0, 0), (0, {})), self.STALL)


class TrainLivenessHook(Base):
    """The probe sees the marker in its `gh pr list`, reads the markers in one more call, and the hook adds the line."""

    STALL = "Landing stalled: 0 merged to main in 60 min, 1 green PRs waiting. Fix landing before starting new work."
    CLAUSE = " No train run in {} min: start the train or check its runner."

    def mark(self, desc, state="PENDING"):
        """One green PR with the marker: the list shows it without the text, the GraphQL reply carries the text."""
        self.set_prs([{**GREEN, "statusCheckRollup": [OK, stage(state)]}])
        self.set_stages([{"__typename": "CheckRun"}, status(desc, state=state)])

    def test_probe_returns_the_markers_and_asks_once_more_only_while_one_is_listed(self):
        self.mark("gating run=ab12cd34 at=1000 eta<=1200s")
        self.assertEqual(lw.probe(str(self.repo), 60)[5], [("ab12cd34", "gating", 1000, 1200)])
        self.assertEqual(self.gh_calls(), 2, "gh pr list and gh api graphql")
        self.set_prs([GREEN])
        self.assertEqual(lw.probe(str(self.repo), 60)[5], [])
        self.assertEqual(self.gh_calls(), 3, "gh pr list only")

    def test_probe_returns_the_newest_first_parent_commit_time_and_fails_open(self):
        def newest():
            return int(subprocess.run(["git", "-C", str(self.repo), "log", "-1", "--first-parent", "--format=%ct", "origin/main"], capture_output=True, text=True, check=True).stdout)
        before = newest()
        self.assertEqual(lw.probe(str(self.repo), 60)[6], before)
        self.commit(minutes_ago=10)
        self.push()
        self.assertEqual((lw.probe(str(self.repo), 60)[6], newest() > before), (newest(), True))
        real = lw._run

        def no_log(args, cwd, timeout=15):
            if args[:3] == ["git", "log", "-1"]:
                raise RuntimeError("git log failed")
            return real(args, cwd, timeout)
        with mock.patch.object(lw, "_run", no_log):
            probed = lw.probe(str(self.repo), 60)
        self.assertEqual((probed[6], probed[1]), (None, 1), "a failed landing time is None, the rest of the probe stands")

    def test_a_dead_run_is_named_and_its_pr_still_counts_as_waiting(self):
        self.mark(f"gating run=ab12cd34 at={int(time.time()) - 150 * 60} eta<=3600s")
        self.assertEqual(self.prompt().splitlines(), [self.STALL, "Train run stuck: run ab12cd34 posted gating on 1 PRs 150 min ago "
                                                                  "(expected <= 60 min), no outcome since. Check the train runner, not the PRs."])

    def test_a_live_run_and_a_skipped_pr_are_quiet_and_the_skipped_pr_still_waits(self):
        self.mark(f"gating run=ab12cd34 at={int(time.time()) - 30 * 60}")
        self.assertEqual(self.prompt(), self.STALL)
        shutil.rmtree(self.cache)
        self.mark(f"skipped run=ab12cd34 at={int(time.time()) - 5 * 60}", state="FAILURE")
        self.assertEqual(self.prompt(), self.STALL)

    def test_an_old_outcome_with_a_green_pr_waiting_adds_the_clause_to_the_stall_line(self):
        self.mark(f"done run=ab12cd34 at={int(time.time()) - 200 * 60}", state="SUCCESS")
        self.assertEqual(self.prompt(), self.STALL + self.CLAUSE.format(200))

    def test_the_clause_counts_from_the_last_landing_when_that_is_newer_than_every_marker(self):
        self.mark(f"skipped run=ab12cd34 at={int(time.time()) - 3 * 24 * 3600}", state="FAILURE")
        self.assertEqual(self.prompt(), self.STALL + self.CLAUSE.format(300), "the fixture's last landing is 300 min old, the marker 3 days")

    def test_a_healthy_repo_with_an_old_skipped_marker_is_quiet(self):
        self.commit(minutes_ago=10)
        self.push()
        self.mark(f"skipped run=ab12cd34 at={int(time.time()) - 3 * 24 * 3600}", state="FAILURE")
        self.assertIsNone(self.prompt())

    def test_a_dead_runs_marker_is_superseded_by_a_later_landing(self):
        self.commit(minutes_ago=20)
        self.push()
        self.mark(f"gating run=dead0001 at={int(time.time()) - 10 * 24 * 3600} eta<=10800s")
        self.assertIsNone(self.prompt())

    def test_a_failed_second_call_keeps_the_other_lines(self):
        self.set_prs([{**GREEN, "statusCheckRollup": [OK, stage()]}])  # a marker is listed; no reply file, so the fake's `gh api graphql` fails
        self.assertEqual(self.prompt(), self.STALL)
        self.assertEqual(self.gh_calls(), 2)

    def test_the_second_call_shares_the_throttle(self):
        self.mark(f"gating run=ab12cd34 at={int(time.time()) - 150 * 60}")
        first = self.prompt()
        self.assertIn("Train run stuck", first)
        self.assertEqual((self.prompt(), self.gh_calls()), (first, 2))

    def test_the_cli_check_reports_the_line(self):
        self.mark(f"gating run=ab12cd34 at={int(time.time()) - 150 * 60}")
        p = subprocess.run([sys.executable, str(SC / "landing_watchdog.py"), "check"], cwd=self.repo, capture_output=True, text=True, env=os.environ)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertIn("Train run stuck: run ab12cd34 posted gating on 1 PRs 150 min ago", p.stdout)


class Expect(Base):
    """`landing_watchdog.py expect`: the decision file and the exit codes."""

    def expect(self, *args, **env):
        return subprocess.run([sys.executable, str(SC / "landing_watchdog.py"), "expect", *args], cwd=self.repo, capture_output=True, text=True, env={**os.environ, **env})

    def test_records_a_decision_with_the_default_and_an_explicit_window(self):
        f = self.repo / ".git" / "perun-decisions.jsonl"
        p = self.expect("train_size>=12")
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "decision recorded: train_size>=12 for 24 h\n", ""))
        p = self.expect("train_size>=3", "--hours", "2")
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "decision recorded: train_size>=3 for 2 h\n", ""))
        a, b = (json.loads(x) for x in f.read_text().splitlines())
        self.assertEqual(sorted(a), ["at", "metric", "op", "until", "value"])
        self.assertEqual((a["metric"], a["op"], a["value"], a["until"] - a["at"]), ("train_size", ">=", 12, 24 * 3600))
        self.assertEqual((b["value"], b["until"] - b["at"]), (3, 2 * 3600))
        self.assertLess(abs(a["at"] - time.time()), 60)

    def test_the_env_names_the_decision_file(self):
        f = self.tmp / "elsewhere.jsonl"
        self.assertEqual(self.expect("train_size>=5", PERUN_DECISIONS=str(f)).returncode, 0)
        self.assertEqual(json.loads(f.read_text())["value"], 5)
        self.assertFalse((self.repo / ".git" / "perun-decisions.jsonl").exists())

    def test_anything_else_exits_2_with_usage_and_writes_nothing(self):
        for args in ((), ("train_size>=0",), ("train_size>=-1",), ("train_size>=1.5",), ("train_size>=",), ("train_size>12",), ("train_size=12",),
                     ("train_size<=12",), ("size>=12",), ("train_size>=12 ",), ("train_size >= 12",), ("train_size>=1234567890",),
                     ("train_size>=12", "--hours"), ("train_size>=12", "--hours", "0"), ("train_size>=12", "--hours", "x"), ("train_size>=12", "--hours", "-1"),
                     ("train_size>=12", "--hours", "1.5"), ("train_size>=12", "--days", "2"), ("train_size>=12", "--hours", "2", "x"),
                     ("--hours", "2", "train_size>=12")):
            with self.subTest(args=args):
                p = self.expect(*args)
                self.assertEqual((p.returncode, p.stdout), (2, ""))
                self.assertIn("usage: landing_watchdog.py expect 'train_size>=N' [--hours H]", p.stderr)
        self.assertFalse((self.repo / ".git" / "perun-decisions.jsonl").exists())

    def test_the_documented_quoted_form_works_through_a_shell(self):
        """Unquoted, a shell reads `>=12` as a redirect into a file named `=12` and passes only `train_size`."""
        cmd = shlex.join([sys.executable, str(SC / "landing_watchdog.py"), "expect"]) + " 'train_size>=12' --hours 2"
        p = subprocess.run(cmd, shell=True, cwd=self.repo, capture_output=True, text=True, env=os.environ)
        self.assertEqual((p.returncode, p.stdout, p.stderr), (0, "decision recorded: train_size>=12 for 2 h\n", ""))
        self.assertFalse((self.repo / "=12").exists())

    def test_every_place_that_shows_the_command_quotes_the_argument(self):
        shown = {"usage": lw.EXPECT_USAGE, "module docstring": lw.__doc__, "host sizing guide": (ROOT / ".claude/skills/agentic-delivery/references/fanout-host-sizing.md").read_text()}
        for name, text in {**shown, "expect docstring": lw.expect.__doc__}.items():
            with self.subTest(doc=name):
                self.assertNotRegex(text, r"expect\s+train_size>=")
        for name, text in shown.items():
            with self.subTest(doc=name):
                self.assertIn("expect 'train_size>=", text)

    def test_an_unwritable_decision_file_exits_2_not_a_traceback(self):
        p = self.expect("train_size>=5", PERUN_DECISIONS=str(self.tmp))  # a directory
        self.assertEqual((p.returncode, p.stdout), (2, ""))
        self.assertTrue(p.stderr.startswith("landing_watchdog: "), p.stderr)
        self.assertNotIn("Traceback", p.stderr)


class DecisionEffect(unittest.TestCase):
    """_decision: the newest unexpired `expect 'train_size>=N'` against the PRs the trains since actually carried."""

    NOW = 1_800_000_000

    def setUp(self):
        d = Path(tempfile.mkdtemp(prefix="lw-dec-"))
        self.addCleanup(shutil.rmtree, d, True)
        self.dec, self.led = d / "decisions.jsonl", d / "ledger.jsonl"
        p = mock.patch.dict(os.environ, {"PERUN_DECISIONS": str(self.dec), "PERUN_TRAIN_LEDGER": str(self.led)})
        p.start()
        self.addCleanup(p.stop)

    def decide(self, n, set_h=3, left_h=21, **kw):
        rec = {"metric": "train_size", "op": ">=", "value": n, "at": self.NOW - set_h * 3600, "until": self.NOW + left_h * 3600, **kw}
        with open(self.dec, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def train(self, size, h_ago=1, **kw):
        rec = {"tag": "t", "prs": [str(i) for i in range(size)], "landed": [], "outcome": "", "at": self.NOW - int(h_ago * 3600), **kw}
        with open(self.led, "a") as f:
            f.write(json.dumps(rec) + "\n")

    def line(self):
        return lw._decision("/nonexistent", now=self.NOW)

    def test_unmet_with_two_trains_since_fires(self):
        self.decide(12)
        self.train(3)
        self.train(3)
        self.assertEqual(self.line(), "Decision not in effect: train_size>=12 set 3.0 h ago; the 2 trains since carried a median of 3 PRs. "
                                      "Check that the runner reads it.")

    def test_it_is_a_median_not_a_mean_or_a_last(self):
        self.decide(12)
        for size in (2, 3, 4, 9):
            self.train(size)
        self.assertIn("the 4 trains since carried a median of 3.5 PRs", self.line())

    def test_met_is_silent_and_a_median_equal_to_n_is_met(self):
        self.decide(12)
        for sizes, fires in (((12, 12), False), ((13, 20), False), ((10, 14), False), ((2, 12, 12), False), ((20, 20, 3), False), ((11, 12), True)):
            with self.subTest(sizes=sizes):
                self.led.write_text("")
                for size in sizes:
                    self.train(size)
                self.assertEqual(self.line() is not None, fires)

    def test_no_train_or_one_train_since_is_silent(self):
        self.decide(12)
        self.assertIsNone(self.line(), "no ledger")
        self.train(3)
        self.assertIsNone(self.line(), "one train is not a trend")

    def test_an_expired_decision_is_silent(self):
        self.decide(12, set_h=30, left_h=-6)
        self.train(3, h_ago=10)
        self.train(3, h_ago=9)
        self.assertIsNone(self.line())

    def test_records_without_a_time_or_from_before_the_decision_do_not_count(self):
        self.decide(12, set_h=3)
        self.train(3, h_ago=5)
        self.train(3, h_ago=4)
        for _ in range(3):
            with open(self.led, "a") as f:
                f.write(json.dumps({"tag": "t", "prs": ["1"], "landed": [], "outcome": ""}) + "\n")
        self.assertIsNone(self.line())
        self.train(3)
        self.assertIsNone(self.line(), "one counted train since")
        self.train(3)
        self.assertIn("the 2 trains since", self.line())

    def test_a_train_counts_by_when_it_began_not_when_it_ended(self):
        self.decide(12, set_h=3)
        self.train(3, h_ago=2, start=self.NOW - 4 * 3600)  # began before the decision, recorded (ended) after it: the decision never reached it
        self.train(12, h_ago=0.5, start=self.NOW - 3600)
        self.assertIsNone(self.line(), "one train began since; counted by its end stamp the median would be 7.5 and the line would fire")
        self.train(3, h_ago=0.1, start=self.NOW - 1800)
        self.assertIn("the 2 trains since carried a median of 7.5 PRs", self.line())

    def test_a_record_without_a_start_counts_by_its_end_stamp(self):
        self.decide(12, set_h=3)
        self.train(3, h_ago=2)
        self.train(3, h_ago=1)
        self.assertIn("the 2 trains since", self.line())
        self.led.write_text("")
        self.train(3, h_ago=4)
        self.train(3, h_ago=1)
        self.assertIsNone(self.line(), "a record from before the decision does not count")

    def test_the_newest_unexpired_decision_is_the_one_checked(self):
        self.train(4, h_ago=0.5)
        self.train(4, h_ago=0.4)
        self.decide(12, set_h=5)
        self.assertIn("train_size>=12 set 5.0 h ago", self.line())
        self.decide(3, set_h=1)
        self.assertIsNone(self.line(), "the newer decision is met")

    def test_a_newer_expired_decision_is_ignored(self):
        self.train(4, h_ago=0.5)
        self.train(4, h_ago=0.4)
        self.decide(12, set_h=5)
        self.decide(3, set_h=1, left_h=-0.5)
        self.assertIn("train_size>=12 set 5.0 h ago", self.line())

    def test_other_metrics_ops_and_bad_lines_are_ignored(self):
        self.train(3)
        self.train(3)
        base = {"value": 12, "at": self.NOW - 3600, "until": self.NOW + 3600}
        with open(self.dec, "w") as f:
            f.write("not json\n[]\n5\n{}\n")
            for bad in ({"metric": "merges", "op": ">="}, {"metric": "train_size", "op": "<="}, {"metric": "train_size", "op": ">=", "value": "12"},
                        {"metric": "train_size", "op": ">=", "value": 0}, {"metric": "train_size", "op": ">=", "at": "x"}):
                f.write(json.dumps({**base, **bad}) + "\n")
        self.assertIsNone(self.line())
        self.decide(12)
        self.assertIn("train_size>=12", self.line(), "a valid line after the junk is still found")

    def test_missing_or_unreadable_files_are_silent(self):
        self.assertIsNone(self.line(), "neither file exists")
        self.train(3)
        self.train(3)
        self.assertIsNone(self.line(), "no decision file")
        os.mkdir(self.dec)
        self.assertIsNone(self.line(), "a directory is not a decision file")


class DecisionHook(Base):
    """End to end: `expect` and the ledger at their default paths (the git dir), then the hook."""

    def test_the_hook_adds_the_line_while_the_trains_since_are_smaller_than_expected(self):
        env = {k: v for k, v in os.environ.items() if k not in ("PERUN_DECISIONS", "PERUN_TRAIN_LEDGER")}
        p = subprocess.run([sys.executable, str(SC / "landing_watchdog.py"), "expect", "train_size>=12"], cwd=self.repo, capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        for tag in ("t1", "t2"):
            ty.record(str(self.repo / ".git" / "train-yield.jsonl"), tag, [1, 2, 3], [])
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop("PERUN_DECISIONS", None)
            os.environ.pop("PERUN_TRAIN_LEDGER", None)
            lines = self.prompt().splitlines()
        self.assertEqual(lines[-1], "Decision not in effect: train_size>=12 set 0.0 h ago; the 2 trains since carried a median of 3 PRs. Check that the runner reads it.")

    def test_a_train_that_began_before_the_decision_is_not_counted(self):
        env = {k: v for k, v in os.environ.items() if k not in ("PERUN_DECISIONS", "PERUN_TRAIN_LEDGER")}
        p = subprocess.run([sys.executable, str(SC / "landing_watchdog.py"), "expect", "train_size>=12"], cwd=self.repo, capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr)
        for tag in ("t1", "t2"):  # recorded after the decision, but started a minute before it
            ty.record(str(self.repo / ".git" / "train-yield.jsonl"), tag, [1, 2, 3], [], "", None, int(time.time()) - 60)
        with mock.patch.dict(os.environ, clear=False):
            os.environ.pop("PERUN_DECISIONS", None)
            os.environ.pop("PERUN_TRAIN_LEDGER", None)
            self.assertNotIn("Decision not in effect", self.prompt())


if __name__ == "__main__":
    unittest.main()
