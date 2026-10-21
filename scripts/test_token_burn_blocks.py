#!/usr/bin/env python3
"""Tests for token_report.py `burn_blocks` (5-hour window burn rate and peak-window driver, `burn_blocks` in --json, a text lever).

Synthetic, fictional turns only; every figure is hand-computed from the documented formula. Boundary cases sit exactly on each threshold.
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude/skills/agentic-ceo/scripts"))
import token_report as tr  # noqa: E402


def T(hh, mm, inp=0, out=0, cr=0, day=1, tz=timezone.utc, **extra):
    """One turn at 2026-10-<day> hh:mm in `tz`; weighted = input + 0.1 x cache_read + output."""
    return {"timestamp": datetime(2026, 10, day, hh, mm, tzinfo=tz), "model": "m", "input_tokens": inp,
            "cache_write_5m": 0, "cache_write_1h": 0, "cache_read": cr, "output_tokens": out, **extra}


CALM = [T(16, 0, 100), T(22, 0, 100)]  # two later windows of weight 100 each: median 100, so a window of weight W has spike_x = W / 100
# window A 10:00-14:59: main 3500, lane alpha 5000 (open 10:10-10:50), lane beta 1000 (10:20); window B 16:00: main 1000; window C 22:00: main 2000
MAIN = [T(10, 0, 1000), T(10, 30, 2000, 500), T(16, 0, 1000), T(22, 0, 2000)]
LANES = [("alpha", [T(10, 10, 4000, 1000), T(10, 50)]), ("beta", [T(10, 20, 1000)])]


class BurnBlocks(unittest.TestCase):
    def test_hand_computed_blocks_spike_and_lane_advice(self):
        r = tr.burn_blocks(MAIN, LANES)
        a, b, c = r["blocks"]
        self.assertEqual((a["start"], a["weighted"], a["active_min"], a["burn_per_min"]), ("2026-10-01T10:00:00+00:00", 9500.0, 50.0, 190.0))
        self.assertEqual((a["lane_share"], a["peak_lanes"], a["driver"]), (0.6316, 2, {"who": "alpha", "lane": True, "share": 0.5263}))
        self.assertEqual((b["weighted"], b["active_min"], b["burn_per_min"]), (1000.0, 1.0, 1000.0))  # one turn: span floored at 1 minute
        self.assertEqual(r["peak"], a)
        self.assertEqual(r["spike_x"], 6.33)  # 9500 / median(1000, 2000)
        self.assertIn("lane 'alpha' alone drove 53% (2 lanes open at once, 63% of the block from lanes)", r["advice"])

    def test_window_edge_and_two_windows_have_no_spike(self):
        r = tr.burn_blocks([T(10, 0, 100), T(14, 59, 100), T(15, 0, 100)], [])
        self.assertEqual([b["weighted"] for b in r["blocks"]], [200.0, 100.0])  # 15:00 opens the next window
        self.assertIsNone(r["spike_x"])

    def test_window_opens_at_the_hour_of_a_mid_hour_first_turn(self):
        r = tr.burn_blocks([T(10, 45, 100), T(14, 59, 100), T(15, 0, 100)], [])
        self.assertEqual([(b["start"], b["weighted"], b["active_min"]) for b in r["blocks"]],
                         [("2026-10-01T10:00:00+00:00", 200.0, 254.0), ("2026-10-01T15:00:00+00:00", 100.0, 1.0)])  # 10:00+5h = 15:00, not 10:45+5h

    def test_non_utc_timestamps_are_windowed_in_utc(self):
        r = tr.burn_blocks([T(12, 30, 100, tz=timezone(timedelta(hours=2)))], [])  # 12:30+02:00 = 10:30 UTC
        self.assertEqual(r["blocks"][0]["start"], "2026-10-01T10:00:00+00:00")

    def test_main_driven_with_big_context_says_compact(self):
        r = tr.burn_blocks([T(9, 0, cr=250_000, out=1000), T(9, 30, cr=260_000, out=1000)], [])
        self.assertIn("main thread drove 100%", r["advice"])
        self.assertIn("average context 255000 (over the 200000 window): run /compact at a task boundary, or /clear", r["advice"])

    def test_context_threshold_is_strictly_above_the_window(self):
        self.assertIsNone(tr.burn_blocks([T(9, 0, cr=200_000)], [])["advice"])
        self.assertIn("average context 200001", tr.burn_blocks([T(9, 0, cr=200_001)], [])["advice"])

    def test_iter_turns_do_not_dilute_main_context(self):
        r = tr.burn_blocks([T(9, 0, cr=300_000), T(9, 1, iter=True)], [])  # a nested advisor turn is not a main context size
        self.assertEqual(r["blocks"][0]["main_ctx_avg"], 300_000)
        self.assertIn("average context 300000", r["advice"])

    def test_main_driven_small_context_and_diffuse_spend_give_no_advice(self):
        self.assertIsNone(tr.burn_blocks([T(9, 0, cr=50_000, out=1000)], [])["advice"])
        seq = [(f"l{i}", [T(9, i, 1000)]) for i in range(4)]  # four equal lanes one after another: 25% each, never open together
        self.assertIsNone(tr.burn_blocks([], seq)["advice"])

    def test_calm_single_lane_session_gets_no_lane_advice(self):
        one = tr.burn_blocks([T(9, 0, 10)], [("solo", [T(9, 5, 5000)])])  # one window: no baseline, so no spike
        self.assertEqual((one["blocks"][0]["driver"], one["spike_x"], one["advice"]), ({"who": "solo", "lane": True, "share": 0.998}, None, None))
        even = tr.burn_blocks([], [("a", [T(9, 0, 100)]), ("b", [T(16, 0, 100)]), ("c", [T(22, 0, 100)])])  # three equal windows: spike 1.0
        self.assertEqual((even["spike_x"], even["advice"]), (1.0, None))

    def test_spike_threshold_is_two_times_the_median(self):
        at = tr.burn_blocks([], [("a", [T(9, 0, 200)])] + [("m", [T(16, 0, 100), T(22, 0, 100)])])
        self.assertEqual(at["spike_x"], 2.0)
        self.assertIn("lane 'a' alone drove 100%", at["advice"])
        below = tr.burn_blocks([], [("a", [T(9, 0, 199)])] + [("m", [T(16, 0, 100), T(22, 0, 100)])])
        self.assertEqual((below["spike_x"], below["advice"]), (1.99, None))

    def test_driver_share_threshold_is_forty_percent_inclusive(self):
        def lanes(a, b, c):
            return [("a", [T(9, 0, a)]), ("b", [T(9, 10, b)]), ("c", [T(9, 20, c)])]
        r = tr.burn_blocks(CALM, lanes(400, 300, 300))
        self.assertEqual(r["blocks"][0]["driver"]["share"], 0.4)
        self.assertIn("lane 'a' alone drove 40%", r["advice"])
        self.assertIsNone(tr.burn_blocks(CALM, lanes(390, 305, 305))["advice"])  # 39%: diffuse, but never 3 open at once

    def test_fanout_needs_three_lanes_open_at_once(self):
        def par(n, w):  # n lanes all open 09:00-09:30, w weighted each (split over two turns), plus 100 of main
            return [(f"l{i}", [T(9, 0, w // 2), T(9, 30, w // 2)]) for i in range(n)]
        r = tr.burn_blocks(CALM + [T(9, 0, 100)], par(3, 300))  # 3 x 300 + 100: each lane 30%
        self.assertEqual(r["peak"]["peak_lanes"], 3)
        self.assertIn("up to 3 open at once", r["advice"])
        r2 = tr.burn_blocks(CALM + [T(9, 0, 300)], par(2, 350))  # 2 x 350 + 300: top 35%, two open
        self.assertEqual((r2["peak"]["peak_lanes"], r2["advice"]), (2, None))
        self.assertIsNone(tr.burn_blocks([T(9, 0, 100)], par(3, 300))["advice"])  # same fan-out in a lone window: no baseline, no spike

    def test_diffuse_fanout_names_the_fanout_not_a_lane(self):
        par = [(f"l{i}", [T(9, 0, 1000), T(9, 30, 1000)]) for i in range(4)]  # four equal lanes all open 09:00-09:30: 25% each
        r = tr.burn_blocks([T(9, 0, 100)] + CALM, par)
        self.assertEqual((r["peak"]["peak_lanes"], r["peak"]["lane_share"]), (4, 0.9877))
        self.assertIn("99% of it came from lanes, up to 4 open at once (burn 270.0 weighted/min, largest spender only 25%): dispatch fewer lanes per wave", r["advice"])

    def test_lane_spans_are_clipped_to_the_window(self):
        # lane x spans two windows, y and w sit inside window A: only turns inside A count, so none of them overlap in A
        lanes = [("x", [T(10, 0, 100), T(16, 30, 100)]), ("y", [T(10, 30, 100)]), ("w", [T(10, 5, 10), T(22, 0, 10)])]
        r = tr.burn_blocks([T(16, 0, 50)], lanes)
        self.assertEqual([b["peak_lanes"] for b in r["blocks"]], [1, 1, 1])
        idle = tr.burn_blocks([T(16, 0, 50)], [("v", [T(10, 0, 10), T(22, 0, 10)])])  # v is idle through 16:00-21:00
        self.assertEqual([b["peak_lanes"] for b in idle["blocks"]], [1, 0, 1])

    def test_a_lane_named_main_is_still_a_lane(self):
        r = tr.burn_blocks(CALM, [("main", [T(9, 0, 1000)])])
        self.assertTrue(r["peak"]["driver"]["lane"])
        self.assertIn("lane 'main' alone drove 100%", r["advice"])
        big_ctx = tr.burn_blocks(CALM + [T(9, 0, cr=300_000)], [("main", [T(9, 5, 100_000)])])  # lane (100000) outspends main (30000) at 300000 context
        self.assertIn("lane 'main' alone drove 77%", big_ctx["advice"])

    def test_zero_weight_median_has_no_spike_and_no_crash(self):
        r = tr.burn_blocks([T(10, 0, 100), T(16, 0), T(22, 0)], [])
        self.assertEqual((r["spike_x"], r["peak"]["weighted"]), (None, 100.0))

    def test_empty_synthetic_and_untimed_turns_are_ignored(self):
        junk = [{**T(9, 0, 5), "model": "<synthetic>"}, {**T(9, 0, 5), "timestamp": None}]
        self.assertEqual(tr.burn_blocks(junk, []), {"window_s": 18000, "blocks": [], "peak": None, "spike_x": None, "advice": None})

    def test_end_to_end_report_json_and_text(self):
        def line(ts, rid, usage):
            return {"type": "assistant", "timestamp": ts, "requestId": rid, "message": {"model": "m", "usage": usage}}
        main = [line(f"2026-10-01T{h}:00:00Z", rid, {"input_tokens": n, "output_tokens": 10})
                for h, rid, n in (("10", "a", 100), ("16", "c", 10), ("22", "d", 10))]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "s.jsonl").write_text("".join(json.dumps(m) + "\n" for m in main))
            (root / "s" / "subagents").mkdir(parents=True)
            (root / "s" / "subagents" / "agent-1.jsonl").write_text(
                json.dumps(line("2026-10-01T10:05:00Z", "b", {"input_tokens": 9000, "output_tokens": 100})) + "\n")
            (root / "s" / "subagents" / "agent-1.meta.json").write_text(json.dumps({"description": "Fictional Acme lane"}))
            rep = tr.build_report(str(root / "s.jsonl"), None, 5, tr.DEFAULT_RATES)
        json.dumps(rep)  # the private _turns key must not leak into the report
        self.assertNotIn("_turns", rep["all_subagents"][0])
        pk = rep["burn_blocks"]["peak"]
        self.assertEqual((pk["weighted"], pk["driver"]["who"], pk["peak_lanes"]), (9210.0, "Fictional Acme lane", 1))
        text = tr.render_text(rep)
        self.assertIn("5h windows", text)
        self.assertIn("Lever: peak block 2026-10-01T10:00:00+00:00: lane 'Fictional Acme lane' alone drove 99%", text)

    def test_render_text_tolerates_a_report_without_the_key(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "s.jsonl").write_text("")
            rep = tr.build_report(str(Path(d) / "s.jsonl"), None, 5, tr.DEFAULT_RATES)
        self.assertEqual(rep["burn_blocks"]["blocks"], [])
        del rep["burn_blocks"]
        self.assertNotIn("5h windows", tr.render_text(rep))


if __name__ == "__main__":
    unittest.main()
