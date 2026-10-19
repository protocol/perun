#!/usr/bin/env python3
"""Tests for scripts/bench_verdict.py: the outcome-first verdict ladder and the perun-vs-rivals Win gate. Offline."""
import json
import subprocess
import sys
import tempfile
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
        out = {**OUT, "diff_ci": [0.01, 0.2]}

        def t(**kw):
            return b.verdict({**tie, **kw})["verdict"]

        self.assertEqual(t(cost_per_item=COST, outcome=out), "WIN")
        self.assertEqual(t(cost_per_item=COST, outcome={**out, "perun": 0.1}), "PARITY")
        self.assertEqual(t(cost_per_item=COST, outcome=OUT), "PARITY")  # no diff_ci: cannot show not worse
        self.assertEqual(t(cost_per_item=COST, outcome={**out, "diff_ci": [-0.2, 0.3]}), "PARITY")
        self.assertEqual(t(cost_per_item=COST, outcome={**out, "diff_ci": [-0.2, 0.3], "margin": 0.25}), "WIN")
        self.assertEqual(t(cost_per_item={"perun": 1, "rival": 1}, outcome=out), "PARITY")
        self.assertEqual(t(cost_per_item=COST), "PARITY")

    def test_tie_needs_ci_within_equivalence_margin(self):
        out = {**OUT, "diff_ci": [0.01, 0.2]}
        wide = {"wins": 8, "ties": 4, "losses": 8}  # n=20: CI far wider than +/-0.10
        self.assertEqual(b.verdict({**wide, "cost_per_item": COST, "outcome": out})["verdict"], "PARITY")
        self.assertEqual(b.verdict({**wide, "cost_per_item": COST, "outcome": out}, equiv_margin=0.5)["verdict"], "WIN")
        with self.assertRaises(ValueError):
            b.verdict(wide, equiv_margin=float("nan"))

    def test_non_finite_or_non_numeric_is_unmeasured_never_win(self):
        nan, inf = float("nan"), float("inf")
        for bad in ({"perun": nan, "rival": 0.02}, {"perun": inf, "rival": 0.02}, {"perun": "0.01", "rival": 0.02},
                    {"perun": True, "rival": None}, {"perun": -1, "rival": 0.02}, "cheap", [1, 2]):
            self.assertEqual(v(cost_per_item=bad, outcome=OUT), b.PREF_ONLY, bad)
        self.assertEqual(v(cost_per_item=COST, outcome={**OUT, "perun": nan}), b.PREF_ONLY)
        self.assertEqual(v(cost_per_item=COST, outcome={**OUT, "rival": "x"}), b.PREF_ONLY)
        tie = {"wins": 40, "ties": 20, "losses": 40, "outcome": {**OUT, "perun": nan, "diff_ci": [0, 1]}}
        self.assertEqual(b.verdict({**tie, "cost_per_item": COST})["verdict"], "PARITY")

    def test_items_form_matches_counts(self):
        items = [1.0] * 70 + [0.5] * 51 + [0.0] * 29
        self.assertEqual(b.verdict({"items": items}), b.verdict(WIN))

    def test_tiny_n_is_underpowered_not_a_win(self):
        spec = {"wins": 3, "ties": 0, "losses": 0, "cost_per_item": {"perun": 1, "rival": 2},
                "outcome": {"perun": 1, "rival": 0}}
        self.assertEqual(b.verdict(spec)["verdict"], "UNDERPOWERED")

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
        self.assertFalse(b.check_doc(self.row("**Win**: cost $0.01 vs $0.02 per item; outcome merged rate 0.9 vs 0.8 (higher is better)")))
        self.assertTrue(b.check_doc(self.row("**Win**: cost $0.01 per item")))

    def test_win_needs_structured_evidence(self):
        for cell in ("**Win** $5 outcome 1", "**Win**, no outcome measured $9", "**Win**: cost $0.01 per item; outcome merged rate 0.9 vs 0.8",
                     "**Win**: cost $0.05 vs $0.02; outcome merged rate 0.9 vs 0.8",  # Perun costs more
                     "**Win**: cost $0.01 vs $0.02", "**Win**: outcome merged rate 0.9 vs 0.8", "**Preference-only win.**"):
            self.assertTrue(b.check_doc(self.row(cell)), cell)

    def test_win_forms_and_other_gated_headers(self):
        for cell in ("Perun wins", "Perun won", "the winner is Perun", "Preference-only win; unmeasured. Also a win overall"):
            self.assertTrue(b.check_doc(self.row(cell)), cell)
        self.assertTrue(b.check_doc("| a | Result [95% CI] |\n|---|---|\n| s | Perun wins 7/10 |"))
        self.assertTrue(b.check_doc("| a | Verdict and caveat |\n|---|---|\n| s | **Win** |"))
        for cell in ("Win rate 0.6", "non-wins only", "Not a win; win-rate lower bound 0.45"):
            self.assertFalse(b.check_doc(self.row(cell)), cell)

    def test_bench_spec_is_recomputed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name, spec in (("good", {**WIN, "cost_per_item": COST, "outcome": OUT}), ("pref", WIN)):
                (root / "docs/bench" / name).mkdir(parents=True)
                (root / "docs/bench" / name / "verdict_spec.json").write_text(json.dumps(spec))
            ok = self.row("**Win**; bench: docs/bench/good")
            self.assertFalse(b.check_doc(ok, root))
            for cell in ("**Win**; bench: docs/bench/pref", "**Win**; bench: docs/bench/missing", "**Win**; bench: docs/bench/.."):
                self.assertTrue(b.check_doc(self.row(cell), root), cell)
            (root / "docs/bench/good/verdict_spec.json").write_text("{not json")
            self.assertTrue(b.check_doc(ok, root))

    def test_non_wins_ignored(self):
        for cell in ("**Parity, not a win**", "**Win not replicated**", "**Not a win.**", "**Losing**"):
            self.assertFalse(b.check_doc(self.row(cell)), cell)

    def test_code_span_is_not_a_win_claim(self):
        self.assertFalse(b.check_doc(self.row("Parity; raw data in `docs/bench/wins-rep-1018/`")))

    def test_evasions_still_fail(self):
        for cell in ("`Win`", "Verdict: Win", "Perun wins not only on quality", "Win --- clear", "winning",
                     "**Win**: cost $0.01 vs $0.02 per item; outcome merged rate 0.9 vs 0.8",
                     "**Win**: cost $0.01 vs $0.02 per item; outcome merged rate 0.7 vs 0.8 (higher is better)",
                     "**Win**: cost $0.01 vs $0.02 per item; outcome false alarms 0.9 vs 0.8 (lower is better)"):
            self.assertTrue(b.check_doc(self.row(cell)), cell)
        self.assertFalse(b.check_doc(self.row("Win: cost $0.01 vs $0.02; outcome false alarms 0.7 vs 0.8 (lower is better)")))
        self.assertFalse(b.check_doc(self.row("A window of 3 days")))

    def test_other_columns_and_headerless_rows_ignored(self):
        self.assertFalse(b.check_doc("| a | Caveat |\n|---|---|\n| s | **Win** |\n\n| s | **Win** |"))

    def test_committed_doc_passes(self):
        r = subprocess.run([sys.executable, str(REPO / "scripts/bench_verdict.py"), "--check-doc",
                            str(REPO / "docs/perun-vs-rivals.md")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
