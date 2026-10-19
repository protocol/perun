#!/usr/bin/env python3
"""Tests for scripts/review_cost_per_recall.py: S1 matches the committed bench results, reported rows match their cited
sources, missing fields stay `unmeasured`, and the bench README embeds the script's current output. Offline."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_cost_per_recall as m  # noqa: E402

TSV = m.OUT / "reported.tsv"


class S1Raw(unittest.TestCase):
    def test_matches_committed_results_json(self):
        res = json.loads((m.RAW / "results.json").read_text())
        for arm in ("REAL", "TK"):
            rows, _ = m.raw_arm(arm)
            self.assertEqual(len(rows), res["n"])
            self.assertEqual((sum(r["n"] for r in rows), sum(r["good"] for r in rows), sum(r["cred"] for r in rows)),
                             (res[arm]["findings"], res[arm]["good"], res[arm]["cred"]))
            lo, hi = m.boot_ratio([r["cred"] for r in rows], [r["bugs"] for r in rows])
            self.assertEqual([round(lo, 3), round(hi, 3)], res[arm]["recall"]["ci"])

    def test_cost_is_per_case_mean_of_ok_calls(self):
        rows, verify = m.raw_arm("REAL")
        self.assertTrue(all(0 < r["usd"] < 0.2 for r in rows))
        self.assertGreater(verify, 0)


class Reported(unittest.TestCase):
    def test_rows_match_cited_source(self):
        for r in m.reported():
            text = (m.REPO / r["source"]).read_text()
            self.assertIn(f"${r['usd_case']}", text, r["arm"])
            self.assertTrue(r["recall"] in text or f"{r['caught']}/{r['n']}" in text, r["arm"])
            self.assertLessEqual(abs(r["caught"] / int(r["n"]) - float(r["recall"])), 0.0006, r["arm"])  # integer bug count

    def test_missing_fields_and_zero_recall(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.tsv"
            hdr = ["set", "arm", "n", "recall", "findings", "good", "usd_case", "basis", "source"]
            with p.open("w", newline="") as f:
                w = csv.writer(f, delimiter="\t")
                w.writerows([hdr, ["s", "a", "10", "0.500", "", "", "0.1", "b", "x"], ["s", "z", "10", "0.000", "5", "0", "0.0", "b", "x"]])
            a, z = m.reported(p)
        self.assertEqual((a["fa"], a["perbug"]), (m.U, "$0.200"))
        self.assertEqual((z["fa"], z["perbug"]), ("0.50", "no bug caught"))


class Stats(unittest.TestCase):
    def test_boot_ratio(self):
        self.assertEqual(m.boot_ratio([1, 1], [1, 1]), (1.0, 1.0))
        self.assertEqual(m.boot_ratio([1, 1], [1, 0])[0], 1.0)  # zero-denominator resamples are skipped, not divided


class Readme(unittest.TestCase):
    def test_embeds_current_tables(self):
        readme = (m.OUT / "README.md").read_text()
        for t in m.tables():
            self.assertIn(t, readme)


if __name__ == "__main__":
    unittest.main()
