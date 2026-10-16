#!/usr/bin/env python3
"""Offline tests for agentic-delivery comms_guard.py: body extraction per tool form, deny-once-then-allow, fail-open, wiring."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, ".claude/skills/agentic-delivery/scripts/comms_guard.py")
TEMPLATE = os.path.join(ROOT, ".claude/skills/agentic-delivery/templates/operating-layer.settings.json")
sys.path.insert(0, os.path.dirname(GUARD))
import comms_guard as G  # noqa: E402

BAD = "Hope you are well! Just wanted to share a quick update on the migration. " + "It is going well and the team is aligned. " * 8
GOOD = "Migration: 3 of 5 services moved (was 1); finish 2026-10-27.\nAsk: none.\n"


def bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/"}


def run(payload, env=None, guard=GUARD, raw=None):
    e = dict(os.environ, **(env or {}))
    p = subprocess.run([sys.executable, guard], input=raw if raw is not None else json.dumps(payload), capture_output=True, text=True, env=e)
    return p.returncode, p.stdout


class Extract(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        with open(os.path.join(self.d, "b.md"), "w") as f:
            f.write("File body")
        with open(os.path.join(self.d, "b.json"), "w") as f:
            json.dump({"title": "t", "body": "JSON file body"}, f)

    def ex(self, cmd):
        return G.extract("Bash", {"command": cmd}, self.d)

    def test_gh_pr_body_forms(self):
        cases = {
            "gh pr create --title t --body \"$(cat <<'EOF'\nHeredoc \"quoted\" body\n\nPara two\nEOF\n)\"": 'Heredoc "quoted" body\n\nPara two',
            'gh pr create --title t --body "Plain \\"dq\\" body"': 'Plain "dq" body',
            "gh pr edit 12 --body 'single quoted'": "single quoted",
            "gh pr create --body=simple": "simple",
            "gh pr create -b 'short flag'": "short flag",
            "gh pr create --body-file b.md": "File body",
            f"gh pr create -F {self.d}/b.md": "File body",
            "gh pr create -F - <<'EOF'\nstdin body\nEOF": "stdin body",
            "gh pr create --body \"$(cat b.md)\"": "File body",
            "git commit -m \"$(cat <<'EOF'\nmsg\nEOF\n)\" && gh pr create --body \"$(cat <<'EOF'\nreal body\nEOF\n)\"": "real body",
        }
        for cmd, body in cases.items():
            self.assertEqual(self.ex(cmd), ("pr", body), cmd)

    def test_kinds_by_tool(self):
        self.assertEqual(self.ex("gh pr comment 5 --body 'c'"), ("message", "c"))
        self.assertEqual(self.ex("gh issue create --title x --body 'i'"), ("message", "i"))
        self.assertEqual(self.ex("gh issue comment 3 -b 'ic'"), ("message", "ic"))
        self.assertEqual(self.ex("gh release create v1 --notes 'rn'"), ("release", "rn"))
        self.assertEqual(self.ex("gh release edit v1 --notes-file b.md"), ("release", "File body"))

    def test_rest_forms(self):
        url = "https://api.github.com/repos/o/r"
        cases = {
            f"curl -s -X POST {url}/pulls -d '{{\"title\":\"t\",\"body\":\"curl body\"}}'": ("pr", "curl body"),
            f"curl -X POST {url}/issues -d @{self.d}/b.json": ("message", "JSON file body"),
            f"curl -X POST \\\n  {url}/issues/7/comments \\\n  -d '{{\"body\":\"multi\"}}'": ("message", "multi"),
            f"curl -X PATCH {url}/pulls/9 --data-binary @b.json": ("pr", "JSON file body"),
            "gh api repos/o/r/pulls -f title=t -f body='api body'": ("pr", "api body"),
            "gh api repos/o/r/pulls -f title=t -f 'body=quoted assignment'": ("pr", "quoted assignment"),
            f"gh api repos/o/r/pulls -F body=@{self.d}/b.md": ("pr", "File body"),
            "gh api repos/o/r/pulls --input b.json": ("pr", "JSON file body"),
            f"curl -X POST {url}/pulls/4/comments -d '{{\"body\":\"review comment\"}}'": ("message", "review comment"),
        }
        for cmd, want in cases.items():
            self.assertEqual(self.ex(cmd), want, cmd)

    def test_not_covered_or_unreadable_commands_return_none(self):
        for cmd in ("gh pr create --fill", "gh pr list --state all", "gh api repos/o/r/pulls?state=all", "curl -s https://api.github.com/repos/o/r/pulls",
                    "ls -la", "gh pr create --body-file /nonexistent/x.md", "curl -X POST https://api.github.com/repos/o/r/pulls -d 'title=x'",
                    "grep -rn \"gh pr create --body\" .", "gh pr create --body ''"):
            self.assertIsNone(self.ex(cmd), cmd)
        self.assertIsNone(G.extract("Read", {"file_path": "/x"}))
        self.assertIsNone(G.extract("Bash", {"command": 5}))

    def test_linear_mcp_tools_from_any_server_name(self):
        for name, kind in (("mcp__claude_ai_Linear__save_status_update", "status"), ("mcp__claude_ai_Linear__save_comment", "message"),
                           ("mcp__plugin_linear_linear__save_comment", "message"), ("mcp__linear__save_status_update", "status")):
            self.assertEqual(G.extract(name, {"body": "b"}), (kind, "b"), name)
        for name in ("mcp__claude_ai_Linear__save_issue", "mcp__claude_ai_Notion__save_comment", "mcp__claude_ai_Linear__list_comments"):
            self.assertIsNone(G.extract(name, {"body": "b"}), name)
        self.assertIsNone(G.extract("mcp__claude_ai_Linear__save_comment", {"issueId": "x"}))


class Decision(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.env = {}

    def test_warns_with_exact_fixes_and_never_blocks(self):
        payload = {"tool_name": "mcp__claude_ai_Linear__save_comment", "tool_input": {"issueId": "x", "body": BAD}}
        rc, out = run(payload, self.env)
        self.assertEqual(rc, 0)
        res = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(res["hookEventName"], "PreToolUse")
        self.assertNotIn("permissionDecision", res)  # advisory: the write always goes ahead
        self.assertRegex(res["additionalContext"], r"FAIL lead L1: .*Fix: ")
        self.assertIn("advisory", res["additionalContext"])
        self.assertEqual(run(payload, self.env)[1], out)  # no ledger: the same text warns again, never blocks

    def test_a_draft_that_meets_the_bar_passes_silently(self):
        self.assertEqual(run(bash(f"gh pr comment 5 --body '{GOOD}'"), self.env), (0, ""))

    def test_bash_gh_and_curl_writes_are_checked(self):
        cmds = (f"gh pr create --title t --body '{BAD}'", f"curl -X POST https://api.github.com/repos/o/r/issues -d '{json.dumps({'body': BAD})}'")
        for cmd in cmds:
            out = run(bash(cmd), self.env)[1]
            self.assertIn("additionalContext", out, cmd)
            self.assertNotIn("deny", out, cmd)

    def test_opt_out_and_uncovered_calls_and_bad_input_allow(self):
        self.assertEqual(run(bash(f"gh pr create --body '{BAD}'"), {**self.env, "PERUN_COMMS_GUARD": "off"}), (0, ""))
        self.assertEqual(run(bash("ls -la"), self.env), (0, ""))
        self.assertEqual(run(None, self.env, raw="not json"), (0, ""))
        self.assertEqual(run(None, self.env, raw=""), (0, ""))

    def test_missing_comms_skill_fails_open(self):
        lone = os.path.join(self.d, "skills/agentic-delivery/scripts")
        os.makedirs(lone)
        shutil.copy(GUARD, lone)  # no sibling communication-structure skill
        rc, out = run(bash(f"gh pr create --body '{BAD}'"), self.env, guard=os.path.join(lone, "comms_guard.py"))
        self.assertEqual((rc, out), (0, ""))


class Wiring(unittest.TestCase):
    def entry(self):
        with open(TEMPLATE, encoding="utf-8") as f:
            pre = json.load(f)["hooks"]["PreToolUse"]
        found = [e for e in pre if any("comms_guard.py" in h["command"] for h in e["hooks"])]
        self.assertEqual(len(found), 1, "the operating-layer template must wire comms_guard.py exactly once")
        return found[0]

    def test_template_wires_the_guard_fail_open(self):
        e = self.entry()
        cmd = e["hooks"][0]["command"]
        self.assertTrue(cmd.endswith("|| true"), "a missing script exits 2 and would block every Bash call without || true")
        self.assertIn('"$CLAUDE_PROJECT_DIR/.claude/skills/agentic-delivery/scripts/comms_guard.py"', cmd)
        self.assertNotIn("<", e["matcher"], "install.sh skips placeholder matchers that contain <")

    def test_matcher_matches_bash_and_the_linear_write_tools_only(self):
        m = self.entry()["matcher"]
        yes = ("Bash", "mcp__claude_ai_Linear__save_status_update", "mcp__claude_ai_Linear__save_comment", "mcp__plugin_linear_linear__save_comment", "mcp__linear__save_status_update")
        no = ("BashOutput", "Edit", "mcp__claude_ai_Linear__save_issue", "mcp__claude_ai_Linear__list_comments", "mcp__claude_ai_Notion__save_comment")
        for name in yes:
            self.assertTrue(re.search(m, name), name)
        for name in no:
            self.assertFalse(re.search(m, name), name)
        node = shutil.which("node")  # the host evaluates matchers as JavaScript regular expressions
        if node:
            js = f"const r=new RegExp({json.dumps(m)});process.stdout.write(JSON.stringify({json.dumps(yes + no)}.map(n=>r.test(n))))"
            got = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True).stdout)
            self.assertEqual(got, [True] * len(yes) + [False] * len(no))

    def test_doctor_expects_the_guard_to_be_wired(self):
        with open(os.path.join(ROOT, "scripts/perun_doctor.py"), encoding="utf-8") as f:
            self.assertIn('"comms_guard.py"', f.read())


if __name__ == "__main__":
    unittest.main()
