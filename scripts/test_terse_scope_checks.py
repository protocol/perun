#!/usr/bin/env python3
"""Offline tests for terse_reply_check.py (Stop hook) and scope_creep_check.py."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

S = Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"
HOOK, SCOPE = S / "terse_reply_check.py", S / "scope_creep_check.py"

PROSE = ("Sure, I would be happy to help with that. Basically, the build is failing because "
         "the config file is really missing a required key, and perhaps the simplest fix is to "
         "add the key to the file. Please let me know if you would like me to make the change.")
TERSE = "Build fail: config missing key. Add key to config.yml. Rerun tests. Next: push branch."


def hook(msg, active=False, env=None):
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(
        {"last_assistant_message": msg, "stop_hook_active": active}),
        capture_output=True, text=True, env={**os.environ, **(env or {})})
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout) if p.stdout.strip() else None


class Terse(unittest.TestCase):
    def test_prose_blocked(self):
        r = hook(PROSE, env={"TERSE_MODE": "block"})  # default mode only reminds (test_reply_budget_prevention.py)
        self.assertEqual(r["decision"], "block")
        self.assertIn("Rewrite", r["reason"])

    def test_terse_allowed(self):
        self.assertIsNone(hook(TERSE))

    def test_code_blocks_inline_and_errors_ignored(self):
        code = "```\n" + "the a an just really the a an just really " * 20 + "\n```"
        msg = TERSE + "\n" + code + "\n`the a an just really` and\n> the a an just really the\nError: the a an the file"
        self.assertIsNone(hook(msg))

    def test_table_and_indented_code_ignored(self):
        filler = "the a an just really the a an just really " * 5
        table = "\n".join(f"| {filler} | {filler} |" for _ in range(6))
        indented = "\n".join("    " + filler for _ in range(6)) + "\n" + "\t" + filler
        self.assertIsNone(hook(TERSE + "\n" + table))
        self.assertIsNone(hook(TERSE + "\n" + indented))

    def test_bullet_markers_not_counted(self):
        self.assertIsNone(hook("\n".join(f"- item{i} fails: config key missing" for i in range(10))))

    def test_loop_guard(self):
        self.assertIsNone(hook(PROSE, active=True))

    def test_threshold_env(self):
        self.assertIsNone(hook(PROSE, env={"TERSE_MAX_RATIO": "0.9"}))

    def test_fail_open(self):
        p = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout), (0, ""))


def sh(d, *a):
    subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@example.com", *a],
                   check=True, capture_output=True)


class Scope(unittest.TestCase):
    def test_report(self):
        with tempfile.TemporaryDirectory() as d:
            sh(d, "init", "-q", "-b", "main")
            (Path(d) / "package.json").write_text(json.dumps({"dependencies": {"left": "1"}}))
            (Path(d) / "requirements.txt").write_text("flask==2\n")
            sh(d, "add", "."); sh(d, "commit", "-qm", "base")
            (Path(d) / "package.json").write_text(json.dumps({"dependencies": {"left": "1", "right": "2"}}))
            (Path(d) / "requirements.txt").write_text("flask==2\nrequests>=2\n# note\n")
            (Path(d) / "a.py").write_text("class Base:\n    pass\n\nclass Only(Base):\n    pass\n\nclass Alone:\n    pass\n")
            sh(d, "add", "."); sh(d, "commit", "-qm", "feat")
            p = subprocess.run([sys.executable, str(SCOPE), "HEAD~1", "HEAD", "--repo", d],
                               capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        o = p.stdout
        self.assertIn("scope: 3 files touched, 1 new", o)
        self.assertIn("new file: a.py", o)
        self.assertIn("new dependency: right (package.json)", o)
        self.assertIn("new dependency: requests (requirements.txt)", o)
        self.assertNotIn("flask", o)
        self.assertIn("Base (a.py) has exactly one implementation", o)
        self.assertNotIn("Alone (", o)

    def test_bad_range_exits_zero(self):
        p = subprocess.run([sys.executable, str(SCOPE), "nope", "nope2"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertIn("skipped", p.stdout)


class Install(unittest.TestCase):
    def run_install(self, *flags):
        d = tempfile.mkdtemp()
        p = subprocess.run(["bash", str(S.parents[3] / "install.sh"), *flags, d], capture_output=True,
                           text=True, env={**os.environ, "DCR_NO_PROBE": "1"})
        return p, Path(d)

    def test_flag_writes_snippet(self):
        p, d = self.run_install("--with-delivery", "--with-terse-replies")
        self.assertEqual(p.returncode, 0, p.stderr)
        snip = json.loads((d / ".claude/settings.terse-replies.json.new").read_text())
        self.assertIn("terse_reply_check.py", snip["hooks"]["Stop"][0]["hooks"][0]["command"])
        self.assertTrue((d / ".claude/skills/agentic-delivery/scripts/terse_reply_check.py").exists())

    def test_flag_needs_delivery(self):
        p, d = self.run_install("--with-terse-replies")
        self.assertNotEqual(p.returncode, 0)
        self.assertFalse((d / ".claude/settings.terse-replies.json.new").exists())


if __name__ == "__main__":
    unittest.main()
