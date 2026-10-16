#!/usr/bin/env python3
"""terse_reply_check.py prevents instead of forcing a rewrite: budget up front, a violation never blocks the stop,
the reminder lands in the NEXT turn's context once; `! ` lines and fenced code never count; TERSE_MODE=block stays."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/terse_reply_check.py"
LONG = "\n".join(f"line {i} says something short" for i in range(6))  # 6 lines, ~170 chars: over 3 lines


class ReplyBudget(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.addCleanup(self._d.cleanup)
        self.env = {**os.environ, "TERSE_STATE_DIR": self._d.name}
        for k in ("TERSE_MODE", "TERSE_MAX_LINES", "TERSE_MAX_CHARS"):
            self.env.pop(k, None)

    def run_hook(self, event, msg="", sid="s1", **extra):
        env = {**self.env, **extra}
        p = subprocess.run([sys.executable, str(HOOK)], capture_output=True, text=True, env=env, input=json.dumps(
            {"hook_event_name": event, "session_id": sid, "last_assistant_message": msg}))
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def test_budget_injected_at_session_start(self):
        out = self.run_hook("SessionStart")
        self.assertIn("at most 3 lines / 500 chars", out)
        self.assertIn("`! ` command lines are not counted", out)

    def test_budget_follows_env(self):
        self.assertIn("at most 5 lines / 200 chars", self.run_hook("SessionStart", TERSE_MAX_LINES="5", TERSE_MAX_CHARS="200"))

    def test_violation_does_not_block_and_reminds_next_turn_once(self):
        self.assertEqual(self.run_hook("Stop", LONG), "")  # no {"decision": "block"}, no output: nothing to re-emit
        note = self.run_hook("UserPromptSubmit")
        self.assertIn("previous reply was over budget (6 lines", note)
        self.assertIn("do not repeat", note)
        self.assertEqual(self.run_hook("UserPromptSubmit"), "")  # reminder is one-shot

    def test_reminder_is_per_session(self):
        self.run_hook("Stop", LONG, sid="a")
        self.assertEqual(self.run_hook("UserPromptSubmit", sid="b"), "")
        self.assertIn("over budget", self.run_hook("UserPromptSubmit", sid="a"))

    def test_in_budget_reply_records_nothing(self):
        self.assertEqual(self.run_hook("Stop", "Build fixed. Pushed branch."), "")
        self.assertEqual(self.run_hook("UserPromptSubmit"), "")

    def test_fences_and_bang_lines_do_not_count(self):
        cmds = "\n".join(f"! git push origin feat/x{i}" for i in range(8)) + "\n```\n" + "\n".join(["echo hi"] * 20) + "\n```"
        self.assertEqual(self.run_hook("Stop", "Done. Run:\n" + cmds), "")
        self.assertEqual(self.run_hook("UserPromptSubmit"), "")

    def over_budget(self, msg):
        self.assertEqual(self.run_hook("Stop", msg), "")
        return "over budget" in self.run_hook("UserPromptSubmit")

    def test_a_deliverable_in_one_fence_cannot_hide(self):
        self.assertTrue(self.over_budget("Done.\n```\n" + "x" * 11000 + "\n```"))

    def test_an_unclosed_fence_counts_as_prose(self):
        self.assertTrue(self.over_budget("Done.\n```\n" + "\n".join(f"line {i}" for i in range(8))))
        self.assertFalse(self.over_budget("Done.\n```\nls"))  # short unclosed fence is still within budget

    def test_a_wall_of_bang_lines_cannot_hide(self):
        self.assertTrue(self.over_budget("\n".join(f"! git push origin feature/branch-{i:03d}-x" for i in range(100))))

    def test_closed_fence_and_few_bang_lines_still_fit(self):
        self.assertFalse(self.over_budget("Run:\n! ls\n! pwd\n```\nmake test\n```"))

    def test_strict_mode_still_blocks_and_records_nothing(self):
        out = self.run_hook("Stop", LONG, TERSE_MODE="block")
        self.assertEqual(json.loads(out)["decision"], "block")
        self.assertEqual(self.run_hook("UserPromptSubmit"), "")

    def test_strict_mode_loop_guard(self):
        p = subprocess.run([sys.executable, str(HOOK)], capture_output=True, text=True, env={**self.env, "TERSE_MODE": "block"},
                           input=json.dumps({"hook_event_name": "Stop", "stop_hook_active": True, "last_assistant_message": LONG}))
        self.assertEqual(p.stdout, "")

    def test_fails_open(self):
        p = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, env=self.env)
        self.assertEqual((p.returncode, p.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
