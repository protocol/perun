#!/usr/bin/env python3
"""agent_workflow_injection.py second review round: spaced pull/N/head, fork repository checkout, backslash continuation, disallowedTools, base.ref, dedupe."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/scripts"))
import agent_workflow_injection as aw  # noqa: E402

PRT = "name: t\non:\n  pull_request_target:\n  issue_comment:\n"
ISS = "name: t\non:\n  issues:\n"
AG = "      - uses: anthropics/claude-code-action@v1\n"


def rows(src):
    return aw.scan("w.yml", src)


def rules(src):
    return sorted({r[2] for r in rows(src)})


class T(unittest.TestCase):
    def test_spaced_pull_head(self):
        mk = lambda c: PRT + f"jobs:\n  a:\n    steps:\n      - run: {c}\n" + AG  # noqa: E731
        self.assertEqual(rules(mk("git fetch origin pull/${{ github.event.number }}/head:pr")), ["agent-head-checkout"])
        self.assertEqual(rules(mk("git fetch origin pull/${{ github.event.number }}/comments")), [])

    def test_fork_repository_checkout(self):
        mk = lambda w: PRT + "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n        with:\n" + w + AG  # noqa: E731
        self.assertEqual(rules(mk("          repository: ${{ github.event.pull_request.head.repo.full_name }}\n          ref: main\n")), ["agent-head-checkout"])
        self.assertEqual(rules(mk("          repository: ${{ github.repository }}\n          ref: main\n")), [])

    def test_backslash_continuation(self):
        mk = lambda c: ISS + f"jobs:\n  a:\n    steps:\n      - run: |\n{c}\n        env:\n          B: ${{{{ github.event.issue.body }}}}\n"  # noqa: E731
        self.assertEqual(rules(mk('          claude \\\n            -p "$B"')), ["agent-untrusted-input"])
        self.assertEqual(rules(mk('          echo claude \\\n            hi')), [])

    def test_disallowed_tools_quiet(self):
        mk = lambda a: ISS + "jobs:\n  a:\n    steps:\n" + AG + f"        with:\n          claude_args: {a}\n"  # noqa: E731
        self.assertEqual(rules(mk('--disallowedTools "Bash"')), [])
        self.assertEqual(rules(mk('--allowedTools "Read" --disallowedTools Bash')), [])
        self.assertEqual(rules(mk('--allowedTools "Bash,Read"')), ["agent-broad-tools"])

    def test_base_ref_quiet(self):
        mk = lambda e: ISS + "jobs:\n  a:\n    steps:\n" + AG + f"        with:\n          prompt: ${{{{ github.event.pull_request.{e} }}}}\n"  # noqa: E731
        self.assertEqual(rules(mk("base.ref")), [])
        self.assertEqual(rules(mk("head.ref")), ["agent-untrusted-input"])

    def test_one_row_per_line_across_agent_jobs(self):
        src = ISS + "env:\n  B: ${{ github.event.issue.body }}\njobs:\n  a:\n    steps:\n" + AG + "  b:\n    steps:\n" + AG
        self.assertEqual(len(rows(src)), 1)


if __name__ == "__main__":
    unittest.main()
