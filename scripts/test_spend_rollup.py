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
