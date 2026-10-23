#!/usr/bin/env python3
"""Tests for growth-analytics/scripts/readout_check.py: one test per rule, boundaries, bad input, and a guard that fails if a rule is removed."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", ".claude", "skills", "growth-analytics", "scripts", "readout_check.py")
RULES = {"srm", "holm", "sample_size", "run-length"}
_spec = importlib.util.spec_from_file_location("readout_check", SCRIPT)
rc_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc_mod)


def arms(c=5000, v=5000, cc=500, vc=600):
    return {"control": {"n": c, "conversions": cc}, "variant": {"n": v, "conversions": vc}}


GOOD = {"arms": arms(), "expected_split": {"control": 0.5, "variant": 0.5}, "srm_alpha": 0.001, "alpha": 0.05,
        "primary_p_values": [0.01], "planned_sample_size": 10000, "planned_days": 14, "run_days": 14}


def run(drop=(), **over):
    r = {k: v for k, v in {**GOOD, **over}.items() if k not in drop}
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "r.json")
        with open(p, "w") as f:
            json.dump(r, f)
        o = subprocess.run([sys.executable, SCRIPT, p], capture_output=True, text=True)
    status = {ln.split()[1].rstrip(":"): ln.split()[0] for ln in o.stdout.splitlines() if ln.split()[0] in ("PASS", "FAIL", "SKIP")}
    return o.returncode, status, o.stdout + o.stderr


def fails(status):
    return {k for k, v in status.items() if v == "FAIL"}


class ReadoutCheck(unittest.TestCase):
    def test_clean_readout_passes(self):
        rc, st, out = run()
        self.assertEqual((rc, st), (0, dict.fromkeys(RULES, "PASS")), out)

    def test_srm(self):
        rc, st, out = run(arms=arms(v=5400))
        self.assertEqual((rc, fails(st)), (1, {"srm"}), out)

    def test_srm_uses_named_split_not_order(self):
        # 90/10 plan, split given variant-first in JSON: still bound by name.
        rc, st, out = run(arms=arms(c=9000, v=1000), expected_split={"variant": 0.1, "control": 0.9},
                          planned_sample_size=10000)
        self.assertEqual((rc, st["srm"]), (0, "PASS"), out)

    def test_srm_skips_without_alpha(self):
        rc, st, out = run(drop=("srm_alpha",), arms=arms(v=5400))
        self.assertEqual((rc, st["srm"]), (0, "SKIP"), out)
        self.assertIn("SKIP srm: no pre-registered srm_alpha", out)

    def test_srm_alpha_equal_passes(self):
        x2 = (5000 - 5200) ** 2 / 5200 * 2
        p = rc_mod.math.erfc(rc_mod.math.sqrt(x2 / 2))
        a = arms(c=5000, v=5400)  # total 10400, expected 5200 each
        self.assertEqual(rc_mod.srm({"arms": a, "expected_split": GOOD["expected_split"], "srm_alpha": p})[0], "PASS")
        self.assertEqual(rc_mod.srm({"arms": a, "expected_split": GOOD["expected_split"], "srm_alpha": p * 1.0000001})[0], "FAIL")

    def test_holm_raw_pass_holm_fail(self):
        rc, st, out = run(primary_p_values=[0.03, 0.04, 0.045])
        self.assertEqual((rc, fails(st)), (1, {"holm"}), out)

    def test_holm_survives(self):
        rc, st, out = run(primary_p_values=[0.02, 0.03])
        self.assertEqual((rc, st["holm"]), (0, "PASS"), out)

    def test_holm_p_equal_alpha_is_not_a_win(self):
        self.assertEqual(rc_mod.holm({"alpha": 0.05, "primary_p_values": [0.05, 0.05]})[0], "PASS")

    def test_guardrails_reported_unadjusted_outside_family(self):
        rc, st, out = run(primary_p_values=[0.02], guardrail_p_values={"refund_rate": 0.04})
        self.assertEqual((rc, st["holm"]), (0, "PASS"), out)
        self.assertIn("guardrails (unadjusted): refund_rate p=0.04", out)

    def test_underpowered(self):
        rc, st, out = run(planned_sample_size=20000)
        self.assertEqual((rc, fails(st)), (1, {"sample_size"}), out)

    def test_n_equals_plan_passes(self):
        rc, st, out = run(planned_sample_size=10000)
        self.assertEqual(st["sample_size"], "PASS", out)

    def test_run_length_below_plan_fails(self):
        rc, st, out = run(run_days=13)
        self.assertEqual((rc, fails(st)), (1, {"run-length"}), out)

    def test_run_days_equals_plan_passes(self):
        rc, st, out = run(run_days=14)
        self.assertEqual(st["run-length"], "PASS", out)

    def test_no_hardcoded_seven_days(self):
        rc, st, out = run(run_days=3, planned_days=3)
        self.assertEqual((rc, st["run-length"]), (0, "PASS"), out)

    def test_every_rule_skips_when_nothing_pre_registered(self):
        rc, st, out = run(drop=("srm_alpha", "alpha", "primary_p_values", "planned_sample_size", "planned_days"))
        self.assertEqual((rc, st), (3, dict.fromkeys(RULES, "SKIP")), out)
        self.assertIn("INCONCLUSIVE: nothing pre-registered", out)

    def test_bad_input_exits_2_with_error_line(self):
        cases = [
            {"arms": {}},
            {"arms": {"a": GOOD["arms"]["control"], "b": GOOD["arms"]["variant"]}},
            {"primary_p_values": []},
            {"primary_p_values": [1.5]},
            {"expected_split": {"control": 0.5}},
            {"expected_split": {"control": 0.5, "variant": 0.4}},
            {"arms": arms(cc=6000)},
            {"run_days": "x"},
            {"arms": arms(c=10**400, v=10**400, cc=0, vc=0)},
        ]
        for over in cases:
            rc, _, out = run(**over)
            self.assertEqual(rc, 2, (over, out))
            self.assertTrue(out.startswith("ERROR "), (over, out))
            self.assertNotIn("Traceback", out)
        for k in ("arms", "run_days"):
            rc, _, out = run(drop=(k,))
            self.assertEqual((rc, out.startswith("ERROR missing key")), (2, True), out)

    def test_every_rule_still_present(self):
        # Fails if a rule is removed from the script: all four must FAIL on a readout that breaks all four.
        rc, st, out = run(arms=arms(c=400, v=500, cc=40, vc=80), primary_p_values=[0.03, 0.04, 0.045],
                          planned_sample_size=5000, planned_days=14, run_days=2)
        self.assertEqual(rc, 1, out)
        self.assertEqual(fails(st), RULES, out)


if __name__ == "__main__":
    unittest.main()
