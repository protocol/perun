#!/usr/bin/env python3
"""Threshold and lane-count tests for token_report.orchestration_actions (the actions printed when the orchestration share is flagged)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agentic-ceo/scripts"))
import token_report as tr  # noqa: E402


def report(main_raw, sub_raw, lanes, handbacks=()):
    share = main_raw / (main_raw + sub_raw)
    subs = [{"handback_chars": handbacks[i] if i < len(handbacks) else 100} for i in range(lanes)]
    return {"orchestration_flag": share > tr.ORCHESTRATION_FLAG_THRESHOLD, "subagents_count": lanes,
            "subagents_totals": {"raw_tokens": sub_raw}, "main": {"raw_tokens": main_raw}, "all_subagents": subs}


class OrchestrationActions(unittest.TestCase):
    def test_not_flagged_prints_nothing(self):
        self.assertEqual(tr.orchestration_actions(report(200, 800, 5)), [])  # exactly 20.0% is not above the threshold

    def test_measured_42_6_percent_with_30_lanes(self):
        acts = tr.orchestration_actions(report(426, 574, 30))
        self.assertIn("about 10 lanes", acts[0])  # floor(30 * 574 / (426 * 4))
        self.assertIn("14 raw tokens each", acts[0])
        self.assertTrue(any("batch independent" in a for a in acts))

    def test_few_lanes_get_no_merge_advice(self):
        acts = tr.orchestration_actions(report(300, 700, 1))  # target floors to 1 lane, not fewer than the 1 already used
        self.assertFalse(any("fewer, larger lanes" in a for a in acts))

    def test_oversized_handbacks_flagged(self):
        acts = tr.orchestration_actions(report(426, 574, 30, handbacks=(5000, 900)))
        hb = next(a for a in acts if a.startswith("field-only handbacks"))
        self.assertIn("2 of 30 lanes", hb)
        self.assertIn("largest 5000", hb)


if __name__ == "__main__":
    unittest.main()
