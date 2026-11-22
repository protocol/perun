#!/usr/bin/env python3
"""veche.py --criteria repeats: `--criteria a:3 --criteria b:2` must score both criteria, not only the last (#2275). Stdlib only."""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_veche_input import CRIT, council, reply, scores  # noqa: E402  reuses the fake-seat harness


class CriteriaRepeat(unittest.TestCase):
    """Repeated --criteria flags are joined, so every criterion reaches the record and the weighted decision."""

    def test_repeated_flags_keep_every_criterion(self):
        extra = ["--option", "ship", "--criteria", "impact:3", "--criteria", "cost:2"]
        rc, rec, calls = council(reply(scores("ship")), extra)
        self.assertEqual((rc, rec["verdict"], calls), (0, "REVISE", 3))
        self.assertEqual(set(rec["criteria"]), {"impact", "cost"})
        self.assertAlmostEqual(rec["criteria"]["impact"], 0.6)

    def test_repeated_flag_with_comma_list_still_parses(self):
        extra = ["--option", "ship", "--criteria", "impact:3,cost:2", "--criteria", "risk:1"]
        three = {o: {"impact": 3, "cost": 1, "risk": 2} for o in ("do-nothing", "ship")}
        rc, rec, _ = council(reply(three), extra)
        self.assertEqual(rc, 0)
        self.assertEqual(set(rec["criteria"]), {"impact", "cost", "risk"})

    def test_repeated_duplicate_criterion_still_fails_closed(self):
        extra = ["--option", "ship", "--criteria", "impact:3", "--criteria", "impact:2"]
        rc, rec, calls = council(reply(scores("ship")), extra)
        self.assertEqual((rc, rec["verdict"], calls), (3, "COULD_NOT_DECIDE", 0))
        self.assertIn("bad --criteria entry", rec["reason"])


if __name__ == "__main__":
    unittest.main()
