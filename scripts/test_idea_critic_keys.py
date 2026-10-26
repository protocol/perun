#!/usr/bin/env python3
"""Tests for docs/bench/idea-critic-keys-1026/keys_score.py (stdlib unittest)."""
import importlib.util, json, tempfile, unittest
from pathlib import Path

B = Path(__file__).resolve().parent.parent / "docs/bench/idea-critic-keys-1026"
spec = importlib.util.spec_from_file_location("keys_score", B / "keys_score.py")
ks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ks)


class T(unittest.TestCase):
    def test_derive(self):
        k = ks.derive("Give me a single recommendation, the exact metric that would make me walk away, and play devil's advocate.")
        self.assertEqual(k, {"kill": True, "recommend": True, "mind": True})
        self.assertEqual(ks.derive("Tell me about our plan."), {"kill": False, "recommend": False, "mind": False})

    def test_grade(self):
        k = {"kill": True, "recommend": True, "mind": True}
        ok = "Recommend: proceed. Stop if premium capture is below 85%. I would change my mind if buyers refuse."
        self.assertTrue(ks.grade(k, ok)["pass"])
        self.assertEqual(ks.grade(k, "Recommend proceed. Stop if it goes badly. Would change my mind.")["why"], ["no-numeric-kill"])
        self.assertEqual(ks.grade(k, "Stop below 5%. Would change my mind.")["why"], ["no-recommendation"])
        self.assertEqual(ks.grade(k, "Proceed. Stop below 5%.")["why"], ["no-change-my-mind"])
        self.assertEqual(ks.grade(k, " ")["why"], ["empty"])

    def test_keys_file_matches_derivation(self):
        self.assertEqual(json.loads((B / "keys.json").read_text()), ks.build())

    def test_score_missing_output_fails(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a1.txt").write_text("Recommend proceed.")
            r = ks.score({"a1": ks.derive("recommendation please"), "a2": ks.derive("recommendation please")}, d)
            self.assertEqual((r["n"], r["pass_rate"]), (2, 0.5))

    def test_results_reproduce(self):
        spec2 = importlib.util.spec_from_file_location("results", B / "results.py")
        r = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(r)
        self.assertEqual(json.dumps(r.build(), indent=1) + "\n", (B / "results-held.json").read_text())
        self.assertEqual(round(r.mcnemar(16, 5), 4), 0.0266)


if __name__ == "__main__":
    unittest.main()
