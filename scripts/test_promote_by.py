#!/usr/bin/env python3
"""Tests for promote_by.py: overdue shadow flags with no decision fail; the shipped table passes today."""
import datetime
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import promote_by  # noqa: E402

D = datetime.date


def run(rows, today):
    with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as f:
        f.write(rows)
    try:
        return promote_by.check(today, f.name)
    finally:
        os.unlink(f.name)


class T(unittest.TestCase):
    def test_shipped_table_passes_on_a_fixed_date(self):
        self.assertEqual(promote_by.check(D(2026, 10, 28)), [])

    def test_overdue_fails_even_with_a_decision_until_the_date_moves(self):
        p = run("train_gate\t2026-01-01\t\nlkg_gate\t2026-01-01\tkeep shadow\n", D(2026, 6, 1))
        self.assertTrue(any("train_gate" in x and "overdue" in x for x in p))
        self.assertTrue(any("lkg_gate" in x and "overdue" in x for x in p))
        self.assertEqual(run("train_gate\t2026-07-01\tkeep\nlkg_gate\t2026-07-01\tkeep\n", D(2026, 6, 1)), [])

    def test_far_future_date_fails(self):
        p = run("train_gate\t2099-01-01\tkeep\nlkg_gate\t2026-07-01\t\n", D(2026, 6, 1))
        self.assertTrue(any("train_gate" in x and "120 days" in x for x in p))
        self.assertTrue(any("lkg_gate" in x for x in p) is False)

    def test_not_yet_due_passes(self):
        self.assertEqual(run("train_gate\t2026-07-01\t\nlkg_gate\t2026-07-01\t\n", D(2026, 6, 1)), [])

    def test_missing_row_bad_date_and_stale_row_fail(self):
        p = run("train_gate\tsoon\t\nwip_cap\t2026-07-01\t\n", D(2026, 6, 1))
        self.assertTrue(any("lkg_gate" in x and "no promote-by row" in x for x in p))
        self.assertTrue(any("bad promote-by date" in x for x in p))
        self.assertTrue(any("wip_cap" in x and "not shadow" in x for x in p))


if __name__ == "__main__":
    unittest.main()
