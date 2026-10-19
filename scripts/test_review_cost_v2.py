#!/usr/bin/env python3
"""Tests for docs/bench/review-cost-v2-1019 (confirm.py, driver.py system_for, mk_v2.py). No network, no paid call."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "docs/bench/review-cost-v2-1019"
sys.path.insert(0, str(BENCH))
import confirm  # noqa: E402
import driver  # noqa: E402


class Decide(unittest.TestCase):
    def test_rule_a_needs_tokens_at_most_tk_and_ci_floor(self):
        self.assertEqual(confirm.decide(dict(d=0.02, ci=[-0.04, 0.1]), 1.0)["decision"], "keep")
        self.assertEqual(confirm.decide(dict(d=0.02, ci=[-0.06, 0.1]), 0.8)["decision"], "revert")
        self.assertEqual(confirm.decide(dict(d=-0.01, ci=[-0.04, 0.1]), 0.8)["decision"], "revert")
        self.assertEqual(confirm.decide(dict(d=0.1, ci=[-0.04, 0.2]), 1.01)["decision"], "revert")

    def test_rule_b_needs_positive_ci_and_two_x_tokens(self):
        self.assertTrue(confirm.decide(dict(d=0.1, ci=[0.001, 0.2]), 2.0)["rule_B"])
        self.assertFalse(confirm.decide(dict(d=0.1, ci=[0.0, 0.2]), 1.5)["rule_B"])
        self.assertFalse(confirm.decide(dict(d=0.1, ci=[0.05, 0.2]), 2.01)["rule_B"])


class Guards(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = confirm.LEDGER, dict(confirm.ST)
        confirm.LEDGER = Path(self.tmp.name) / "ledger.jsonl"

    def tearDown(self):
        confirm.LEDGER, st = self.old
        confirm.ST.update(st)
        self.tmp.cleanup()

    def test_spent_ignores_lines_without_cost(self):
        confirm.LEDGER.write_text('{"event": "preregistered", "sha256": "ab"}\n{"cost": 0.5}\n{"cost": 0.25}\n')
        self.assertEqual(confirm.spent(), 0.75)

    def test_cap_stops_before_any_call(self):
        confirm.LEDGER.write_text(json.dumps(dict(cost=confirm.CAP - confirm.RESERVE / 2)) + "\n")
        with self.assertRaises(confirm.Stop):
            confirm.call("x", self.tmp.name, None, "t")

    def test_quota_stops_before_any_call(self):
        confirm.ST["util"] = 0.8
        with self.assertRaises(confirm.Stop):
            confirm.call("x", self.tmp.name, None, "t")

    def test_tokens_sums_the_four_usage_fields(self):
        self.assertEqual(confirm.tokens(dict(input_tokens=1, cache_creation_input_tokens=2, cache_read_input_tokens=4, output_tokens=8, turns=3)), 15)


class Variant(unittest.TestCase):
    def test_mk_v2_builds_skill_copy_with_matching_name(self):
        with tempfile.TemporaryDirectory() as t:
            subprocess.run([sys.executable, str(BENCH / "mk_v2.py"), "V2a", t], check=True)
            s = (Path(t) / "SKILL.md").read_text()
            self.assertIn("name: deep-code-review", s.split("\n---\n")[0])
            self.assertTrue((Path(t) / "references/full-map.md").read_text().strip())
            self.assertNotIn("references/compact-mode.md", s)

    def test_system_for_strips_frontmatter_and_only_v2_arms_inline(self):
        with tempfile.TemporaryDirectory() as t:
            subprocess.run([sys.executable, str(BENCH / "mk_v2.py"), "V2a", t], check=True)
            old = driver.SKILL
            driver.SKILL = Path(t)
            try:
                body = driver.system_for("V2a")
            finally:
                driver.SKILL = old
            self.assertTrue(body.startswith("# Deep Code Review"))
            self.assertEqual(driver.system_for("TK"), driver.TK)
            self.assertIsNone(driver.system_for("BASE"))

    def test_every_variant_is_a_single_read_prompt(self):
        for v in (BENCH / "variants").glob("V2*.md"):
            t = v.read_text()
            self.assertIn("full-map.md", t)
            self.assertNotIn("compact-mode.md", t)
            self.assertLess(len(t), 4000)


class Result(unittest.TestCase):
    def test_recorded_decision_matches_the_rule(self):
        p = BENCH / "results-heldout.json"
        if not p.exists():
            self.skipTest("held-out result not recorded yet")
        r = json.loads(p.read_text())
        want = confirm.decide(r["arms"]["V2"]["minus_TK"]["f1"], r["keep"]["token_ratio_V2_over_TK"])
        self.assertEqual({k: r["keep"][k] for k in want}, want)
        self.assertLessEqual(r["spent_usd"], confirm.CAP)


if __name__ == "__main__":
    unittest.main()
