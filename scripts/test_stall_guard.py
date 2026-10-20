#!/usr/bin/env python3
"""Tests for stall_guard.py: blocks a stall-phrase stop with no launch, passes the second stop (stop_hook_active), a turn
that launched an Agent or a background tool, the kill switch, a non-stall reply, fenced text, a prior turn's launch, and
garbage input; plus the operating-layer wiring. Fixtures are synthetic transcripts in a temp dir."""
import json
import os
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

    def test_non_stall_and_fenced_text_pass(self):
        for t in ("Merged #12; next lane is running.", "```\nwaiting on you\n```\nLaunching the review now."):
            self.assertEqual(run({}, [PROMPT, text(t)])[1], "")

    def test_garbage_input_fails_open(self):
        for payload in ("not json", "[]", "{", '{"transcript_path": "/nonexistent/t.jsonl"}', '{"transcript_path": 5}', ""):
            rc, out, _ = run(payload)
            self.assertEqual((rc, out), (0, ""), payload)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.jsonl"
            p.write_text("garbage\n{}\n[1]\n")
            self.assertEqual(run({"transcript_path": str(p)})[:2], (0, ""))


class Wiring(unittest.TestCase):
    def test_template_registers_stop_and_doctor_checks_it(self):
        stop = [e for e in json.loads(TEMPLATE.read_text())["hooks"]["Stop"] if "stall_guard.py" in json.dumps(e)]
        self.assertEqual(len(stop), 1)
        self.assertTrue(stop[0]["hooks"][0]["command"].endswith("|| true"))
        self.assertIn("stall_guard.py", perun_doctor.HOOK_SCRIPTS)


if __name__ == "__main__":
    unittest.main()
