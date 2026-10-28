"""finding_guard.py: deny a duplicate `gh issue create`, explicit override, fail open on tool error."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/finding_guard.py"
HIT = '[{"number":5,"title":"Queue stalls after retry timeout","state":"CLOSED","url":"https://example.com/5"}]'
CREATE = 'gh issue create --title "Queue stalls after retry timeout" --body x'


class T(unittest.TestCase):
    def hook(self, cmd, gh_out="[]", gh_rc=0, tool="Bash"):
        d = tempfile.mkdtemp()
        gh = pathlib.Path(d, "gh")
        gh.write_text(f"#!/bin/sh\n[ {gh_rc} -ne 0 ] && exit {gh_rc}\necho '{gh_out}'\n")
        gh.chmod(0o755)
        env = {**os.environ, "PATH": f"{d}:{os.environ['PATH']}", "PERUN_FINDING_LOG": f"{d}/force.log"}
        r = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps({"tool_name": tool, "tool_input": {"command": cmd}}),
                           capture_output=True, text=True, env=env)
        return r, pathlib.Path(d, "force.log")

    def test_denies_duplicate_and_names_it(self):
        r, _ = self.hook(CREATE, HIT)
        self.assertEqual(r.returncode, 2)
        self.assertIn("#5 [CLOSED]", r.stderr)

    def test_allows_when_no_match(self):
        self.assertEqual(self.hook(CREATE)[0].returncode, 0)

    def test_explicit_override_allows_and_logs_reason(self):
        r, log = self.hook(CREATE + " # finding-force: distinct root cause", HIT)
        self.assertEqual(r.returncode, 0)
        self.assertIn("distinct root cause", log.read_text())

    def test_fail_open_on_search_error_and_garbage(self):
        r, _ = self.hook(CREATE, HIT, gh_rc=1)
        self.assertEqual((r.returncode, "allowing" in r.stderr), (0, True))
        r = subprocess.run([sys.executable, str(SCRIPT)], input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)

    def test_ignores_other_commands_tools_and_untitled_creates(self):
        for cmd, tool in (("gh issue list --search queue", "Bash"), ("gh issue create --body x", "Bash"), (CREATE, "Edit")):
            self.assertEqual(self.hook(cmd, HIT, tool=tool)[0].returncode, 0, cmd)


if __name__ == "__main__":
    unittest.main()
