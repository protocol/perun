#!/usr/bin/env python3
"""veche.uniq keeps kill criteria that differ only by a comparison operator: `p95 < 200 ms` and `p95 > 200 ms` are opposite
tripwires, not one. Near-duplicates (case, spacing, punctuation) still collapse. Stdlib only."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/idea-critic/scripts"))
import veche  # noqa: E402
from test_veche_record import council, reply  # noqa: E402


class Comparators(unittest.TestCase):
    def test_opposite_bounds_stay_two_items(self):
        for a, b in (("p95 latency < 200 ms", "p95 latency > 200 ms"), ("churn <= 5%", "churn >= 5%"),
                     ("p95 < 200 ms", "p95 <= 200 ms"), ("rate ≤ 5%", "rate ≥ 5%")):
            self.assertEqual(veche.uniq([a, b]), [a, b])

    def test_near_duplicates_still_collapse_keeping_the_first_wording_and_order(self):
        self.assertEqual(veche.uniq(["p95 latency < 200 ms.", "P95  latency <200 ms", "p95 latency < 200 ms"]), ["p95 latency < 200 ms."])
        self.assertEqual(veche.uniq(["b > 1", "a < 1", "B >1"]), ["b > 1", "a < 1"])

    def test_digits_still_distinguish(self):
        self.assertEqual(veche.uniq(["churn < 5%", "churn < 6%"]), ["churn < 5%", "churn < 6%"])

    def test_the_council_record_keeps_both_directions(self):
        kills = ["p95 latency < 200 ms by 2030-01-31", "p95 latency > 200 ms by 2030-01-31"]
        _, rec = council([reply("REVISE", kill=k) for k in kills + kills[:1]])
        self.assertEqual(rec["kill_criteria"], kills)


if __name__ == "__main__":
    unittest.main()
