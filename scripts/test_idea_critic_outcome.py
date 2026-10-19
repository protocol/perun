#!/usr/bin/env python3
"""Offline tests for the idea-critic outcome bench (docs/bench/idea-critic-outcome-1019): corpus integrity, no hindsight leak,
decision parser, scoring, and that the committed results recompute exactly from the committed outputs."""
import json
import sys
import unittest
from pathlib import Path

B = Path(__file__).resolve().parent.parent / "docs/bench/idea-critic-outcome-1019"
sys.path.insert(0, str(B))
import bench_outcome as bo  # noqa: E402

CASES = bo.corpus()


class Corpus(unittest.TestCase):
    def test_size_and_balance(self):
        self.assertGreaterEqual(len(CASES), 30)
        keys = [c["key"] for c in CASES]
        self.assertGreaterEqual(min(keys.count("good"), keys.count("bad")), 15)

    def test_unique_ids_and_fields(self):
        self.assertEqual(len({c["id"] for c in CASES}), len(CASES))
        for c in CASES:
            self.assertTrue(all(u.startswith("https://en.wikipedia.org/wiki/") for u in c["source_urls"]), c["id"])
            self.assertEqual(c["fetched"], "2026-10-19")
            self.assertLess(c["decision_year"], 2021)

    def test_no_hindsight_words(self):
        for c in CASES:  # outcome vocabulary must not appear in what the model sees
            for w in ("write-down", "writedown", "bankrupt", "shut down", "failure", "reintroduc", "billion monthly"):
                self.assertNotIn(w, c["prompt"].lower(), c["id"])


class Scoring(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(bo.parse("x\nDECISION: GO"), "GO")
        self.assertEqual(bo.parse("DECISION: GO\nmore\n**DECISION: NO-GO**"), "NO-GO")
        self.assertIsNone(bo.parse("no verdict"))
        self.assertIsNone(bo.parse(None))

    def test_right(self):
        good, bad = {"key": "good"}, {"key": "bad"}
        self.assertEqual((bo.right(good, "GO"), bo.right(good, "NO-GO"), bo.right(bad, "NO-GO"), bo.right(bad, "GO"), bo.right(bad, None)), (1, 0, 1, 0, 0))


class Results(unittest.TestCase):
    def test_committed_results_recompute(self):
        for f in B.glob("results-*.json"):
            res = json.loads(f.read_text())
            model = res["model"]
            for a in bo.ARMS:  # accuracy from the stored outputs
                acc = sum(bo.right(c, bo.parse(bo.path(model, a, c["id"], r).read_text())) for c in CASES for r in range(bo.REPS)) / (len(CASES) * bo.REPS)
                self.assertAlmostEqual(acc, res["arms"][a]["accuracy"]["mean"], places=3, msg=f"{model} {a}")


if __name__ == "__main__":
    unittest.main()
