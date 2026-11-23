#!/usr/bin/env python3
"""Tests for token_report.py lane tail spend beyond the tool-call cap (`lane_tail`, `tail_share_over_cap`).

Fixtures are synthetic lanes generated in a temp dir; no real session is read.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude/skills/agentic-ceo/scripts"))
import token_report as tr  # noqa: E402

MAIN = {"type": "assistant", "requestId": "m", "timestamp": "2026-10-19T10:00:00+00:00",
        "message": {"model": "claude-sonnet-5", "usage": {"input_tokens": 1, "output_tokens": 1}}}


def lane(calls, ie):
    """One-turn lane with `calls` tool_use blocks and `ie` input-eq (plain input tokens weigh 1.0)."""
    block = [{"type": "tool_use", "id": f"t{i}"} for i in range(calls)]
    return [{"type": "assistant", "requestId": "r", "timestamp": "2026-10-19T10:00:01+00:00",
             "message": {"model": "claude-sonnet-5", "content": block, "usage": {"input_tokens": ie, "output_tokens": 1}}}]


def report(lanes, **kw):
    d = tempfile.TemporaryDirectory()
    root = Path(d.name)
    (root / "s.jsonl").write_text(json.dumps(MAIN) + "\n")
    (root / "s" / "subagents").mkdir(parents=True)
    for i, rows in enumerate(lanes):
        (root / "s" / "subagents" / f"agent-{i}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    r = tr.build_report(str(root / "s.jsonl"), None, 5, tr.DEFAULT_RATES, **kw)
    d.cleanup()
    return r


class LaneTail(unittest.TestCase):
    def test_matches_bench_one_liner(self):
        # bench: sum(ie*(calls-150)/calls for calls>150) / sum(ie); lanes: 300 calls/1000, 150 calls/1000 (not over), 20 calls/500
        r = report([lane(300, 1000), lane(150, 1000), lane(20, 500)])
        a = r["all_subagents"]
        want = sum(x["input_equivalent"] * (x["tool_calls"] - 150) / x["tool_calls"] for x in a if x["tool_calls"] > 150) / sum(
            x["input_equivalent"] for x in a)
        lt = r["lane_tail"]
        self.assertAlmostEqual(lt["tail_share_over_cap"], want, delta=0.0005)
        self.assertAlmostEqual(lt["tail_share_over_cap"], 500 / 2500, places=4)  # 1000 * 150/300 = 500
        self.assertEqual((lt["lanes_over_cap"], lt["cap"]), (1, 150))

    def test_cap_default_is_budget_max_tool_calls(self):
        self.assertEqual(tr.lane_tail([])["cap"], tr.DEFAULT_BUDGET["star"]["max_tool_calls"])

    def test_p90_nearest_rank(self):
        lanes = [{"input_equivalent": 1, "tool_calls": c} for c in range(1, 11)]
        self.assertEqual(tr.lane_tail(lanes)["p90_tool_calls"], 9)
        self.assertEqual(tr.lane_tail(lanes[:1])["p90_tool_calls"], 1)

    def test_no_lanes_or_zero_ie_is_zero_not_crash(self):
        self.assertEqual(tr.lane_tail([])["tail_share_over_cap"], 0.0)
        self.assertEqual(tr.lane_tail([])["p90_tool_calls"], 0)
        self.assertEqual(tr.lane_tail([{"input_equivalent": 0, "tool_calls": 400}])["tail_share_over_cap"], 0.0)

    def test_json_and_text_lever_only_when_material(self):
        big = report([lane(300, 1000), lane(20, 500)])  # tail 500/1500 = 33%
        self.assertEqual(json.loads(json.dumps(big))["lane_tail"]["tail_share_over_cap"], 0.3333)
        text = tr.render_text(big)
        self.assertIn("Lane tail (upper bound, redo cost ignored): 33.3% of lane input-eq is spent beyond the reference cap of 150", text)
        self.assertIn("Lever: lower LANE_TOOL_CAP (shipped 150) toward p90 300", text)
        self.assertIn("lane_cap.py", text)
        small = tr.render_text(report([lane(160, 100), lane(20, 5000)]))  # tail ~0.1%
        self.assertIn("Lane tail", small)
        self.assertNotIn("Lever: lower LANE_TOOL_CAP", small)
        self.assertNotIn("Lane tail", tr.render_text(report([])))

    def test_shipped_cap_read_from_template_and_reported_separately(self):
        self.assertEqual(tr.shipped_lane_cap(), 150)  # the installed default; fixtures below assume it, update both together
        r = report([lane(300, 1000), lane(20, 500)])["lane_tail"]
        self.assertEqual((r["shipped_cap"], r["tail_share_over_shipped_cap"], r["lanes_over_shipped_cap"]), (150, 0.3333, 1))  # 1000*150/300 / 1500
        self.assertEqual(r["tail_share_over_cap"], 0.3333)
        text = tr.render_text(report([lane(300, 1000), lane(20, 500)]))
        self.assertIn("33.3% beyond the shipped hook cap of 150 (1 lane over)", text)

    def test_lever_keys_on_shipped_cap_not_reference_cap(self):
        # the lever keys on the shipped cap: a lane under the shipped 150 gives no lever
        text = tr.render_text(report([lane(120, 1000)]))
        self.assertIn("0.0% beyond the shipped hook cap of 150", text)
        self.assertNotIn("Lever: lower LANE_TOOL_CAP", text)
        self.assertIn("Lever: lower LANE_TOOL_CAP (shipped 150)", tr.render_text(report([lane(200, 1000)])))

    def test_unreadable_template_degrades_to_reference_only(self):
        self.assertIsNone(tr.shipped_lane_cap("/nonexistent/settings.json"))
        lt = tr.lane_tail([{"input_equivalent": 10, "tool_calls": 300}])
        self.assertIsNone(lt["shipped_cap"])
        self.assertIsNone(lt["tail_share_over_shipped_cap"])

    def test_budget_cap_flows_from_cli_into_build_report(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        root = Path(d.name)
        (root / "s.jsonl").write_text(json.dumps(MAIN) + "\n")
        (root / "b.tsv").write_text("*\tmax_tool_calls\t100\n")
        seen = []
        real = tr.build_report
        tr.build_report = lambda *a, **k: (seen.append(a[4] if len(a) > 4 else k.get("cap")), real(*a, **k))[1]
        self.addCleanup(setattr, tr, "build_report", real)
        with contextlib.redirect_stdout(io.StringIO()):
            tr.main(["--session", str(root / "s.jsonl"), "--budget", str(root / "b.tsv")])
            tr.main(["--session", str(root / "s.jsonl"), "--budget"])
            tr.main(["--session", str(root / "s.jsonl")])
        self.assertEqual(seen, [100, 150, 150])
        r = report([lane(300, 1000)], cap=100)["lane_tail"]
        self.assertEqual((r["cap"], r["tail_share_over_cap"]), (100, 0.6667))


if __name__ == "__main__":
    unittest.main()
