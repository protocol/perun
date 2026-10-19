#!/usr/bin/env python3
"""Tests for scripts/bench_verdict.py: the outcome-first verdict ladder and the perun-vs-rivals Win gate. Offline."""
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_verdict as b  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
WIN = {"wins": 70, "ties": 51, "losses": 29}  # 0.637 [0.577, 0.697] in the committed doc
COST = {"perun": 0.01, "rival": 0.02}
OUT = {"name": "merged rate", "perun": 0.9, "rival": 0.8, "higher_is_better": True}


def v(**kw):
    return b.verdict({**WIN, **kw})["verdict"]


class Ladder(unittest.TestCase):
    def test_win_needs_cost_and_outcome(self):
        self.assertEqual(v(cost_per_item=COST, outcome=OUT), "WIN")

    def test_preference_only_when_unmeasured(self):
        self.assertEqual(v(), b.PREF_ONLY)
        self.assertEqual(v(cost_per_item=COST), b.PREF_ONLY)
        self.assertEqual(v(outcome=OUT), b.PREF_ONLY)

    def test_outcome_worse_handles_lower_is_better(self):
        worse = {**OUT, "perun": 0.7}
        self.assertEqual(v(cost_per_item=COST, outcome=worse), "WIN ON PROXY, OUTCOME WORSE")
        low = {"name": "escaped defects", "perun": 5, "rival": 0, "higher_is_better": False}
        self.assertEqual(v(cost_per_item=COST, outcome=low), "WIN ON PROXY, OUTCOME WORSE")
        self.assertEqual(v(cost_per_item=COST, outcome={**low, "perun": 0}), "WIN")

    def test_cost_higher_blocks_win(self):
        self.assertEqual(v(cost_per_item={"perun": 0.05, "rival": 0.02}, outcome=OUT), "WIN ON PROXY, COST HIGHER")

    def test_equal_cost_is_a_win_on_a_preference_win(self):
        self.assertEqual(v(cost_per_item={"perun": 1, "rival": 1}, outcome=OUT), "WIN")

    def test_loss_and_parity(self):
        self.assertEqual(b.verdict({"wins": 10, "ties": 20, "losses": 120})["verdict"], "LOSS")
        self.assertEqual(b.verdict({"wins": 40, "ties": 20, "losses": 40})["verdict"], "PARITY")

    def test_tie_at_lower_cost_is_a_win_only_with_outcome_not_worse(self):
        tie = {"wins": 40, "ties": 20, "losses": 40}
        self.assertEqual(b.verdict({**tie, "cost_per_item": COST, "outcome": OUT})["verdict"], "WIN")
        self.assertEqual(b.verdict({**tie, "cost_per_item": COST, "outcome": {**OUT, "perun": 0.1}})["verdict"], "PARITY")
        self.assertEqual(b.verdict({**tie, "cost_per_item": {"perun": 1, "rival": 1}, "outcome": OUT})["verdict"], "PARITY")
        self.assertEqual(b.verdict({**tie, "cost_per_item": COST})["verdict"], "PARITY")

    def test_items_form_matches_counts(self):
        items = [1.0] * 70 + [0.5] * 51 + [0.0] * 29
        self.assertEqual(b.verdict({"items": items}), b.verdict(WIN))

    def test_empty_or_out_of_range_rejected(self):
        for spec in ({"wins": 0, "ties": 0, "losses": 0}, {"items": [1.5]}):
            with self.assertRaises(ValueError):
                b.verdict(spec)


class DocGate(unittest.TestCase):
    def row(self, cell):
        return f"| Skill | n | Verdict |\n|---|---|---|\n| s | 1 | {cell} |"

    def test_bare_win_fails(self):
        for cell in ("**Win** (replicated)", "**Win in this run** by the rule", "A clear win"):
            self.assertTrue(b.check_doc(self.row(cell)), cell)

    def test_honest_label_and_measured_pass(self):
        self.assertFalse(b.check_doc(self.row("**Preference-only win; cost and outcome unmeasured.**")))
        self.assertFalse(b.check_doc(self.row("**Win**: cost $0.01 vs $0.02 per item; outcome merged rate 0.9 vs 0.8")))
        self.assertTrue(b.check_doc(self.row("**Win**: cost $0.01 per item")))

    def test_non_wins_ignored(self):
        for cell in ("**Parity, not a win**", "**Win not replicated**", "**Not a win.**", "**Losing**"):
            self.assertFalse(b.check_doc(self.row(cell)), cell)

    def test_other_columns_and_headerless_rows_ignored(self):
        self.assertFalse(b.check_doc("| a | Result |\n|---|---|\n| s | **Win** |\n\n| s | **Win** |"))

    def test_committed_doc_passes(self):
        r = subprocess.run([sys.executable, str(REPO / "scripts/bench_verdict.py"), "--check-doc",
                            str(REPO / "docs/perun-vs-rivals.md")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
