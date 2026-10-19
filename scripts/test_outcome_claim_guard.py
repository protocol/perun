#!/usr/bin/env python3
"""Tests for outcome_claim_guard.py: the Stop claim check (must-flag and must-pass replies), the modes and the loop
guard, the policy keys, the PreToolUse PR check on a throwaway git repo and a fake `gh`, fail-open, and the
operating-layer wiring (install into a scratch repo, then fire the hook exactly as wired).

Fixtures are synthetic and generic (Acme, example.com); the real policy file and the real gh are never touched.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
GUARD = SC / "outcome_claim_guard.py"
TEMPLATE = ROOT / ".claude/skills/agentic-delivery/templates/operating-layer.settings.json"
sys.path.insert(0, str(SC))
sys.path.insert(0, str(ROOT / "scripts"))
import outcome_claim_guard as ocg  # noqa: E402
import perun_doctor  # noqa: E402
import perun_policy as pp  # noqa: E402

MUST_FLAG = [
    "The shared merge lock is queued as #41; it ends the risk once it lands.",
    "Big progress today: 12 PRs merged and 5 lanes spawned.",
    "Pipeline work is done and CI is faster now; PR #77 is open.",
    "Fixed the flaky gate in #19, so the train no longer goes red.",
    "That makes 9 merged today.",
    "The pipeline improved a lot: 3 PRs merged, 40 tests added, 25 files touched.",
    # the false-positive rules must skip one claim, never the whole sentence or message
    "Great progress: 12 merged today, 30 still open.",
    "That makes 40 PRs merged since Monday.",
    "The audit log is attached and CI is faster now.",
    "I fixed the merge conflict bug, so the train no longer stalls.",
    "I fixed one error in the report and the gate is faster now.",
    # laundering attempts: the skip words must sit right next to the claim word
    "Train speedup done; see the report.",
    "Fixed the merge train, no conflicts left.",
    "Fixed issues blocking the merge train.",
    "Build speedup is done, per the audit.",
    "I fixed the errors stalling the merge train.",
    "Done: pipeline fixed, see the log.",
]
MUST_PASS = [
    "Merge lock opened as #41, unmeasured; I will measure gate minutes after it merges.",
    "Gate fix opened, not yet measured.",
    "CI is faster: gate median 820s -> 240s over 10 runs after a1b2c3d merged.",
    "The train is faster: lead time 41 min -> 18 min across 12 runs since #88 merged.",
    "The train is not faster yet; nothing has merged since 09:00.",
    "Is the gate fixed?",
    "This change would make CI faster once it merges.",
    "The README typo is fixed and pushed.",
    "Train r12 is running with #5 and #6; next check at 14:00.",
    "```\nfixed the pipeline, 4 PRs merged today\n```\nLog above is from last week.",
    # honest status reports that the claim words and tallies used to flag
    "The Q3 pipeline audit is done.",
    "Done: the handoff note and the pipeline log.",
    "Pulling the 40 PRs merged since Monday into the standup draft.",
    "12 merged today, 30 still open.",
    "I fixed one error: #12 is still in the queue, not merged.",
    "I resolved the merge conflicts on #51 and re-queued it.",
    "The merge hit a conflict on #51, so I resolved it.",
    "Fixed the unit tests on #8; its pre-merge check is running.",
    "Cleaned the backlog: 6 issues already fixed, 3 duplicates.",
    "Closed the already-fixed issues in the backlog.",
]


class StopCheck(unittest.TestCase):
    def test_must_flag(self):
        for text in MUST_FLAG:
            with self.subTest(text=text):
                self.assertTrue(ocg.stop_violation(text))

    def test_must_pass(self):
        for text in MUST_PASS:
            with self.subTest(text=text):
                self.assertIsNone(ocg.stop_violation(text))

    def test_output_counts_are_not_evidence(self):
        self.assertFalse(ocg.evidenced("CI is faster: 6 PRs merged, 3 lanes spawned, 20 tests added, sha a1b2c3d."))

    def test_after_only_number_is_not_before_and_after(self):
        self.assertTrue(ocg.stop_violation("The flaky gate is fixed: 5 of 5 runs pass after a1b2c3d merged."))


class Modes(unittest.TestCase):
    def stop(self, text, mode, active=False):
        return ocg.handle({"hook_event_name": "Stop", "last_assistant_message": text, "stop_hook_active": active},
                          mode, ocg.DEFAULT_PATHS)

    def test_block_blocks_once_with_a_short_reason(self):
        out = self.stop(MUST_FLAG[0], "block")
        self.assertEqual(out["decision"], "block")
        self.assertIn("unmeasured", out["reason"])
        self.assertLess(len(out["reason"]), 500)
        self.assertIsNone(self.stop(MUST_FLAG[0], "block", active=True), "stop_hook_active must never re-block")

    def test_warn_tells_the_owner_and_never_blocks(self):
        out = self.stop(MUST_FLAG[1], "warn")
        self.assertEqual(set(out), {"systemMessage"})

    def test_off_and_compliant_print_nothing(self):
        self.assertIsNone(self.stop(MUST_FLAG[0], "off"))
        self.assertIsNone(self.stop(MUST_PASS[0], "block"))

    def test_default_mode_is_warn(self):
        self.assertEqual(ocg.DEFAULT_MODE, "warn")
        self.assertEqual(pp.validate({})["outcome_guard"], "warn")


class Policy(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ocg-pol-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pol = self.tmp / "policy.json"
        p = mock.patch.dict(os.environ, {"PERUN_POLICY": str(self.pol)})
        p.start()
        self.addCleanup(p.stop)
        os.environ.pop("PERUN_OUTCOME_GUARD", None)

    def test_policy_key_then_env_override(self):
        self.pol.write_text('{"outcome_guard": "block", "outcome_guard_paths": ["deploy/*"]}')
        self.assertEqual(ocg.policy(), ("block", ("deploy/*",)))
        os.environ["PERUN_OUTCOME_GUARD"] = "off"
        self.assertEqual(ocg.policy()[0], "off")

    def test_bad_policy_fails_open_to_defaults(self):
        self.pol.write_text('{"outcome_guard": "loud"}')
        self.assertEqual(ocg.policy(), ("warn", ocg.DEFAULT_PATHS))
        for bad in ({"outcome_guard": "loud"}, {"outcome_guard_paths": "x/*"}, {"outcome_guard_paths": [""]}):
            with self.assertRaises(ValueError):
                pp.validate(bad)


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


@unittest.skipUnless(shutil.which("git"), "needs git")
class PullRequest(unittest.TestCase):
    """`gh pr create` reads git; `gh pr merge` reads one `gh pr view` from a fake gh on PATH."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ocg-pr-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        env = {"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "Jane Smith",
               "GIT_AUTHOR_EMAIL": "jane@example.com", "GIT_COMMITTER_NAME": "Jane Smith",
               "GIT_COMMITTER_EMAIL": "jane@example.com"}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        self.repo = self.tmp / "acme-app"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "README.md").write_text("acme\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "init")
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.repo, "switch", "-qc", "feat")

    def commit(self, path, msg="change"):
        f = self.repo / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", msg)

    def create(self, body, mode="block", globs=ocg.DEFAULT_PATHS):
        cmd = 'gh pr create --base main --title "t" --body "%s"' % body
        return ocg.handle({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": cmd},
                           "cwd": str(self.repo)}, mode, globs)

    def test_pipeline_pr_without_verdict_is_denied_in_block_and_warned_otherwise(self):
        self.commit(".github/workflows/ci.yml")
        out = self.create("Speeds up CI.")["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn(".github/workflows/ci.yml", out["permissionDecisionReason"])
        warn = self.create("Speeds up CI.", mode="warn")["hookSpecificOutput"]
        self.assertNotIn("permissionDecision", warn)
        self.assertIn("pipeline_profile.py compare", warn["additionalContext"])

    def test_keep_passes_revert_and_unverified_are_denied(self):
        self.commit("scripts/merge_train.py")
        self.assertIsNone(self.create("KEEP  dropped 30.0% (10m -> 7m) [n=5]"))
        self.assertIn("REVERT", self.create("REVERT  did not drop by more than 5% and 1s")
                      ["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertIn("UNVERIFIED", self.create("UNVERIFIED  only 1 sample(s) on the smaller side; need >= 3")
                      ["hookSpecificOutput"]["permissionDecisionReason"])

    def test_verdict_in_a_commit_message_counts(self):
        self.commit(".githooks/pre-push", "Run the suite once at the merge gate\n\nKEEP  dropped 41.0% (13m -> 8m) [n=6]")
        self.assertIsNone(self.create("See the commit."))

    def test_non_pipeline_pr_and_policy_globs(self):
        self.commit("src/app.py")
        self.assertIsNone(self.create("Adds a page."))
        self.assertIn("src/app.py", self.create("Adds a page.", globs=("src/*",))
                      ["hookSpecificOutput"]["permissionDecisionReason"])

    def test_merge_reads_gh_pr_view(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        view = {"body": "Faster gates.", "files": [{"path": "scripts/ci-gates.sh"}], "commits": []}
        (bin_dir / "gh").write_text("#!/bin/sh\ncat <<'EOF'\n%s\nEOF\n" % json.dumps(view))
        (bin_dir / "gh").chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": "%s%s%s" % (bin_dir, os.pathsep, os.environ["PATH"])}):
            data = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "gh pr merge 41 --squash"},
                    "cwd": str(self.repo)}
            self.assertEqual(ocg.handle(data, "block", ocg.DEFAULT_PATHS)["hookSpecificOutput"]["permissionDecision"], "deny")
            view["body"] += "\nKEEP  dropped 22.0% (9m -> 7m) [n=4]"
            (bin_dir / "gh").write_text("#!/bin/sh\ncat <<'EOF'\n%s\nEOF\n" % json.dumps(view))
            self.assertIsNone(ocg.handle(data, "block", ocg.DEFAULT_PATHS))

    def test_merge_selector_skips_flag_values_and_keeps_repo(self):
        calls = []
        def fake_run(cmd, cwd):
            calls.append(cmd)
            return json.dumps({"body": "", "files": [], "commits": []})
        with mock.patch.object(ocg, "_run", fake_run):
            ocg.pr_facts("gh pr merge --repo acme/app 41 --merge --subject 'x y' && echo done", str(self.repo))
            ocg.pr_facts("gh pr merge -R acme/app --squash", str(self.repo))
        self.assertEqual(calls[0], ["gh", "pr", "view", "41", "--repo", "acme/app", "--json", "body,files,commits"])
        self.assertEqual(calls[1], ["gh", "pr", "view", "--repo", "acme/app", "--json", "body,files,commits"])

    def test_other_commands_are_ignored(self):
        for cmd in ("gh pr view 4", "git push", "echo gh pr"):
            self.assertIsNone(ocg.handle({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                          "tool_input": {"command": cmd}, "cwd": str(self.repo)}, "block", ocg.DEFAULT_PATHS))


class Contract(unittest.TestCase):
    def run_hook(self, stdin, **env):
        e = {k: v for k, v in os.environ.items() if k != "PERUN_OUTCOME_GUARD"} | env
        return subprocess.run([sys.executable, str(GUARD)], input=stdin, capture_output=True, text=True, env=e)

    def test_fails_open(self):
        for stdin in ("", "not json", "[]"):
            p = self.run_hook(stdin)
            self.assertEqual((p.returncode, p.stdout), (0, ""))
        gh_fail = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "cwd": "/nonexistent/acme",
                              "tool_input": {"command": "gh pr create --body x"}})
        self.assertEqual(self.run_hook(gh_fail, PERUN_OUTCOME_GUARD="block").stdout, "")

    def test_env_block_over_stdin(self):
        p = self.run_hook(json.dumps({"hook_event_name": "Stop", "last_assistant_message": MUST_FLAG[0]}),
                          PERUN_OUTCOME_GUARD="block")
        self.assertEqual(json.loads(p.stdout)["decision"], "block")

    def test_selftest(self):
        self.assertEqual(subprocess.run([sys.executable, str(GUARD), "--selftest"], capture_output=True).returncode, 0)


