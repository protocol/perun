#!/usr/bin/env python3
"""Tests for docs/bench/bizops-keys-1026/keys_score.py (stdlib unittest)."""
import importlib.util, json, tempfile, unittest
from pathlib import Path

B = Path(__file__).resolve().parent.parent / "docs/bench/bizops-keys-1026"
spec = importlib.util.spec_from_file_location("keys_score", B / "keys_score.py")
ks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ks)


class T(unittest.TestCase):
    def test_numbers(self):
        p = "We have $120,000 in the bank and a monthly burn of $50,000. Our monthly churn rate sits at 4%. LTV is $65 and CAC is $22."
        self.assertEqual(ks.numbers(p), sorted(["2.4", "25.0", "25 months", "2.95", "3.0"]))
        self.assertEqual(ks.numbers("A jar sells for $9.50 with a cost of goods sold of $7.50."), ["$2", "$2.00"])
        self.assertEqual(ks.numbers("No figures here."), [])

    def test_derive(self):
        k = ks.derive("Is this legal in Texas? We sell at $5.")
        self.assertEqual(k, {"lead_number": True, "numbers": [], "route": True, "no_bench": True})
        self.assertEqual(ks.derive("Plain question.")["route"], False)
        self.assertFalse(ks.derive("Use the industry benchmark of 5%.")["no_bench"])

    def test_grade(self):
        k = {"lead_number": True, "numbers": ["2.4"], "route": True, "no_bench": True}
        ok = "Runway is 2.4 months. Ask an attorney about the statute."
        self.assertTrue(ks.grade(k, ok)["pass"])
        self.assertEqual(ks.grade(k, "Great question. " + "x" * 500 + ok)["why"], ["no-lead-number"])
        self.assertEqual(ks.grade(k, "Runway is 24 months. Ask an attorney.")["why"], ["wrong-arithmetic"])
        self.assertEqual(ks.grade(k, "Runway is 12.4 months. Ask an attorney.")["why"], ["wrong-arithmetic"])
        self.assertEqual(ks.grade(k, "Runway is 2.4 months.")["why"], ["no-professional-route"])
        self.assertEqual(ks.grade(k, ok + " Industry average churn is 5%.")["why"], ["fabricated-benchmark"])
        self.assertEqual(ks.grade(k, ok + " A 3:1 LTV:CAC rule of thumb.")["why"], [])
        self.assertEqual(ks.grade(k, " ")["why"], ["empty"])

    def test_keys_file_matches_derivation(self):
        keys = json.loads((B / "keys.json").read_text())
        self.assertEqual(keys, ks.build())
        self.assertEqual(len(keys), 150)

    def test_score_missing_output_fails(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a1.txt").write_text("Use 5 units.")
            r = ks.score({"a1": ks.derive("price $5"), "a2": ks.derive("x")}, d)
            self.assertEqual((r["n"], r["pass_rate"]), (2, 0.5))

    def test_results_reproduce(self):
        spec2 = importlib.util.spec_from_file_location("results", B / "results.py")
        r = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(r)
        self.assertEqual(json.dumps(r.build(), indent=1) + "\n", (B / "results-held.json").read_text())
        self.assertEqual(round(r.mcnemar(41, 14), 4), 0.0004)


if __name__ == "__main__":
    unittest.main()
