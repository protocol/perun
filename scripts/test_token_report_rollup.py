#!/usr/bin/env python3
"""token_report --rollup lean pass: byte-identical to the per-session build_report path on a fictional project dir.

The reference is the old behaviour (rollup priced from build_report); the lean reader skips lines without usage, lines
before the --since window and files not modified in it. Offline; fixtures are generated into a temp dir."""
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

P = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-ceo/scripts/token_report.py"
spec = importlib.util.spec_from_file_location("token_report", P)
tr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tr)

T0 = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def line(rid, minutes, model="claude-sonnet-5", out=5, block=None, sidechain=False, kind="assistant"):
    ts = (T0 + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.123Z")
    e = {"type": kind, "timestamp": ts, "requestId": rid, "isSidechain": sidechain,
         "message": {"model": model, "usage": {"input_tokens": 10, "output_tokens": out, "cache_read_input_tokens": 100,
                                               "cache_creation_input_tokens": 20}}}
    if block is not None:
        e["apiBlockIndex"] = block
    return json.dumps(e)


def noise(minutes):  # a tool-result line: no usage, big
    return json.dumps({"type": "user", "timestamp": (T0 + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ"), "message": {"content": "x" * 5000}})


def write(path, lines, mtime_minutes=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    if mtime_minutes is not None:
        t = (T0 + timedelta(minutes=mtime_minutes)).timestamp()
        os.utime(path, (t, t))


def fixture(root):
    a = root / "proj-a"
    write(a / "s1.jsonl", [line("r1", 0), noise(1), line("r2", 60, block=0), line("r2", 61, block=1, out=9), line("r3", 3000, "claude-opus-5")], 3000)
    write(a / "s1/subagents/agent-1.jsonl", [line("l1", 5, sidechain=True), noise(6), line("l2", 3010, sidechain=True)], 3010)
    (a / "s1/subagents/agent-1.meta.json").write_text(json.dumps({"agentType": "reviewer", "description": "d"}))
    write(a / "s1/subagents/agent-2.jsonl", [noise(7)], 9000)  # no usable turn -> unusable lane (fresh mtime: never skipped)
    write(a / "s2.jsonl", [line("r1", 0), line("r2", 60, block=0), line("r4", 6000)], 6000)  # resumed copy of r1/r2 then new
    write(a / "bad.jsonl", ["not json", "{broken"], 9000)
    write(a / "empty-usage.jsonl", [noise(8)], 9000)
    b = root / "proj-b"
    write(b / "s3.jsonl", [line("r5", 100, "claude-sonnet-4-6"), line("r6", 9000)], 9000)
    return root


def old_session(path, since, seen, turns_out=None):  # the pre-lean reference: full build_report
    return tr.build_report(path, since, 0, tr.DEFAULT_RATES, seen=seen, turns_out=turns_out)


class Rollup(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = fixture(pathlib.Path(self.td.name))

    def tearDown(self):
        self.td.cleanup()

    def both(self, since, **kw):
        new = tr.build_rollup(str(self.root), since, **kw)
        keep = tr.rollup_session
        tr.rollup_session = old_session
        try:
            old = tr.build_rollup(str(self.root), since, **kw)
        finally:
            tr.rollup_session = keep
        return old, new

    def test_matches_old_path_all_time(self):
        old, new = self.both(None, by="day", group="agent")
        self.assertEqual(json.dumps(new, sort_keys=True), json.dumps(old, sort_keys=True))
        self.assertGreater(new["total_usd"], 0)
        self.assertEqual(new["lanes"], 1)
        self.assertEqual(new["unreadable_lanes"], 1)
        self.assertEqual(new["unreadable_sessions"], 1)  # bad.jsonl only; the usage-less valid file is not bad

    def test_dedupes_resumed_turns_once(self):
        _, new = self.both(None)
        raw = sum(s["raw_tokens"] for s in new["sessions"])
        # 8 distinct requests (r1..r6 mains, l1, l2 lane) at 135 tokens, r2 keeps its higher block (out=9 -> 139); s2's r1/r2 copies bill once
        self.assertEqual(raw, 135 * 7 + 139)

    def test_matches_old_path_windowed(self):
        for since in (T0 + timedelta(minutes=2000), T0 + timedelta(minutes=60), T0 + timedelta(minutes=3000, seconds=-1)):
            old, new = self.both(since, by="day", group="project")
            self.assertEqual(json.dumps(new, sort_keys=True), json.dumps(old, sort_keys=True), since)
        # past every file: nothing counted (the old path would also report the unreadable files it had to open)
        self.assertEqual(self.both(T0 + timedelta(minutes=200000))[1]["sessions"], [])

    def test_old_files_skipped_unread(self):
        reads = []
        keep = tr.read_usage_entries
        tr.read_usage_entries = lambda p, floor=None: (reads.append(os.path.basename(p)), keep(p, floor))[1]
        try:
            tr.build_rollup(str(self.root), T0 + timedelta(minutes=5000))
        finally:
            tr.read_usage_entries = keep
        self.assertEqual(sorted(reads), ["agent-2.jsonl", "bad.jsonl", "empty-usage.jsonl", "s2.jsonl", "s3.jsonl"])  # s1 and agent-1 are older than the window

    def test_read_usage_entries(self):
        p = self.root / "proj-a/s1.jsonl"
        self.assertEqual(len(tr.read_usage_entries(str(p))[0]), 4)
        self.assertEqual(len(tr.read_usage_entries(str(p), "2026-01-03T00:00:00")[0]), 1)  # line before floor dropped unparsed
        self.assertEqual(tr.read_usage_entries(str(self.root / "proj-a/bad.jsonl")), ([], False))
        self.assertEqual(tr.read_usage_entries(str(self.root / "proj-a/empty-usage.jsonl")), ([], True))


if __name__ == "__main__":
    unittest.main()
