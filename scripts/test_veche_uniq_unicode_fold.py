#!/usr/bin/env python3
"""veche.uniq folds the Unicode and ASCII spellings of one comparison: `rate ≤ 5%` and `rate <= 5%` are the same tripwire, so
only the first wording stays. Opposite or different bounds (`≤` vs `≥`, `<` vs `≤`) stay apart. Stdlib only."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/idea-critic/scripts"))
import veche  # noqa: E402
from test_veche_record import council, reply  # noqa: E402


class Fold(unittest.TestCase):
    def test_unicode_and_ascii_spellings_are_one_item_keeping_the_first_wording(self):
        for uni, asc in (("rate ≤ 5%", "rate <= 5%"), ("rate ≥ 5%", "rate >= 5%"), ("p95 ≤200 ms", "P95 <= 200 ms."), ("a ≥ 1", "a>=1")):
            self.assertEqual(veche.uniq([uni, asc]), [uni])
            self.assertEqual(veche.uniq([asc, uni]), [asc])

    def test_different_bounds_stay_apart(self):
        for a, b in (("rate ≤ 5%", "rate ≥ 5%"), ("rate ≤ 5%", "rate < 5%"), ("rate ≥ 5%", "rate > 5%"), ("rate ≤ 5%", "rate >= 5%"),
                     ("rate <= 5%", "rate >= 5%"), ("rate ≤ 5%", "rate ≤ 6%")):
            self.assertEqual(veche.uniq([a, b]), [a, b])

    def test_the_council_record_folds_the_spellings(self):
        kills = ["p95 latency ≤ 200 ms by 2030-01-31", "p95 latency <= 200 ms by 2030-01-31", "p95 latency ≥ 200 ms by 2030-01-31"]
        _, rec = council([reply("REVISE", kill=k) for k in kills])
        self.assertEqual(rec["kill_criteria"], [kills[0], kills[2]])


if __name__ == "__main__":
    unittest.main()
