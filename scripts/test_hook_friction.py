#!/usr/bin/env python3
"""Hook-friction fixes: handback cap miscount and release valve, resume nudge text, tier_gate missing file,
lockfile-only review skip, and the flake-throttling method in the tests reference. Offline, temp dirs only."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
import handback_cap as hc  # noqa: E402
import lane_resume_nudge as ln  # noqa: E402


class Cap(unittest.TestCase):
    def test_blank_lines_and_link_urls_not_counted(self):
        msg = "\n\n".join(["k=v"] * 9)  # 17 lines raw, 9 counted
        self.assertFalse(hc._shape(msg)[2])
        link = "[" + "t" * 10 + "](https://example.com/" + "p" * 900 + ")"
        self.assertFalse(hc._shape("see " + link)[2])

    def test_real_overlength_still_blocked(self):
        self.assertTrue(hc._shape("\n".join(["k=v"] * 11))[2])

    def test_cap_not_loosened(self):
        self.assertEqual(hc.MAX_BLOCKS, 3)

    def test_long_url_message_still_blocked_at_copy_ceiling(self):
        link = "[t](https://example.com/" + "p" * (hc.MAX_CHARS * hc.COPY_FACTOR) + ")"
        self.assertTrue(hc._shape("k=v " + link)[2])


class Text(unittest.TestCase):
    def test_resume_text_warns_cap_does_not_reset(self):
        src = (SC / "lane_resume_nudge.py").read_text()
        self.assertIn("does not reset on resume", src)
        self.assertIn("fresh lane is better", src)
        self.assertIn("does not reset on resume", (ROOT / ".claude/skills/agentic-delivery/references/operating-discipline.md").read_text())

    def test_flake_method_in_tests_reference(self):
        t = (ROOT / ".claude/skills/deep-code-review/references/testing-situational.md").read_text()
        self.assertIn("Reproduce a suspected flake under CPU throttling", t)
        self.assertIn("hydration before click", t)


class Gates(unittest.TestCase):
    def test_tier_gate_missing_tiers_file_is_clear_not_a_fail(self):
        r = subprocess.run([sys.executable, str(SC / "tier_gate.py"), "--tiers", "/nonexistent/x.tsv", "--classify", "a"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("cannot read tiers file", r.stderr)
        self.assertNotIn("FAIL", r.stdout + r.stderr)

    def gate(self, files, flag, audit, oid="a" * 40):
        with tempfile.TemporaryDirectory() as d:
            gh = Path(d, "gh")
            fl = [f if isinstance(f, dict) else {"path": f} for f in files]
            gh.write_text(f"#!/bin/sh\necho '{json.dumps({'files': fl, 'headRefOid': oid})}'\n")
            gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
            Path(d, "p.json").write_text(json.dumps({"review_gate": "enforce", "lockfile_skip_review": flag}))
            env = {**os.environ, "GH": str(gh), "REVIEW_DIR": d + "/rev", "PERUN_POLICY": d + "/p.json"}
            args = ["check", "7", "--head", "a" * 40] + (["--audit-clean"] if audit else [])
            return subprocess.run([sys.executable, str(SC / "review_gate.py"), *args], env=env, capture_output=True, text=True).returncode

    def test_lockfile_skip(self):
        self.assertEqual(self.gate(["package-lock.json", "web/yarn.lock"], "on", True), 0)
        self.assertEqual(self.gate(["package-lock.json"], "off", True), 1)  # default off
        self.assertEqual(self.gate(["package-lock.json"], "on", False), 1)  # audit not asserted clean
        self.assertEqual(self.gate(["package-lock.json", "src/a.py"], "on", True), 1)

    def test_lockfile_skip_fails_closed(self):
        self.assertEqual(self.gate(["package-lock.json"], "on", True, oid="b" * 40), 1)  # head moved
        self.assertEqual(self.gate(["package-lock.json"] * 100, "on", True), 1)  # list may be truncated
        self.assertEqual(self.gate([{"path": "yarn.lock", "previousFilename": "src/a.py"}], "on", True), 1)  # rename source
        self.assertEqual(self.gate([{"path": "yarn.lock", "previousFilename": "old/yarn.lock"}], "on", True), 0)
        self.assertEqual(self.gate(["my-yarn.lock"], "on", True), 1)  # exact basename only


if __name__ == "__main__":
    unittest.main()
