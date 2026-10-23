#!/usr/bin/env python3
"""Tests for product-output-safety/scripts/output_safety_check.py: one per check, SKIP/INCONCLUSIVE, bad input, quote-verbatim guard. Fictional data, offline."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude/skills/product-output-safety"
sys.path.insert(0, str(SKILL / "scripts"))
import output_safety_check as O  # noqa: E402

ROW = {"harm": "bias", "positive_control": "p", "negative_control": "n", "sliced_by": "region",
       "metric": "gap", "threshold": 0.1, "threshold_owner": "Jane Smith", "stop_condition": "block launch"}
# Hardcoded so deleting an entry from the module constant cannot silently delete its test.
CARD_KEYS = ("intended_use", "out_of_scope_uses", "subgroup_performance", "limits", "known_gaps",
             "owner", "model_version", "data_composition", "provenance", "consent")
ROW_KEYS = ("harm", "positive_control", "negative_control", "sliced_by", "metric", "threshold_owner", "stop_condition")
SWEEP_KEYS = ("prompt_injection", "data_leakage", "excess_agency")
REGIME_NAMES = ("EU AI Act", "ISO/IEC 42001", "NIST AI RMF")
CARD = {k: "x" for k in CARD_KEYS}
GOOD = {
    "harm_inventory": [{"harm": "bias", "affected": "applicants", "worst_case": "unfair denial", "owner": "Jane Smith"}],
    "rereview_on": ["Feature", "model", "data"],
    "actions": [{"action": "payout", "high_stakes": True, "human_gate": True}],
    "metrics": [{"name": "hallucination", "measured": False}],
    "test_rows": [ROW],
    "sweeps": {"prompt_injection": True, "data_leakage": True, "excess_agency": True},
    "claims_about_system": ["Residual risk is unverified."],
    "confidence_displays": ["Corroborated"],
    "confidence_tiers": {"Corroborated": "two independent sources"},
    "override_offered": True,
    "card": CARD,
    "disclosure_recommended": True,
    "legal_questions": [{"question": "must we disclose?", "routed_to": "counsel"}],
    "regimes_named": ["EU AI Act", "ISO/IEC 42001", "NIST AI RMF"],
}


def run(d):
    with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
        json.dump(d, f)
        f.flush()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = O.main([f.name])
    return rc, out.getvalue()


def bad(**kw):
    """GOOD with overrides; assert exactly the named check FAILs and nothing else."""
    rc, out = run({**GOOD, **kw})
    return rc, [ln.split()[1].rstrip(":") for ln in out.splitlines() if ln.startswith("FAIL")], out


def cases():
    i = GOOD["harm_inventory"][0]
    return [
        ("inventory", dict(harm_inventory=[]), "inventory"),
        ("inventory", dict(harm_inventory=[{**i, "worst_case": " "}]), "inventory"),
        ("owners", dict(harm_inventory=[{k: v for k, v in i.items() if k != "owner"}]), "owners"),
        ("rereview", dict(rereview_on=["feature", "model"]), "rereview"),
        ("human_gate", dict(actions=[{"action": "delete", "high_stakes": True, "human_gate": False}]), "human_gate"),
        ("metric", dict(metrics=[{"name": "bias", "value": 0.0, "measured": False}]), "unmeasured_metric"),
        ("row field", dict(test_rows=[{**ROW, "stop_condition": ""}]), "test_rows"),
        ("no row", dict(test_rows=[{**ROW, "harm": "other"}]), "test_rows"),
        ("zero tol", dict(test_rows=[{**ROW, "threshold": 0}]), "test_rows"),
        ("sweep", dict(sweeps={"prompt_injection": True, "data_leakage": True}), "sweeps"),
        ("certify", dict(claims_about_system=["The model is unbiased."]), "never_certify"),
        ("pct", dict(confidence_displays=["87% confident"]), "bare_percentage"),
        ("tier", dict(confidence_tiers={"High": ""}), "tiers_defined"),
        ("override", dict(override_offered=False), "override"),
        ("no card", dict(card=None), "card"),
        ("card gap", dict(card={**CARD, "consent": ""}), "card"),
        ("disclosure", dict(disclosure_recommended=False), "disclosure"),
        ("legal", dict(legal_questions=[{"question": "q", "routed_to": ""}]), "legal_routed"),
        ("regime", dict(regimes_named=["EU AI Act", "NIST AI RMF"]), "regimes"),
        ("date", dict(regimes_named=["EU AI Act 2024", "ISO/IEC 42001", "NIST AI RMF"]), "no_date"),
    ]



class Checks(unittest.TestCase):
    def test_good_passes_every_check(self):
        rc, out = run(GOOD)
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.count("PASS "), len(O.CHECKS))

    def test_each_check_fails_alone(self):
        for label, kw, name in cases():
            with self.subTest(label):
                rc, failed, out = bad(**kw)
                self.assertEqual((rc, failed), (1, [name]), out)

    def test_boundaries_pass(self):
        # zero threshold on a gated irreversible action, a measured value
        for kw in (dict(test_rows=[{**ROW, "threshold": 0, "gated_irreversible": True}]),
                   dict(card=CARD, metrics=[{"name": "m", "value": 3, "measured": True}])):
            self.assertEqual(bad(**kw)[0], 0)

    def test_failure_cites_rule(self):
        self.assertIn('rule: "offer an override"', bad(override_offered=False)[2])

    def test_skip_and_inconclusive(self):
        rc, out = run({"override_offered": True})
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("SKIP "), len(O.CHECKS) - 1)
        rc, out = run({})
        self.assertEqual(rc, 3)
        self.assertIn("INCONCLUSIVE", out)
        self.assertNotIn("PASS", out)

    def test_test_rows_alone_skips_coverage(self):
        d = {k: GOOD[k] for k in ("test_rows",)}
        self.assertEqual(run(d)[0], 0)


class Vacuous(unittest.TestCase):
    def test_empty_lists_skip_never_pass(self):
        for k in ("actions", "metrics", "test_rows", "legal_questions", "claims_about_system", "confidence_displays"):
            with self.subTest(k):
                rc, out = run({k: []})
                self.assertEqual(rc, 3, out)
                self.assertNotIn("PASS", out)
        rc, out = run({"harm_inventory": []})
        self.assertEqual(rc, 1)
        self.assertIn("SKIP owners: empty", out)
        rc, out = run({"harm_inventory": GOOD["harm_inventory"], "test_rows": []})
        self.assertIn("FAIL test_rows: bias: no test row", out)

    def test_empty_row_or_string_is_error(self):
        for d in ({"actions": [{}]}, {"metrics": [{}]}, {"legal_questions": [{}]}, {"harm_inventory": [{}]},
                  {"test_rows": [{}]}, {"claims_about_system": [""]}, {"claims_about_system": ["  "]},
                  {"confidence_displays": [""]}, {"regimes_named": [""]}, {"rereview_on": [""]}):
            with self.subTest(d):
                self.assertEqual(run(d)[0], 2)

    def test_empty_containers_fail_not_pass(self):
        for d in ({"sweeps": {}}, {"card": {}}, {"confidence_tiers": {}}, {"rereview_on": []}, {"regimes_named": []}):
            with self.subTest(d):
                rc, out = run(d)
                self.assertEqual(rc, 1, out)

    def test_certification_fails_closed(self):
        # any certification word FAILs, disclaimers included (intended: reword the line)
        for c in ("The model is safe, not risky.", "Unverified, but we declare it safe.", "No doubt it is safe.",
                  "Not surprisingly it is safe.", "No, it is safe.", "It is not unbiased.", "It is never safe.",
                  "It isn't compliant.", "We do not call it safe.", "We make no claim it is safe"):
            with self.subTest(c):
                self.assertEqual(bad(claims_about_system=[c])[1], ["never_certify"])
        for w in ("safe", "unbiased", "fair", "compliant"):  # each word alone, so dropping one from the regex fails
            with self.subTest(w):
                self.assertEqual(bad(claims_about_system=[f"The system is {w}."])[1], ["never_certify"])
        self.assertEqual(bad(claims_about_system=["Residual risk is unverified."])[0], 0)

    def test_negated_regime_is_not_named(self):
        self.assertEqual(bad(regimes_named=["EU AI Act", "ISO/IEC 42001", "not the NIST AI RMF"])[1], ["regimes"])


class Mutation(unittest.TestCase):
    """One FAIL case per rule so deleting any rule from the checker breaks a test."""

    def fails(self, name, **kw):
        rc, failed, out = bad(**kw)
        self.assertEqual((rc, failed), (1, [name]), out)

    def test_inventory_affected(self):
        i = GOOD["harm_inventory"][0]
        self.fails("inventory", harm_inventory=[{k: v for k, v in i.items() if k != "affected"}])

    def test_row_fields(self):
        for k in ROW_KEYS:
            if k != "harm":
                with self.subTest(k):
                    self.fails("test_rows", test_rows=[{**ROW, k: ""}])

    def test_threshold_type(self):
        for t in ("0.1", True, None):
            with self.subTest(t):
                self.fails("test_rows", test_rows=[{**ROW, "threshold": t}])

    def test_sweeps(self):
        for k in SWEEP_KEYS:
            with self.subTest(k):
                self.fails("sweeps", sweeps={**GOOD["sweeps"], k: False})

    def test_rereview(self):
        for w in ("feature", "model", "data"):
            with self.subTest(w):
                self.fails("rereview", rereview_on=[x for x in ("feature", "model", "data") if x != w])

    def test_regimes(self):
        for n in REGIME_NAMES:
            with self.subTest(n):
                self.fails("regimes", regimes_named=[r for r in REGIME_NAMES if r != n])

    def test_card_fields(self):
        for k in CARD_KEYS:
            with self.subTest(k):
                self.fails("card", card={**CARD, k: ""})

    def test_dates_and_versions(self):
        for x in ("EU AI Act 2024", "EU AI Act version two", "EU AI Act v2", "NIST AI RMF 1.0"):
            with self.subTest(x):
                self.fails("no_date", regimes_named=[x, *[r for r in REGIME_NAMES if r not in x]])

    def test_tier_definition_is_stripped(self):
        self.fails("tiers_defined", confidence_tiers={"High": "   "})

    def test_metric_value_without_measured_key_fails(self):
        self.fails("unmeasured_metric", metrics=[{"name": "bias", "value": 0.1}])
        self.assertEqual(run({"metrics": [{"name": "bias", "value": 0.1, "measured": "yes"}]})[0], 2)

    def test_nonfinite_threshold_is_error(self):
        for lit in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(lit):
                self.assertEqual(BadInput.err(self, '{"test_rows": [{"harm": "a", "threshold": %s}]}' % lit), None)


class BadInput(unittest.TestCase):
    def err(self, raw):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            f.write(raw)
            f.flush()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = O.main([f.name])
        self.assertEqual(rc, 2, out.getvalue())
        self.assertTrue(out.getvalue().startswith("ERROR "))

    def test_malformed(self):
        for raw in ("not json", "[]", "null", '{"harm_inventory": {}}', '{"harm_inventory": [1]}',
                    '{"actions": [{"high_stakes": "yes", "human_gate": true}]}',
                    '{"sweeps": []}', '{"card": 5}', '{"override_offered": "y"}', '{"regimes_named": [1]}',
                    '{"test_rows": [{"harm": ["x"]}]}', '{"harm_inventory": [{"harm": 3}]}',
                    '{"confidence_tiers": {"a": 1}}', '{"harm_inventory": 1e999999999}', "[" * 100000 + "]" * 100000):
            with self.subTest(raw[:30]):
                self.err(raw)

    def test_missing_file(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(O.main(["/nonexistent/in.json"]), 2)

    def test_stdin(self):
        old, sys.stdin = sys.stdin, io.StringIO('{"override_offered": false}')
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(O.main([]), 1)
        finally:
            sys.stdin = old


class Guards(unittest.TestCase):
    def test_constants_match_the_hardcoded_copies(self):
        self.assertEqual((O.CARD, O.ROW, O.SWEEPS, O.REGIMES), (CARD_KEYS, ROW_KEYS, SWEEP_KEYS, REGIME_NAMES))

    def test_quotes_are_verbatim(self):
        text = " ".join((SKILL / "SKILL.md").read_text().split() + (SKILL / "references/full-map.md").read_text().split())
        for name, _, quote, _ in O.CHECKS:
            self.assertIn(" ".join(quote.split()), text, name)

    def test_every_check_is_exercised(self):
        failed = {n for _, kw, n in cases()}
        self.assertEqual(failed, {c[0] for c in O.CHECKS})

    def test_no_numeric_limits_in_source(self):
        # limits come from the input: no comparison against a numeric literal other than 0
        import re
        src = (SKILL / "scripts/output_safety_check.py").read_text()
        self.assertEqual(re.findall(r"[<>]=?\s*[1-9]\d*\.?\d*", src), [])


if __name__ == "__main__":
    unittest.main()
