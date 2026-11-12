#!/usr/bin/env python3
"""agent_workflow_injection.py: positives for each rule, decoys that must stay quiet, and the review_checks.sh step. Offline, hermetic temp repo."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/deep-code-review/scripts"
sys.path.insert(0, str(SK))
import agent_workflow_injection as aw  # noqa: E402

HDR = "name: t\non:\n  issues:\n    types: [opened]\n"
CASES = {
    "title_write": (HDR + "jobs:\n  a:\n    permissions:\n      issues: write\n    steps:\n      - uses: anthropics/claude-code-action@v1\n"
                    "        with:\n          prompt: \"Triage ${{ github.event.issue.title }}\"\n", ["agent-untrusted-input"], "holds write"),
    "body_default_token": (HDR + "jobs:\n  a:\n    steps:\n      - uses: openai/codex-action@v1\n        with:\n          prompt: ${{ github.event.comment.body }}\n",
                           ["agent-untrusted-input"], "no permissions block"),
    "branch_env_cli": ("name: t\non: pull_request\npermissions:\n  contents: read\njobs:\n  a:\n    steps:\n      - run: claude -p \"$B\"\n        env:\n"
                       "          B: ${{ github.head_ref }}\n          K: ${{ secrets.API_KEY }}\n", ["agent-untrusted-input"], "secrets are in scope"),
    "prt_head_checkout": ("name: t\non:\n  pull_request_target:\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n        with:\n"
                          "          ref: ${{ github.event.pull_request.head.sha }}\n      - uses: anthropics/claude-code-action@v1\n", ["agent-head-checkout"], "no permissions block"),
    "skip_perms": (HDR + "jobs:\n  a:\n    steps:\n      - run: claude -p x --dangerously-skip-permissions\n", ["agent-broad-tools"], ""),
    "bare_bash": (HDR + "jobs:\n  a:\n    steps:\n      - uses: anthropics/claude-code-action@v1\n        with:\n          claude_args: --allowedTools \"Bash,Read\"\n",
                  ["agent-broad-tools"], ""),
    "any_user": (HDR + "jobs:\n  a:\n    steps:\n      - uses: anthropics/claude-code-action@v1\n        with:\n          allowed_non_write_users: \"*\"\n",
                 ["agent-broad-tools"], ""),
}
DECOYS = {
    "no_agent": HDR + "jobs:\n  a:\n    steps:\n      - run: echo \"${{ github.event.issue.title }}\"\n",
    "agent_trusted_inputs": HDR + "jobs:\n  a:\n    steps:\n      - uses: anthropics/claude-code-action@v1\n        with:\n"
                            "          prompt: \"Triage issue ${{ github.event.issue.number }}\"\n          claude_args: --allowedTools \"Bash(gh issue view:*),Read\"\n",
    "pr_head_checkout_pull_request": "name: t\non: pull_request\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n        with:\n"
                                     "          ref: ${{ github.event.pull_request.head.sha }}\n      - uses: anthropics/claude-code-action@v1\n",
    "prt_base_checkout": "name: t\non:\n  pull_request_target:\njobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n      - uses: anthropics/claude-code-action@v1\n",
    "commented": HDR + "jobs:\n  a:\n    steps:\n      - uses: anthropics/claude-code-action@v1\n        with:\n          # prompt: ${{ github.event.issue.body }}\n          # claude_args: --dangerously-skip-permissions\n          prompt: hi\n",
    "other_action": HDR + "jobs:\n  a:\n    steps:\n      - uses: acme/claude-notes@v1\n        with:\n          x: ${{ github.event.issue.body }}\n",
    "no_jobs": "name: t\non: push\n",
}


class T(unittest.TestCase):
    def test_positives(self):
        for name, (src, rules, reach) in CASES.items():
            with self.subTest(name):
                rows = aw.scan("w.yml", src)
                self.assertEqual(sorted({r[2] for r in rows}), rules, rows)
                self.assertTrue(all(reach in r[3] for r in rows), rows)

    def test_decoys(self):
        for name, src in DECOYS.items():
            with self.subTest(name):
                self.assertEqual(aw.scan("w.yml", src), [])

    def test_read_only_token_message(self):
        src = CASES["title_write"][0].replace("issues: write", "issues: read")
        self.assertIn("read-only", aw.scan("w.yml", src)[0][3])

    def test_unreadable_is_not_checked(self):
        r = subprocess.run([sys.executable, "-I", str(SK / "agent_workflow_injection.py")], input="nope.yml\n", capture_output=True, text=True)
        self.assertIn("\tnot-checked\t", r.stdout)

    def test_review_checks_step(self):
        with tempfile.TemporaryDirectory() as d:
            bind = Path(d, "bin"); bind.mkdir()
            for c in "git python3 bash sed grep head tail mktemp rm cat dirname perl env tr wc".split():
                p = subprocess.run(["bash", "-c", f"command -v {c}"], capture_output=True, text=True).stdout.strip()
                if p:
                    (bind / c).symlink_to(p)
            repo = Path(d, "repo"); repo.mkdir()
            g = lambda *a: subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
            g("init", "-q", "."); g("commit", "-q", "--allow-empty", "-m", "base"); g("branch", "base")
            wf = repo / ".github/workflows"; wf.mkdir(parents=True)
            (wf / "bad.yml").write_text(CASES["title_write"][0]); (wf / "ok.yml").write_text(DECOYS["agent_trusted_inputs"])
            g("add", "."); g("commit", "-q", "-m", "wf")
            env = {"PATH": str(bind), "PERUN_HEAVY_DIR": f"{d}/heavy", "HOME": d, "TMPDIR": d}
            r = subprocess.run(["bash", str(SK / "review_checks.sh"), "--base", "base"], cwd=repo, env=env, capture_output=True, text=True)
            import json
            rows = [x for x in json.loads(r.stdout) if x["tool"] == "agent-injection"]
            self.assertEqual([(x["file"], x["rule"]) for x in rows], [(".github/workflows/bad.yml", "agent-untrusted-input")], r.stderr[-500:])
            self.assertRegex(r.stderr, r"analyzers ran:.* agent-injection")


if __name__ == "__main__":
    unittest.main()
