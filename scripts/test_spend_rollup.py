#!/usr/bin/env python3
"""Tests for `token_report.py --rollup DIR`: per-project spend across sessions, main vs lanes, UNPRICED, window.

Transcripts are generated in a temp dir from fictional models; no real transcript is read.
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


def turn(model, inp=0, out=0, ts="2026-10-19T10:00:00Z", rid="r1"):
    usage = {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    return {"type": "assistant", "requestId": rid, "timestamp": ts, "message": {"model": model, "usage": usage}}


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


class Rollup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        # a: main sonnet-5 1M in = $2.00; one opus-5 lane 1M out = $25.00
        write(self.d / "a.jsonl", [turn("claude-sonnet-5", inp=1_000_000)])
        write(self.d / "a" / "subagents" / "lane1.jsonl", [turn("claude-opus-5", out=1_000_000)])
        # b: unknown model only -> UNPRICED, never estimated
        write(self.d / "b.jsonl", [turn("mystery-model", inp=500, out=500)])
        # c: another sonnet-5 main, later day
        write(self.d / "c.jsonl", [turn("claude-sonnet-5", inp=1_000_000, ts="2026-10-20T10:00:00Z")])

    def test_rollup_totals_split_and_unpriced(self):
        r = tr.build_rollup(str(self.d), None)
        self.assertEqual(len(r["sessions"]), 3)
        self.assertEqual(r["lanes"], 1)
        self.assertEqual(r["main_usd"], 4.0)
        self.assertEqual(r["lanes_usd"], 25.0)
        self.assertEqual(r["total_usd"], 29.0)
        self.assertEqual(r["unpriced_models"], ["mystery-model"])
        self.assertIn("$29.00 + UNPRICED (mystery-model) across 3 sessions, 1 lanes", r["line"])
        b = next(s for s in r["sessions"] if s["session"] == "b")
        self.assertIsNone(b["usd"])

    def test_since_window_drops_sessions(self):
        r = tr.build_rollup(str(self.d), tr.parse_timestamp("2026-10-20T00:00:00Z"))
        self.assertEqual([s["session"] for s in r["sessions"]], ["c"])
        self.assertEqual(r["total_usd"], 2.0)

    def test_all_unpriced_is_not_zero(self):
        d = self.d / "u"
        write(d / "x.jsonl", [turn("mystery-model", inp=5)])
        r = tr.build_rollup(str(d), None)
        self.assertIsNone(r["total_usd"])
        self.assertTrue(r["line"].startswith("spend: UNPRICED across 1 sessions"))

    def test_no_sessions_is_zero_not_unpriced(self):
        empty = self.d / "empty"
        empty.mkdir()
        for r in (tr.build_rollup(str(empty), None), tr.build_rollup(str(self.d), tr.parse_timestamp("2030-01-01T00:00:00Z"))):
            self.assertEqual(r["total_usd"], 0.0)
            self.assertTrue(r["line"].startswith("spend: $0.00 across 0 sessions, 0 lanes"))
            self.assertNotIn("UNPRICED", r["line"])

    def test_unreadable_lane_counted(self):
        (self.d / "a" / "subagents" / "junk.jsonl").write_text("not json\n")
        r = tr.build_rollup(str(self.d), None)
        self.assertEqual(r["unreadable_lanes"], 1)
        self.assertEqual(r["lanes"], 1)
        self.assertTrue(r["line"].endswith("; 1 lane transcript(s) unreadable"))

    def test_non_utf8_session_and_lane_do_not_crash(self):
        (self.d / "bad.jsonl").write_bytes(b"\xff\xfe\x00bad\n")
        write(self.d / "a2.jsonl", [turn("claude-sonnet-5", inp=1)])
        (self.d / "a2" / "subagents").mkdir(parents=True)
        (self.d / "a2" / "subagents" / "l.jsonl").write_bytes(b"\xff\xfe\n")
        r = tr.build_rollup(str(self.d), None)
        # bad main + the session owning the bad lane are both reported; the readable sessions still price
        self.assertEqual(r["unreadable_sessions"], 2)
        self.assertEqual(r["total_usd"], 29.0)
        self.assertIn("; 2 session(s) unreadable", r["line"])

    def test_all_unparsable_session_is_unreadable_not_zero(self):
        d = self.d / "only"
        d.mkdir()
        (d / "junk.jsonl").write_text("not json\n{broken\n")
        r = tr.build_rollup(str(d), None)
        self.assertEqual(r["unreadable_sessions"], 1)
        self.assertTrue(r["line"].endswith("; 1 session(s) unreadable"))
        self.assertEqual(tr.build_rollup(str(self.d), tr.parse_timestamp("2030-01-01T00:00:00Z"))["unreadable_sessions"], 0)

    def test_unparsable_main_with_readable_lane_is_flagged(self):
        d = self.d / "mixed"
        write(d / "m" / "subagents" / "lane.jsonl", [turn("claude-opus-5", out=1_000_000)])
        (d / "m.jsonl").write_text("not json\n")
        r = tr.build_rollup(str(d), None)
        self.assertEqual(r["unreadable_sessions"], 1)
        self.assertIn("; 1 session(s) unreadable", r["line"])

    def test_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(tr.main(["--rollup", str(self.d), "--top", "1"]), tr.OK)
        self.assertEqual(len(out.getvalue().strip().splitlines()), 2)  # summary line + 1 session
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(tr.main(["--rollup", str(self.d / "missing")]), tr.ERROR)


if __name__ == "__main__":
    unittest.main()
