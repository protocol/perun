#!/usr/bin/env python3
"""Tests for scripts/hidden_test_pool.py: the pooled hard-split numbers quoted in the r2 README. Offline."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hidden_test_pool as P  # noqa: E402


class Pool(unittest.TestCase):
    def test_pooled_counts_and_differences_match_the_readme(self):
        counts, diffs = P.pool()
        self.assertEqual(counts, {"none": (190, 276), "perun": (169, 276), "perun-core": (135, 207)})
        m, lo, hi = diffs[("perun", "none")]
        self.assertEqual((round(m, 3), round(lo, 3), round(hi, 3)), (-0.076, -0.156, 0.004))
        m, lo, hi = diffs[("perun-core", "none")]
        self.assertEqual((round(m, 3), round(lo, 3), round(hi, 3)), (-0.036, -0.122, 0.053))


if __name__ == "__main__":
    unittest.main()
