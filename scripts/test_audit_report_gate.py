#!/usr/bin/env python3
"""Tests: audit_report_gate.py blocks a failing audit report once and stays silent in every other case (offline)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODE = str(ROOT / ".claude/skills/deep-code-review/references/security-review-mode.md")
GATE = ROOT / ".claude/skills/deep-code-review/scripts/audit_report_gate.py"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_report_contract_lint import report  # noqa: E402  passing fixture

CITES = "\n".join(f"- src/app.py:{i}" for i in range(1, 7))
BAD = "# Audit\n| a | b |\n|---|---|\n| x | y |\n" + CITES + "\n"


def run(inp, raw=None, args=(), tmp=None):
    env = dict(os.environ, TMPDIR=tmp) if tmp else None
    p = subprocess.run([sys.executable, "-I", str(GATE), *args], input=raw if raw is not None else json.dumps(inp), capture_output=True, text=True, env=env)
    return p.returncode, p.stdout


HUMAN = json.dumps({"type": "user", "message": {"content": "audit this app"}}) + "\n"


class Gate(unittest.TestCase):
    def rd(self):
        b = {"type": "tool_use", "name": "Read", "input": {"file_path": MODE}}
        return json.dumps({"type": "assistant", "message": {"content": [b]}}) + "\n"

    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.root = Path(self.d.name)
        (self.root / "src").mkdir()
        (self.root / "src/app.py").write_text("a\nrun(escape(x))\nc\n")
        self.tp = self.root / "t.jsonl"
        self.tp.write_text(HUMAN + self.rd())

    def tearDown(self):
        self.d.cleanup()

    def inp(self, msg=BAD, **kw):
        d = {"cwd": str(self.root), "transcript_path": str(self.tp), "last_assistant_message": msg, "stop_hook_active": False}
        d.update(kw)
        return d

    def test_active_flag(self):
        self.assertEqual(run(self.inp(stop_hook_active=True)), (0, ""))

    def test_few_cites_missing_transcript(self):
        self.assertEqual(run(self.inp("hi src/a.py:1", transcript_path=str(self.root / "none"))), (0, ""))

    def test_no_mode_read(self):
        self.tp.write_text('{"type":"user","message":"hello"}\n')
        self.assertEqual(run(self.inp()), (0, ""))

    def test_skill_text_only_no_read(self):
        self.tp.write_text(HUMAN + json.dumps({"type": "user", "isMeta": True, "message": {"content": "see references/security-review-mode.md"}}) + "\n")
        self.assertEqual(run(self.inp()), (0, ""))

    def test_read_before_last_prompt(self):
        self.tp.write_text(self.rd() + HUMAN)
        self.assertEqual(run(self.inp()), (0, ""))

    def test_read_after_prompt_blocks(self):
        self.tp.write_text(HUMAN + self.rd())
        self.assertEqual(json.loads(run(self.inp())[1])["decision"], "block")

    def test_block_on_failing_report(self):
        rc, out = run(self.inp())
        self.assertEqual(rc, 0)
        r = json.loads(out)
        self.assertEqual(r["decision"], "block")
        self.assertIn("missing-table", r["reason"])
        self.assertIn("review_checks.sh --full", r["reason"])

    def test_passing_report(self):
        self.assertEqual(run(self.inp(report())), (0, ""))

    def test_malformed_stdin(self):
        self.assertEqual(run(None, raw="{nope"), (0, ""))

    def test_transcript_fallback(self):
        line = {"type": "assistant", "message": {"content": [{"type": "text", "text": BAD}]}}
        self.tp.write_text(HUMAN + self.rd() + json.dumps(line) + "\n")
        i = self.inp()
        del i["last_assistant_message"]
        rc, out = run(i)
        self.assertEqual(json.loads(out)["decision"], "block")

    def post(self, name, **inp):
        return {"session_id": "s-1", "tool_name": name, "tool_input": inp}

    def test_mark_read_creates_marker_other_does_not(self):
        run(self.post("Read", file_path="/x/references/other.md"), args=["--mark"], tmp=str(self.root))
        self.assertFalse((self.root / "perun-audit-mode-s-1").exists())
        run(self.post("Read", file_path=MODE), args=["--mark"], tmp=str(self.root))
        self.assertTrue((self.root / "perun-audit-mode-s-1").exists())

    def test_marker_without_transcript_blocks_and_clears(self):
        mk = self.root / "perun-audit-mode-s-1"
        mk.write_text("")
        i = self.inp(transcript_path=str(self.root / "none"), session_id="s-1")
        rc, out = run(i, tmp=str(self.root))
        self.assertEqual(json.loads(out)["decision"], "block")
        self.assertFalse(mk.exists())

    def test_no_transcript_no_marker_allows(self):
        self.assertEqual(run(self.inp(transcript_path=str(self.root / "none"), session_id="s-1"), tmp=str(self.root)), (0, ""))

    def test_hook_command_creates_marker(self):
        h = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]["PostToolUse"][0]
        self.assertEqual(h["matcher"], "Read")
        env = dict(os.environ, TMPDIR=str(self.root), CLAUDE_PLUGIN_ROOT=str(ROOT))
        subprocess.run(["sh", "-c", h["hooks"][0]["command"]], input=json.dumps(self.post("Read", file_path=MODE)), text=True, env=env)
        self.assertTrue((self.root / "perun-audit-mode-s-1").exists())

    def test_copy_and_bash_do_not_mark_or_trigger(self):
        cp = self.root / "references"
        cp.mkdir()
        (cp / "security-review-mode.md").write_text("x")
        run(self.post("Read", file_path=str(cp / "security-review-mode.md")), args=["--mark"], tmp=str(self.root))
        run(self.post("Bash", command="cat " + MODE), args=["--mark"], tmp=str(self.root))
        self.assertFalse((self.root / "perun-audit-mode-s-1").exists())
        b = {"type": "tool_use", "name": "Read", "input": {"file_path": str(cp / "security-review-mode.md")}}
        c = {"type": "tool_use", "name": "Bash", "input": {"command": "cat " + MODE}}
        self.tp.write_text(HUMAN + "".join(json.dumps({"type": "assistant", "message": {"content": [x]}}) + "\n" for x in (b, c)))
        self.assertEqual(run(self.inp()), (0, ""))

    def test_lint_systemexit_fails_open(self):
        import importlib.util
        import io
        from unittest import mock
        spec = importlib.util.spec_from_file_location("gate", GATE)
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        sys.path.insert(0, str(GATE.parent))
        import report_contract_lint
        out = io.StringIO()
        with mock.patch.object(report_contract_lint, "lint", side_effect=SystemExit(2)), mock.patch("sys.stdin", io.StringIO(json.dumps(self.inp()))), mock.patch("sys.stdout", out):
            g.main()
        self.assertEqual(out.getvalue(), "")

    def test_hooks_json(self):
        h = json.loads((ROOT / "hooks/hooks.json").read_text())
        cmd = h["hooks"]["Stop"][0]["hooks"][0]["command"]
        rel = cmd.split("${CLAUDE_PLUGIN_ROOT}/")[1].split('"')[0]
        self.assertTrue((ROOT / rel).is_file())


if __name__ == "__main__":
    unittest.main()
