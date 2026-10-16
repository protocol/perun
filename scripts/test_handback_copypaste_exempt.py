#!/usr/bin/env python3
"""handback_cap.py: fenced code blocks and `! ` lines are not counted toward the char/line cap, but the whole message
still has a ceiling so a deliverable cannot hide in a fence; terse_reply_check.py ignores `! ` lines in its ratio."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

S = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"
CAP, TERSE = S / "handback_cap.py", S / "terse_reply_check.py"


def cap(msg, tmp, agent="a1"):
    env = {**os.environ, "HANDBACK_STATE_DIR": tmp}
    for k in ("HANDBACK_MAX_CHARS", "HANDBACK_MAX_LINES", "HANDBACK_REQUIRE_STATUS", "HANDBACK_EXEMPT_TYPES"):
        env.pop(k, None)
    p = subprocess.run([sys.executable, str(CAP)], capture_output=True, text=True, env=env,
                       input=json.dumps({"agent_id": agent, "last_assistant_message": msg}))
    return p.returncode, p.stderr


class CopyPaste(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.addCleanup(self._d.cleanup)
        self.tmp = self._d.name
        self.n = 0

    def rc(self, msg):
        self.n += 1
        return cap(msg, self.tmp, f"agent{self.n}")

    def test_fenced_commands_do_not_force_a_rewrite(self):
        block = "```bash\n" + "\n".join(f"git -C /w/x push origin feat/part{i}" for i in range(30)) + "\n```"  # ~1.2k chars, 32 lines
        self.assertEqual(self.rc("VERIFIED | sha=abc\nrun:\n" + block)[0], 0)

    def test_bang_lines_do_not_force_a_rewrite(self):
        cmds = "\n".join(f"! gh pr create --title t{i}" for i in range(25))
        self.assertEqual(self.rc("VERIFIED | sha=abc\n" + cmds)[0], 0)

    def test_prose_over_the_cap_still_blocks(self):
        rc, err = self.rc("\n".join(["narration"] * 15))
        self.assertEqual(rc, 2)
        self.assertIn("Handback too long", err)
        self.assertIn("not counting fenced code", err)

    def test_prose_beside_a_fence_is_still_counted(self):
        self.assertEqual(self.rc("\n".join(["narration"] * 12) + "\n```\nls\n```")[0], 2)

    def test_deliverable_in_a_fence_hits_the_total_ceiling(self):
        self.assertEqual(self.rc("VERIFIED\n```\n" + "x" * 4100 + "\n```")[0], 2)  # > 5 x 800 chars overall

    def test_unclosed_fence_hides_lines_but_not_the_ceiling(self):
        self.assertEqual(self.rc("VERIFIED\n```\n" + "\n".join(["l"] * 40))[0], 0)
        self.assertEqual(self.rc("VERIFIED\n```\n" + "y" * 4100)[0], 2)

    def test_one_line_fence_toggles_nothing(self):
        self.assertEqual(self.rc("```cmd```\n" + "\n".join(["narration"] * 15))[0], 2)

    def test_plain_long_message_blocks_as_before(self):
        self.assertEqual(self.rc("x" * 900)[0], 2)

    def test_terse_hook_ignores_bang_lines(self):
        filler = "! grep -n the a an just really the a an just really src " * 4
        msg = "Build fail: config missing key. Add key to config.yml. Rerun tests. Next: push branch.\n" + "\n".join([filler] * 6)
        env = {**os.environ, "TERSE_STATE_DIR": self.tmp, "TERSE_MODE": "block", "TERSE_MAX_LINES": "0", "TERSE_MAX_CHARS": "0"}
        p = subprocess.run([sys.executable, str(TERSE)], capture_output=True, text=True, env=env,
                           input=json.dumps({"last_assistant_message": msg}))
        self.assertEqual(p.stdout, "")
        p = subprocess.run([sys.executable, str(TERSE)], capture_output=True, text=True, env=env,
                           input=json.dumps({"last_assistant_message": msg.replace("! grep", "grep")}))
        self.assertEqual(json.loads(p.stdout)["decision"], "block")


if __name__ == "__main__":
    unittest.main()
