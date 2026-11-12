#!/usr/bin/env python3
"""agent_workflow_injection.py review fixes: head.sha is not outsider text, flags before -p, multi-line allowedTools, CLI head checkout, workflow_run and env text."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts"))
import agent_workflow_injection as aw  # noqa: E402

ISS = "name: t\non:\n  issues:\n    types: [opened]\n"
PRT = "name: t\non:\n  pull_request_target:\n  issue_comment:\n"
AG = "      - uses: anthropics/claude-code-action@v1\n"


def rules(src):
    return sorted({r[2] for r in aw.scan("w.yml", src)})


class T(unittest.TestCase):
    def test_head_sha_quiet_ref_label_flagged(self):
        mk = lambda e: ISS + "jobs:\n  a:\n    steps:\n" + AG + f"        with:\n          prompt: ${{{{ github.event.pull_request.head.{e} }}}}\n"  # noqa: E731
        for ok in ("sha", "repo.full_name"):
            self.assertEqual(rules(mk(ok)), [], ok)
        for bad in ("ref", "label"):
            self.assertEqual(rules(mk(bad)), ["agent-untrusted-input"], bad)

    def test_flags_before_p(self):
        mk = lambda c: ISS + f"jobs:\n  a:\n    steps:\n      - run: {c}\n        env:\n          B: ${{{{ github.event.issue.body }}}}\n"  # noqa: E731
        self.assertEqual(rules(mk('claude --model opus -p "$B"')), ["agent-untrusted-input"])
        self.assertEqual(rules(mk("codex --full-auto exec x")), ["agent-untrusted-input"])
        self.assertEqual(rules(mk('echo "claude is great"')), [])

    def test_multiline_allowed_tools(self):
        mk = lambda tools: ISS + "jobs:\n  a:\n    steps:\n" + AG + f"        with:\n          claude_args: |\n            --allowedTools\n            {tools}\n          prompt: hi\n"  # noqa: E731
        self.assertEqual(rules(mk("Bash,Read")), ["agent-broad-tools"])
        self.assertEqual(rules(mk("Bash(gh issue view:*),Read")), [])
        rows = aw.scan("w.yml", mk("Bash"))
        self.assertEqual(rows[0][1], 11)

    def test_cli_head_checkout(self):
        mk = lambda c, t=PRT: t + f"jobs:\n  a:\n    steps:\n      - run: {c}\n" + AG  # noqa: E731
        for c in ("gh pr checkout ${{ github.event.issue.number }}", "git fetch origin pull/7/head:pr", "git checkout ${{ github.head_ref }}"):
            self.assertIn("agent-head-checkout", rules(mk(c)), c)
        self.assertEqual(rules(mk("git fetch origin main")), [])
        self.assertEqual(rules(mk("gh pr checkout 5", "name: t\non: pull_request\n")), [])

    def test_workflow_run_text(self):
        mk = lambda e: "name: t\non:\n  workflow_run:\n    workflows: [ci]\njobs:\n  a:\n    steps:\n" + AG + f"        with:\n          prompt: ${{{{ github.event.workflow_run.{e} }}}}\n"  # noqa: E731
        for bad in ("head_branch", "head_commit.message"):
            self.assertIn("agent-untrusted-input", rules(mk(bad)), bad)
        self.assertEqual(rules(mk("conclusion")), [])

    def test_env_levels(self):
        wf = ISS + "env:\n  B: ${{ github.event.issue.body }}\njobs:\n  a:\n    steps:\n" + AG
        jb = ISS + "jobs:\n  a:\n    env:\n      T: ${{ github.event.issue.title }}\n    steps:\n" + AG
        self.assertEqual(rules(wf), ["agent-untrusted-input"])
        self.assertEqual(rules(jb), ["agent-untrusted-input"])
        self.assertEqual(rules(wf.replace("github.event.issue.body", "github.event.issue.number")), [])
        self.assertEqual(rules(wf.replace(AG, "      - run: echo hi\n")), [])  # no agent step: stays quiet
        self.assertEqual(rules(ISS + "jobs:\n  a:\n    if: ${{ github.event.issue.title == 'x' }}\n    steps:\n" + AG), [])

    def test_fork_note(self):
        src = ISS + "jobs:\n  a:\n    permissions:\n      issues: write\n    steps:\n" + AG + "        with:\n          prompt: ${{ github.event.issue.title }}\n"
        self.assertIn("fork pull_request run still gets a read-only token", aw.scan("w.yml", src)[0][3])


if __name__ == "__main__":
    unittest.main()