class NoteNudge(unittest.TestCase):
    """warn-mode Stop leaves a per-session note; the next UserPromptSubmit hands it to the model once."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ocg-note-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        patch = mock.patch.dict(os.environ, {"PERUN_OUTCOME_DIR": self.tmp})
        patch.start()
        self.addCleanup(patch.stop)

    def stop(self, mode, text=MUST_FLAG[0], sid="s1"):
        return ocg.handle({"hook_event_name": "Stop", "last_assistant_message": text, "session_id": sid},
                          mode, ocg.DEFAULT_PATHS)

    def prompt(self, sid="s1"):
        return ocg.handle({"hook_event_name": "UserPromptSubmit", "prompt": "go on", "session_id": sid},
                          "warn", ocg.DEFAULT_PATHS)

    def test_warn_writes_note_then_injects_once_and_deletes_it(self):
        self.assertIn("systemMessage", self.stop("warn"))
        self.assertEqual(os.listdir(self.tmp), ["s1.json"])
        out = self.prompt()["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "UserPromptSubmit")
        for word in ("ends the risk", "before -> after", "Measure it or hedge"):
            self.assertIn(word, out["additionalContext"])
        self.assertLess(len(out["additionalContext"]), 400)
        self.assertEqual(os.listdir(self.tmp), [])
        self.assertIsNone(self.prompt(), "second prompt: nothing left to inject")

    def test_notes_are_per_session(self):
        self.stop("warn", sid="a")
        self.assertIsNone(self.prompt("b"))
        self.assertIsNotNone(self.prompt("a"))

    def test_block_mode_and_compliant_replies_write_no_note(self):
        self.stop("block")
        self.stop("warn", text=MUST_PASS[0])
        self.assertEqual(os.listdir(self.tmp), [])
        self.assertIsNone(self.prompt())

    def test_no_session_id_writes_and_injects_nothing(self):
        ocg.handle({"hook_event_name": "Stop", "last_assistant_message": MUST_FLAG[0]}, "warn", ocg.DEFAULT_PATHS)
        self.assertEqual(os.listdir(self.tmp), [])
        self.assertIsNone(ocg.handle({"hook_event_name": "UserPromptSubmit"}, "warn", ocg.DEFAULT_PATHS))

    def test_session_id_cannot_escape_the_state_dir(self):
        self.stop("warn", sid="../../evil")
        self.assertEqual(os.listdir(self.tmp), ["evil.json"])

    def test_bad_note_is_dropped_silently(self):
        for body in ("not json", "[]", "{}"):
            Path(self.tmp, "s1.json").write_text(body)
            self.assertIsNone(self.prompt(), body)
            self.assertEqual(os.listdir(self.tmp), [], body)

    def test_unwritable_state_dir_still_warns(self):
        blocker = Path(self.tmp, "file")
        blocker.write_text("x")
        with mock.patch.dict(os.environ, {"PERUN_OUTCOME_DIR": str(blocker / "sub")}):
            self.assertIn("systemMessage", self.stop("warn"))
            self.assertIsNone(self.prompt())

    def test_hook_process_roundtrip_and_fail_open_on_bad_stdin(self):
        env = {**os.environ, "PERUN_OUTCOME_GUARD": "warn"}

        def run(stdin):
            return subprocess.run([sys.executable, str(GUARD)], capture_output=True, text=True, env=env, input=stdin)

        run(json.dumps({"hook_event_name": "Stop", "last_assistant_message": MUST_FLAG[0], "session_id": "p1"}))
        out = json.loads(run(json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "p1"})).stdout)
        self.assertIn("additionalContext", out["hookSpecificOutput"])
        bad = run('{"hook_event_name": "UserPromptSubmit", "session_id": 5')
        self.assertEqual((bad.returncode, bad.stdout), (0, ""))


class Wiring(unittest.TestCase):
    def test_template_registers_stop_prompt_and_bash_pretooluse(self):
        hooks = json.loads(TEMPLATE.read_text())["hooks"]
        for ev in ("Stop", "PreToolUse", "UserPromptSubmit"):
            entries = [e for e in hooks[ev] if "outcome_claim_guard.py" in json.dumps(e)]
            self.assertEqual(len(entries), 1, ev)
            self.assertTrue(entries[0]["hooks"][0]["command"].endswith("|| true"))
        self.assertEqual([e for e in hooks["PreToolUse"] if "outcome_claim_guard.py" in json.dumps(e)][0]["matcher"], "Bash")
        self.assertIn("outcome_claim_guard.py", perun_doctor.HOOK_SCRIPTS)

    @unittest.skipUnless(shutil.which("jq") and shutil.which("git"), "install.sh needs jq and git")
    def test_install_wires_both_events_and_the_installed_hook_fires(self):
        tmp = Path(tempfile.mkdtemp(prefix="ocg-inst-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        target, home = tmp / "acme-app", tmp / "home"
        (target / ".claude").mkdir(parents=True)
        home.mkdir()
        subprocess.run(["git", "init", "-q", str(target)], check=True)
        env = {k: v for k, v in os.environ.items() if k not in ("PERUN_POLICY", "PERUN_OUTCOME_GUARD")}
        env |= {"DCR_NO_PROBE": "1", "CLAUDE_CONFIG_DIR": str(home)}
        p = subprocess.run(["bash", str(ROOT / "install.sh"), "--with-delivery", "--apply-operating-layer", str(target)],
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        hooks = json.loads((target / ".claude/settings.local.json").read_text())["hooks"]
        cmds = {ev: [h["command"] for e in hooks[ev] for h in e["hooks"] if "outcome_claim_guard.py" in h["command"]]
                for ev in ("Stop", "PreToolUse", "UserPromptSubmit")}
        self.assertEqual({ev: len(c) for ev, c in cmds.items()}, {"Stop": 1, "PreToolUse": 1, "UserPromptSubmit": 1})
        run_env = {**env, "CLAUDE_PROJECT_DIR": str(target)}
        fire = lambda stdin, **e: subprocess.run(["bash", "-c", cmds["Stop"][0]], input=stdin, capture_output=True,  # noqa: E731
                                                 text=True, env={**run_env, **e}, cwd=target).stdout
        msg = json.dumps({"hook_event_name": "Stop", "last_assistant_message": MUST_FLAG[0], "cwd": str(target),
                          "session_id": "inst1"})
        notes = {"PERUN_OUTCOME_DIR": str(tmp / "notes")}
        self.assertIn("systemMessage", json.loads(fire(msg, **notes)), "installed default is warn")
        ups = json.dumps({"hook_event_name": "UserPromptSubmit", "session_id": "inst1", "cwd": str(target)})
        sent = subprocess.run(["bash", "-c", cmds["UserPromptSubmit"][0]], input=ups, capture_output=True, text=True,
                              env={**run_env, **notes}, cwd=target).stdout
        self.assertIn("Measure it or hedge", json.loads(sent)["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(json.loads(fire(msg, PERUN_OUTCOME_GUARD="block"))["decision"], "block")


if __name__ == "__main__":
    unittest.main()
