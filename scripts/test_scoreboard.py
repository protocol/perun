#!/usr/bin/env python3
"""Tests for scripts/scoreboard.py: verdict rule, computed rows, cited paths hold their numbers, UNMEASURED never guessed,
--check detects a stale page."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoreboard as sb  # noqa: E402


class Scoreboard(unittest.TestCase):
    def test_verdict_rule(self):
        self.assertEqual([sb.verdict(.51, .6), sb.verdict(.45, .55), sb.verdict(.2, .49), sb.verdict(.45, .66), sb.verdict(-.1, .0, 0)],
                         ["win", "tie", "loss", "not a win", "tie"])
        self.assertEqual(sb.verdict(-.108, .025, 0), "not a win")  # wide interval is not a tie

    def test_rows_computed_from_sources(self):
        page = sb.build()
        self.assertIn("| idea-critic (head-to-head) | gstack plan-ceo-review | tie (preference proxy): win rate 0.537 [0.473, 0.597], n=150", page)
        self.assertIn("| 0.64x | 2026-10-18 |", page)  # agentic-delivery tokens 7,301 / 11,487
        self.assertIn("addyosmani/agent-skills", page)
        self.assertIn("JuliusBrussee/caveman | UNMEASURED | UNMEASURED | UNMEASURED | UNMEASURED", page)
        self.assertNotIn("nan", page.lower())

    def test_source_is_the_dir_holding_the_number(self):
        rows = {(r["feature"], r["rival"]): r for r in sb.h2h_rows()}
        r = rows["business-ops (head-to-head)", "marketingskills pricing"]
        self.assertIn("`docs/bench/bizops-sup-1018`", r["src"])  # not the first cited dir, bizops-e-confirm-1018, which lacks 0.463
        self.assertNotIn("bizops-e-confirm-1018", r["src"])

    def test_review_equal_estimates_are_not_ties(self):
        rows = sb.review_rows()
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(r["v"], sb.EQ)
            self.assertTrue(r["q"].startswith(sb.EQ) and r["cost"].endswith("x"))
        head = sb.build().split("\n\n")[2]
        self.assertIn(f"4 {sb.EQ}", head)
        self.assertNotIn("tie: recall", sb.build())

    def test_comms_proxy_loss_is_superseded_by_outcome_rows(self):
        page = sb.build()
        self.assertIn("humanizer | superseded by the outcome rows below", page)
        self.assertIn("win (outcome, rule deviation: simulated readers, shipped over a frozen-rule REVERT): Perun minus rival +0.046 [+0.034, +0.058]", page)
        self.assertNotIn("paired; shipped E4", page)
        self.assertIn("tie (outcome): Perun minus rival -0.001", page)

    def test_header_counts_separate_clean_outcome_wins(self):
        head = sb.build().split("\n\n")[2]
        self.assertIn("Clean outcome wins: 0 (Perun has no clean outcome win)", head)
        self.assertIn("Preference proxy (blind judge)", head)
        self.assertIn("1 outcome win with a rule deviation", head)
        self.assertIn("2 narrative-only wins", head)
        self.assertIn("1 win not confirmed as outcome", head)

    def test_h8_is_narrative_only(self):
        rows = sb.h8_rows()
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(r["v"], "narrative win")
            self.assertIn("no committed result file, narrative only", r["q"])

    def test_safety_proxy_win_not_confirmed_as_outcome(self):
        self.assertIn("not confirmed as outcome (safety-outcome-1019 tie)", sb.build())

    def test_h14_rows_carry_pilot_caveat(self):
        rows = sb.h14_rows()
        self.assertTrue(rows)
        for r in rows:
            self.assertIn("exploratory pilot; preregistered recheck REVERT", r["q"])

    def test_caveats_ride_on_rows(self):
        page = sb.build()
        self.assertIn("narrow, lower bound 0.507", page)
        self.assertIn("32-string own corpus", page)

    def test_proof_fails_on_missing_dir_and_wrong_number(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "bench" / "a").mkdir(parents=True)
            (root / "bench" / "a" / "r.json").write_text('{"m": 0.4633, "lo": 0.403}')
            self.assertTrue(sb.holds("bench/a", ["0.463", "0.403"], root))  # rounding match
            ok = {"feature": "f", "rival": "r", "proofs": [("bench/a", ["0.463"])]}
            sb.verify([ok], root)
            for bad in ({"proofs": [("bench/missing", ["0.463"])]}, {"proofs": [("bench/a", ["0.999"])]}):
                with self.assertRaises(SystemExit):
                    sb.verify([{**ok, **bad}], root)

    def test_check_mode(self):
        with tempfile.TemporaryDirectory() as d:
            sb.PAGE = Path(d) / "scoreboard.md"
            with self.assertRaises(SystemExit):
                sb.main(["--check"])  # missing page
            sb.main([])
            sb.main(["--check"])  # fresh page passes
            sb.PAGE.write_text(sb.PAGE.read_text() + "x")
            with self.assertRaises(SystemExit):
                sb.main(["--check"])  # stale page fails

    def test_committed_page_is_fresh(self):
        sb.PAGE = Path(sb.__file__).resolve().parent.parent / "docs" / "scoreboard.md"
        sb.main(["--check"])


if __name__ == "__main__":
    unittest.main()
