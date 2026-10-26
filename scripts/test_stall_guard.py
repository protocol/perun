#!/usr/bin/env python3
"""Tests for stall_guard.py: blocks a stall-phrase stop with no launch, passes the second stop (stop_hook_active), a turn
that launched an Agent or a background tool, the kill switch, a non-stall reply, fenced text, a prior turn's launch, and
garbage input; plus the operating-layer wiring. Fixtures are synthetic transcripts in a temp dir."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
GUARD = SC / "stall_guard.py"
TEMPLATE = ROOT / ".claude/skills/agentic-delivery/templates/operating-layer.settings.json"
sys.path.insert(0, str(ROOT / "scripts"))
import perun_doctor  # noqa: E402

STALL = "The push was denied, so I'm stopped here, waiting on you to approve."
PROMPT = {"type": "user", "message": {"role": "user", "content": "go"}}
RESULT = {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}}


def text(t):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": t}]}}


def tool(name, **inp):
    return {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": name, "input": inp}]}}


def run(payload, entries=None, env=None):
    """Run the hook on a payload; `entries` become the transcript. Returns (exit code, stdout, stderr)."""
    with tempfile.TemporaryDirectory() as d:
        if entries is not None:
            p = Path(d) / "t.jsonl"
            p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
            payload = {**payload, "transcript_path": str(p)}
        e = {k: v for k, v in os.environ.items() if k != "PERUN_STALL_GUARD"}
        e.update(env or {})
        r = subprocess.run([sys.executable, str(GUARD)], input=payload if isinstance(payload, str) else json.dumps(payload),
                           capture_output=True, text=True, env=e)
    return r.returncode, r.stdout, r.stderr


class Guard(unittest.TestCase):
    def blocked(self, out):
        self.assertEqual(json.loads(out)["decision"], "block")
        self.assertIn("denial or blocker stops only that action", json.loads(out)["reason"])

    def test_blocks_stall_with_no_launch(self):
        rc, out, _ = run({}, [PROMPT, tool("Bash", command="git push"), RESULT, text(STALL)])
        self.assertEqual(rc, 0)
        self.blocked(out)

    def test_second_stop_passes(self):
        rc, out, _ = run({"stop_hook_active": True}, [PROMPT, text(STALL)])
        self.assertEqual((rc, out), (0, ""))

    def test_agent_launch_in_turn_passes(self):
        for launch in (tool("Agent", prompt="x"), tool("Task", prompt="x"), tool("Bash", command="make", run_in_background=True)):
            rc, out, _ = run({}, [PROMPT, launch, RESULT, text(STALL)])
            self.assertEqual((rc, out), (0, ""))

    def test_launch_in_an_earlier_turn_does_not_count(self):
        rc, out, _ = run({}, [PROMPT, tool("Agent", prompt="x"), RESULT, text("done"), PROMPT, text(STALL)])
        self.blocked(out)

    def test_kill_switch(self):
        rc, out, _ = run({}, [PROMPT, text(STALL)], env={"PERUN_STALL_GUARD": "off"})
        self.assertEqual((rc, out), (0, ""))

    def test_non_stall_fenced_inline_and_quoted_text_pass(self):
        for t in ("Merged #12; next lane is running.", "```\nwaiting on you\n```\nLaunching the review now.",
                  "The log said `I'm stopped, waiting on you`; launching the build.",
                  "> I'm stopped, waiting on you\nLaunching the review now.",
                  "PR #12 on hold; the build is standing by for CI. Merging #13 next."):
            self.assertEqual(run({}, [PROMPT, text(t)])[1], "", t)

    def test_first_person_stalls_block(self):
        for t in ("I'm on hold until CI is green.", "I am holding here.", "Blocked by the owner; nothing else to do."):
            self.blocked(run({}, [PROMPT, text(t)])[1])

    def test_last_text_block_of_the_message_is_judged(self):
        two = {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": STALL}, {"type": "text", "text": "Launching the review lane now."}]}}
        self.assertEqual(run({}, [PROMPT, two])[1], "")

    def test_reason_allows_an_owner_requested_stop(self):
        out = run({}, [PROMPT, text(STALL)])[1]
        self.assertIn("owner asked you to stop or pause", json.loads(out)["reason"])
        self.assertEqual(run({"stop_hook_active": True}, [PROMPT, text("Stopping as you asked.")])[1], "")

    def test_garbage_input_fails_open(self):
        for payload in ("not json", "[]", "{", '{"transcript_path": "/nonexistent/t.jsonl"}', '{"transcript_path": 5}', ""):
            rc, out, _ = run(payload)
            self.assertEqual((rc, out), (0, ""), payload)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.jsonl"
            p.write_text("garbage\n{}\n[1]\n")
            self.assertEqual(run({"transcript_path": str(p)})[:2], (0, ""))


WAIT = "CI is running; next check at 13:42, merge on green."


class IdleWait(unittest.TestCase):
    """Planted RED transcripts: a turn that only schedules a wake-up while waiting on CI."""

    def reason(self, entries, **kw):
        out = run(kw, entries)[1]
        return json.loads(out)["reason"] if out else ""

    def test_wakeup_only_turn_blocks(self):
        for sleeper in (tool("ScheduleWakeup", delaySeconds=600), tool("CronCreate", cron="*/10 * * * *")):
            r = self.reason([PROMPT, tool("Bash", command="gh pr checks"), RESULT, sleeper, RESULT, text(WAIT)])
            self.assertEqual(r, "Waiting on CI is not a stop: launch the next priority lane now, then wake on the CI notification.")

    def test_launch_passes(self):
        for launch in (tool("Agent", prompt="x"), tool("Task", prompt="x"), tool("Workflow", script="x"),
                       tool("Bash", command="make", run_in_background=True)):
            self.assertEqual(self.reason([PROMPT, launch, RESULT, tool("ScheduleWakeup"), RESULT, text(WAIT)]), "")

    def test_one_shot_kill_switch_and_unrelated_text_pass(self):
        e = [PROMPT, tool("ScheduleWakeup"), RESULT, text(WAIT)]
        self.assertEqual(self.reason(e, stop_hook_active=True), "")
        self.assertEqual(run({}, e, env={"PERUN_STALL_GUARD": "off"})[1], "")
        self.assertEqual(self.reason([PROMPT, tool("ScheduleWakeup"), RESULT, text("Reminder set for tomorrow.")]), "")
        self.assertEqual(self.reason([PROMPT, text(WAIT)]), "")  # no wake-up scheduled: not this trigger
        self.assertEqual(self.reason([PROMPT, tool("ScheduleWakeup"), RESULT, text("`merge on green`")]), "")


NOTE = {"type": "user", "message": {"role": "user", "content": "<task-notification><status>completed</status></task-notification>"}}


class OpenLanesAndNarrowing(unittest.TestCase):
    def blocked(self, entries):
        return bool(run({}, entries)[1])

    def test_earlier_turn_background_lane_still_open_passes(self):
        bg = tool("Agent", prompt="x", run_in_background=True)
        bg["message"]["content"][0]["id"] = "toolu_1"
        wake = [PROMPT, tool("ScheduleWakeup"), RESULT, text(WAIT)]
        self.assertFalse(self.blocked([PROMPT, bg, RESULT, text("launched")] + wake))
        self.assertTrue(self.blocked([PROMPT, bg, RESULT, text("launched"), done("t1", use="toolu_1")] + wake))  # lane finished: still a stall

    def test_past_tense_ci_text_passes_forward_looking_blocks(self):
        for t, want in (("PR merged, CI green, checks passed.", False), ("Merging now.", False), ("Waiting on CI.", True),
                        ("Checks pending; next look at 13:42.", True), ("Holding until checks pass.", True)):
            self.assertEqual(self.blocked([PROMPT, tool("ScheduleWakeup"), RESULT, text(t)]), want, t)


def launched(aid):
    t = f"Async agent launched successfully.\nagentId: {aid} (internal)\nThe agent is working in the background."
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": [{"type": "text", "text": t}]}]}}


def resumed(aid):
    t = json.dumps({"success": True, "message": "Resuming agent", "resumedAgentId": aid})
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": [{"type": "text", "text": t}]}]}}


def done(tid, status="completed", use="toolu_x"):
    return {"type": "user", "message": {"role": "user", "content": f"<task-notification>\n<task-id>{tid}</task-id>\n<tool-use-id>{use}</tool-use-id>\n<status>{status}</status>\n</task-notification>"}}


class OpenBgPerId(unittest.TestCase):
    """Real-format ids: one agent notifies again on each resume, so a raw count goes negative."""

    def open(self, entries):
        sys.path.insert(0, str(SC))
        import stall_guard
        return stall_guard._open_bg([json.dumps(e) for e in entries])

    def test_repeat_notifications_do_not_hide_an_open_lane(self):
        e = [launched("aaa"), launched("bbb"), done("aaa"), resumed("aaa"), done("aaa"), resumed("aaa"), done("aaa")]
        self.assertTrue(self.open(e))  # bbb never finished
        self.assertFalse(self.open(e + [done("bbb", "failed")]))

    def test_resume_reopens_until_its_notification(self):
        self.assertTrue(self.open([launched("aaa"), done("aaa"), resumed("aaa")]))
        self.assertFalse(self.open([launched("aaa"), done("aaa"), resumed("aaa"), done("aaa", "killed")]))

    def test_background_tool_use_closes_by_tool_use_id(self):
        bgt = {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"run_in_background": True}}]}}
        self.assertTrue(self.open([bgt]))
        self.assertFalse(self.open([bgt, done("b1", use="toolu_1")]))


class Wiring(unittest.TestCase):
    def test_default_delivery_install_applies_template_idempotently(self):
        if not shutil.which("jq"):
            self.skipTest("jq missing")
        with tempfile.TemporaryDirectory() as d:
            for _ in range(2):
                subprocess.run(["bash", str(ROOT / "install.sh"), "--with-delivery", d], capture_output=True, check=True)
            stop = json.loads((Path(d) / ".claude/settings.local.json").read_text())["hooks"]["Stop"]
            self.assertEqual(json.dumps(stop).count("stall_guard.py"), 1)

    def test_template_registers_stop_and_doctor_checks_it(self):
        stop = [e for e in json.loads(TEMPLATE.read_text())["hooks"]["Stop"] if "stall_guard.py" in json.dumps(e)]
        self.assertEqual(len(stop), 1)
        self.assertTrue(stop[0]["hooks"][0]["command"].endswith("|| true"))
        self.assertIn("stall_guard.py", perun_doctor.HOOK_SCRIPTS)


if __name__ == "__main__":
    unittest.main()
