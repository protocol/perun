#!/usr/bin/env python3
"""lane_guard.hot_files flags files that more than N other open PRs also touch (offline, stubbed PR file sets)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts"))
import lane_guard  # noqa: E402


class HotFiles(unittest.TestCase):
    def test_flags_only_files_over_limit(self):
        prs = {i: ["LEDGER.md", f"f{i}.py"] for i in range(6)}
        prs[9] = ["other.md"]
        self.assertEqual(lane_guard.hot_files(["LEDGER.md", "new.py"], prs), {"LEDGER.md": 6})

    def test_at_limit_is_quiet(self):
        prs = {i: ["LEDGER.md"] for i in range(5)}
        self.assertEqual(lane_guard.hot_files(["LEDGER.md"], prs), {})

    def test_no_open_prs(self):
        self.assertEqual(lane_guard.hot_files(["a"], {}), {})


if __name__ == "__main__":
    unittest.main()
