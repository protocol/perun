#!/usr/bin/env python3
"""Tests for business-ops/scripts/bizops_check.py: one per check, boundary-equal, SKIP/INCONCLUSIVE, bad input, check-removal guard. Fictional numbers, offline."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude/skills/business-ops/scripts"))
import bizops_check as B  # noqa: E402

# The skill's own worked case: $30 seat, CAC $240, 5% churn, 80% margin -> LTV $480, LTV:CAC 2.0, payback 10 months.
BASE = {"price": 30, "cac": 240, "churn": 0.05, "margin": 0.8, "cash": 120000, "net_burn": 10000}


def run(d):
    with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
        json.dump(d, f)
        f.flush()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = B.main([f.name])
    return rc, out.getvalue()


def only(limit_key, limit, **extra):
    return run({**BASE, **extra, limit_key: limit})


class Checks(unittest.TestCase):
    def test_runway(self):
        self.assertEqual(only("min_runway_months", 12)[0], 0)  # 120000 / 10000 = 12, equal passes
        rc, out = only("min_runway_months", 12.5)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL runway", out)

    def test_ltv_cac(self):
        self.assertEqual(only("min_ltv_cac", 2)[0], 0)  # 30 x 0.8 / 0.05 / 240 = 2.0 exactly
        self.assertEqual(only("min_ltv_cac", 2.01)[0], 1)

    def test_payback(self):
        self.assertEqual(only("max_payback_months", 10)[0], 0)  # 240 / (30 x 0.8) = 10 exactly
        self.assertEqual(only("max_payback_months", 9.99)[0], 1)

    def test_margin_from_unit_cost(self):
        d = {"price": 40, "unit_cost": 12}  # $28 per seat, 70%
        self.assertEqual(run({**d, "min_margin": 0.7})[0], 0)
        self.assertEqual(run({**d, "min_margin": 0.71})[0], 1)

    def test_all_pass_lists_every_check(self):
        rc, out = run({**BASE, "min_runway_months": 12, "min_ltv_cac": 2, "max_payback_months": 10, "min_margin": 0.8})
        self.assertEqual(rc, 0)
        for name in ("runway", "ltv_cac", "payback", "margin"):
            self.assertIn(f"PASS {name}", out)

    def test_missing_limit_skips_only_that_check(self):
        rc, out = only("min_ltv_cac", 2)
        self.assertEqual(rc, 0)
        self.assertIn("SKIP runway", out)
        self.assertIn("PASS ltv_cac", out)

    def test_all_skip_is_inconclusive(self):
        rc, out = run(BASE)
        self.assertEqual(rc, 3)
        self.assertIn("INCONCLUSIVE", out)
        self.assertNotIn("PASS", out)

    def test_binds_by_key_not_order(self):
        rc, _ = run(dict(reversed(list({**BASE, "min_ltv_cac": 2}.items()))))
        self.assertEqual(rc, 0)


class BadInput(unittest.TestCase):
    def err(self, d):
        rc, out = run(d)
        self.assertEqual(rc, 2, out)
        self.assertTrue(out.startswith("ERROR "), out)

    def test_missing_input_for_stated_limit(self):
        self.err({"min_runway_months": 6, "cash": 5})

    def test_not_an_object(self):
        self.err([1, 2])

    def test_non_number(self):
        self.err({**BASE, "min_runway_months": 6, "cash": "lots"})
        self.err({**BASE, "min_runway_months": True})

    def test_zero_divisor(self):
        self.err({**BASE, "min_runway_months": 6, "net_burn": 0})
        self.err({**BASE, "min_ltv_cac": 2, "churn": 0})

    def test_nonpositive_payback_margin(self):
        self.err({**BASE, "max_payback_months": 10, "margin": 0})

    def test_overflow_and_nonfinite(self):
        self.err({**BASE, "min_runway_months": 6, "cash": 10**400})
        rc, out = run({**BASE, "min_runway_months": 6, "cash": float("inf")})
        self.assertEqual((rc, out.startswith("ERROR ")), (2, True))

    def test_margin_out_of_range(self):
        self.err({**BASE, "min_margin": 0.5, "margin": 1.5})
        self.err({**BASE, "min_margin": 0.5, "margin": -0.1})
        self.err({"price": 10, "unit_cost": 12, "min_margin": 0.5})  # derived margin < 0

    def test_margin_bounds_inclusive(self):
        self.assertEqual(run({"margin": 1, "min_margin": 1})[0], 0)
        self.assertEqual(run({"margin": 0, "min_margin": 0})[0], 0)

    def test_bad_price_or_unit_cost(self):
        self.err({"price": 0, "unit_cost": 0, "min_margin": 0.5})
        self.err({"price": 40, "unit_cost": -1, "min_margin": 0.5})

    def test_margin_conflicts_with_price_and_unit_cost(self):
        self.err({"price": 40, "unit_cost": 12, "margin": 0.8, "min_margin": 0.5})
        self.assertEqual(run({"price": 40, "unit_cost": 12, "margin": 0.7, "min_margin": 0.7})[0], 0)

    def test_deeply_nested_json(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            f.write("[" * 200000)
            f.flush()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(B.main([f.name]), 2)
            self.assertTrue(out.getvalue().startswith("ERROR "))

    def test_reads_stdin_without_path(self):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps({**BASE, "min_ltv_cac": 2}))), contextlib.redirect_stdout(out):
            self.assertEqual(B.main([]), 0)
        self.assertIn("PASS ltv_cac", out.getvalue())

    def test_bad_json_and_missing_file(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(B.main(["/nonexistent/in.json"]), 2)
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            f.write("{nope")
            f.flush()
            with contextlib.redirect_stdout(out):
                self.assertEqual(B.main([f.name]), 2)


class Guards(unittest.TestCase):
    def test_check_set_pinned(self):
        # Fails if a check is removed (or renamed) without updating the skill and this test.
        self.assertEqual([c[0] for c in B.CHECKS], ["runway", "ltv_cac", "payback", "margin"])

    def test_quotes_are_verbatim_skill_sentences(self):
        skill = (ROOT / ".claude/skills/business-ops/SKILL.md").read_text()
        for c in B.CHECKS:
            self.assertIn(c[4], skill, c[0])


if __name__ == "__main__":
    unittest.main()
