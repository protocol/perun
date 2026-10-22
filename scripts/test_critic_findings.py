#!/usr/bin/env python3
"""Tests for validate_verdict.py optional `findings` and `--artifact` (idea-critic).

Fictional artifact and verdicts, generated in a temp dir.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = ROOT / ".claude/skills/idea-critic/scripts/validate_verdict.py"
ARTIFACT = "Plan: migrate the Acme billing cron to a queue.\nRollback: none planned.\n"
BASE = {
    "verdict": "REVISE", "independence": "independent", "origin": "agent-originated",
    "claim": "c", "steelman": "s", "hats_run": "skeptic", "assumptions": "NONE",
    "better_ways": "NONE", "kill_criteria": "NONE",
    "strongest_attack_survived": "a real attack that failed because x",
    "questions_parent_must_resolve": "NONE", "user_question": "NONE",
    "dissent_ledger": "d", "remaining_risk": "r",
}
REAL = {"text": "no rollback", "class": "real", "quote": "Rollback: none planned."}


class CriticFindings(unittest.TestCase):
    def run_v(self, verdict, artifact=True, text=ARTIFACT):
        with tempfile.TemporaryDirectory() as d:
            v, a = Path(d, "v.json"), Path(d, "a.md")
            v.write_text(json.dumps({**BASE, **verdict}))
            a.write_text(text, encoding="utf-8")
            cmd = [sys.executable, str(VALIDATOR), "--file", str(v)] + (["--artifact", str(a)] if artifact else [])
            return subprocess.run(cmd, capture_output=True, text=True)

    def test_old_verdict_still_passes(self):
        self.assertEqual(self.run_v({}, artifact=False).returncode, 0)

    def test_grounded_real_finding_passes(self):
        self.assertEqual(self.run_v({"findings": [REAL]}).returncode, 0)

    def test_fabricated_quote_fails(self):
        r = self.run_v({"findings": [REAL, {**REAL, "class": "noise", "quote": "Rollback: tested nightly."}]})
        self.assertEqual(r.returncode, 1)
        self.assertIn("not in the artifact", r.stderr)

    def test_revise_needs_real_finding(self):
        noise = {**REAL, "class": "noise"}
        self.assertEqual(self.run_v({"findings": [noise]}).returncode, 1)
        self.assertEqual(self.run_v({}).returncode, 1)  # --artifact with no findings at all
        self.assertEqual(self.run_v({"verdict": "PASS_TO_USER"}).returncode, 0)

    def test_real_rule_fires_without_artifact_but_not_inline(self):
        noise = {**REAL, "class": "noise"}
        self.assertEqual(self.run_v({"findings": [noise]}, artifact=False).returncode, 1)
        self.assertEqual(self.run_v({"findings": [noise], "independence": "inline"}).returncode, 0)

    def test_bad_class_fails_without_artifact(self):
        r = self.run_v({"findings": [{**REAL, "class": "meh"}]}, artifact=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("class must be one of", r.stderr)

    def test_non_string_class_is_a_contract_error_not_a_crash(self):
        for bad in (["real"], {"a": 1}, 3, None):
            r = self.run_v({"findings": [{**REAL, "class": bad}]}, artifact=False)
            self.assertEqual(r.returncode, 1, bad)
            self.assertNotIn("Traceback", r.stderr)

    def test_short_quote_rejected(self):
        r = self.run_v({"findings": [{**REAL, "quote": "a"}]})
        self.assertEqual(r.returncode, 1)
        self.assertIn("at least 12", r.stderr)

    def test_whitespace_and_unicode_variants_match(self):
        q = {**REAL, "quote": "Plan:  migrate\nthe Acme   billing cron"}
        self.assertEqual(self.run_v({"findings": [q]}).returncode, 0)

    def test_nfc_variants_match(self):
        q = {**REAL, "quote": "Café billing cron stays"}  # precomposed
        self.assertEqual(self.run_v({"findings": [q]}, text="Café billing cron stays").returncode, 0)

    def test_unreadable_artifact_is_usage_error(self):
        with tempfile.TemporaryDirectory() as d:
            v = Path(d, "v.json")
            v.write_text(json.dumps({**BASE, "findings": [REAL]}))
            r = subprocess.run([sys.executable, str(VALIDATOR), "--file", str(v), "--artifact", str(Path(d, "none.md"))],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)


if __name__ == "__main__":
    unittest.main()
