#!/usr/bin/env python3
"""repeat_poll_guard (nudge, never block) and subagent_brief_lint (dead-tool briefs). Offline; cache dir is a temp dir."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

S = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"


def run(script, payload, cache, **env):
    e = {**os.environ, "XDG_CACHE_HOME": cache, "CLAUDE_PROJECT_DIR": cache, **env}
    inp = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, "-I", str(S / script)], input=inp, capture_output=True, text=True, env=e)


class Poll(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.c = self.td.name

    def tearDown(self):
        self.td.cleanup()

    def poll(self, cmd, sid="s1", **env):
        return run("repeat_poll_guard.py", {"tool_name": "Bash", "session_id": sid, "tool_input": {"command": cmd}}, self.c, **env)

    def test_nudge_on_fourth_then_every_tenth(self):
        cmd = "gh pr checks 123 --repo example/x"
        outs = [self.poll(cmd) for _ in range(15)]
        self.assertTrue(all(o.returncode == 0 for o in outs))
        hit = [i + 1 for i, o in enumerate(outs) if o.stdout]
        self.assertEqual(hit, [4, 14])
        self.assertIn("additionalContext", json.loads(outs[3].stdout)["hookSpecificOutput"])

    def test_whitespace_normalized_and_sessions_separate(self):
        for i in range(3):
            self.poll("gh   pr checks 123\n --repo example/x")
        self.assertTrue(self.poll("gh pr checks 123 --repo example/x").stdout)
        self.assertFalse(self.poll("gh pr checks 123 --repo example/x", sid="other").stdout)

    def test_short_and_other_commands_not_counted(self):
        self.assertFalse(any(self.poll("git status").stdout for _ in range(6)))
        self.assertFalse(any(self.poll(f"echo run number {i} of the batch").stdout for i in range(6)))

    def test_max_env(self):
        outs = [self.poll("gh pr checks 123 --repo example/x", REPEAT_POLL_MAX="1") for _ in range(2)]
        self.assertTrue(outs[1].stdout and not outs[0].stdout)

    def test_never_blocks_on_bad_input(self):
        for bad in ("", "not json", "[]", '{"tool_input": null}', '{"session_id": "s", "tool_input": {"command": 5}}'):
            self.assertEqual(run("repeat_poll_guard.py", bad, self.c).returncode, 0, bad)
        self.assertEqual(run("repeat_poll_guard.py", {"tool_name": "Bash", "session_id": "s", "tool_input": {"command": "x" * 30}}, "/proc/none/x").returncode, 0)


class Brief(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.c = self.td.name

    def tearDown(self):
        self.td.cleanup()

    def brief(self, prompt, mode=None, **kw):
        env = {"BRIEF_LINT_MODE": mode} if mode else {}
        return run("subagent_brief_lint.py", {"tool_name": "Agent", "tool_input": {"prompt": prompt, **kw}}, self.c, **env)

    def test_flags_dead_tools_once(self):
        for p in ("Wait with the Monitor tool until CI ends.", "Then use Monitor to watch the log.", "Run it with the bash tool.", "Call `bash` to build.", "tool: grep"):
            r = self.brief(p)
            self.assertEqual(r.returncode, 2, p)
            self.assertTrue(r.stderr, p)
            self.assertEqual(self.brief(p).returncode, 0, "same brief resent must pass: " + p)

    def test_plain_prose_passes(self):
        for p in ("Write a bash script that reads the file and greps for errors; run bash -c 'true'.", "Use Bash and Read. Monitor the output of the job yourself.",
                  "Edit the grep config, then write tests.", "Read the doc at /usr/bin/bash."):
            self.assertEqual(self.brief(p).returncode, 0, p)

    def test_warn_mode_advises(self):
        r = self.brief("Use the Monitor tool.", mode="warn")
        self.assertEqual(r.returncode, 0)
        self.assertIn("Monitor", json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"])

    def test_agent_def_that_lists_tool_is_allowed(self):
        d = pathlib.Path(self.c) / ".claude/agents"
        d.mkdir(parents=True)
        (d / "watcher.md").write_text("---\nname: watcher\ntools: Bash, Monitor\n---\nbody\n")
        self.assertEqual(self.brief("Use the Monitor tool.", subagent_type="watcher").returncode, 0)
        self.assertEqual(self.brief("Use the Monitor tool now.", subagent_type="../watcher").returncode, 2)

    def test_non_utf8_agent_file_does_not_crash(self):
        d = pathlib.Path(self.c) / ".claude/agents"
        d.mkdir(parents=True)
        (d / "odd.md").write_bytes(b"---\ntools: \xff\xfe\n---\n")
        r = self.brief("Use the Monitor tool.", subagent_type="odd")
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_other_input_silent(self):
        for bad in ("", "nope", '{"tool_name": "Bash", "tool_input": {"prompt": "use Monitor tool"}}', '{"tool_name": "Agent", "tool_input": {}}'):
            r = run("subagent_brief_lint.py", bad, self.c)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""), bad)


if __name__ == "__main__":
    unittest.main()
