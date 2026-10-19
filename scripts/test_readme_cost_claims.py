#!/usr/bin/env python3
"""Pins README cost claims to committed bench data: raw S1 costs recomputed, aggregate costs found in bench-results.md,
retired unsourced figures absent, H7b ratio is per case (3.4), bench90 states no cost basis it cannot confirm. Offline."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_cost_per_recall as m  # noqa: E402

R = m.REPO
README = (R / "README.md").read_text()
BENCH = (R / ".claude/skills/deep-code-review/scripts/fixtures/bench-results.md").read_text()
DOCS = ("docs/perun-vs-rivals.md", "docs/capability-matrix.md", "docs/roadmap.md", "docs/roadmap-input.json")


class ReadmeCost(unittest.TestCase):
    def test_37_case_costs_match_bench_file(self):
        for fig in ("$0.136", "$0.090", "$0.098"):
            self.assertIn(fig, README)
            self.assertIn(fig, BENCH)

    def test_retired_figures_absent(self):
        for gone in ("$0.20 per case", "$0.14 to $0.16", "$0.17 against $0.27", "$0.14 against $0.07", "| Cost per case |", "$0.126"):
            self.assertNotIn(gone, README)

    def test_s1_cost_per_caught_bug_matches_raw(self):
        got = {}
        for arm in ("REAL", "TK"):
            rows, _ = m.raw_arm(arm)
            usd = sum(r["usd"] for r in rows)
            got[arm] = (usd / len(rows), usd / sum(r["cred"] for r in rows))
        self.assertEqual([f"${got['REAL'][1]:.3f}", f"${got['TK'][1]:.3f}"], ["$0.093", "$0.030"])
        self.assertEqual(f"{got['REAL'][0] / got['TK'][0]:.1f}", "3.4")
        for fig in ("$0.093", "$0.030", "$0.0551", "$0.0162", "3.4 times"):
            self.assertIn(fig, README)

    def test_h7b_ratio_is_per_case_everywhere(self):
        for p in DOCS:
            t = (R / p).read_text()
            self.assertNotIn("3.5x ($0.0537", t, p)
            self.assertNotIn("$.0537 vs $.0153); that", t, p)
            self.assertNotIn("about 3.5 times", t, p)

    def test_bench90_cost_basis_not_claimed(self):
        t = (R / "docs/bench/bench90-results.md").read_text()
        self.assertNotIn("Cost per review (including verifier) |\n|---|---|---|---|\n| Prompt only", t)
        self.assertNotIn("at $0.073 per review", t)
        self.assertIn("basis not recorded", t)


if __name__ == "__main__":
    unittest.main()
