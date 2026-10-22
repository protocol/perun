#!/usr/bin/env python3
"""Regression: landing_watchdog emits a standing line once per session and again only when it changes."""
import sys
import os
import time
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_landing_watchdog import GREEN, Base, lw  # noqa: E402


class Once(Base):
    def hook(self, sid, now):
        return lw.hook({"hook_event_name": "UserPromptSubmit", "cwd": str(self.repo), "session_id": sid}, now=now)

    def test_emits_once_then_silent_but_reemits_on_change_and_new_session(self):
        t = time.time()
        first = self.hook("s1", t)
        self.assertIn("Landing stalled", first)
        self.assertIsNone(self.hook("s1", t + 60), "same line in the same session is not repeated")
        self.assertEqual(self.hook("s2", t + 120), first, "another session still gets it once")
        self.set_prs([])  # stall clears after the window: silent, stamp resets
        self.assertIsNone(self.hook("s1", t + 16 * 60))
        self.set_prs([GREEN])
        self.assertEqual(self.hook("s1", t + 32 * 60), first, "recurrence after a clear re-emits")

    def test_spawn_always_gets_the_line(self):
        t = time.time()
        self.assertTrue(self.hook("s1", t))
        spawn = {"hook_event_name": "PreToolUse", "tool_name": "Agent", "cwd": str(self.repo), "session_id": "s1"}
        self.assertEqual(lw.hook(spawn, now=t + 60), self.hook("s2", t + 61))
        self.assertIsNone(self.hook("s1", t + 62), "the spawn did not touch the prompt stamp")

    def test_no_session_id_is_not_deduped(self):
        t = time.time()
        p = {"hook_event_name": "UserPromptSubmit", "cwd": str(self.repo)}
        self.assertTrue(lw.hook(p, now=t))
        self.assertTrue(lw.hook(p, now=t + 60))

    def test_reshown_after_ttl_so_compaction_recovers(self):
        t = time.time()
        self.assertEqual(lw.STAMP_TTL_S, 15 * 60)
        first = self.hook("s1", t)
        self.assertIsNone(self.hook("s1", t + 60))
        self.assertEqual(self.hook("s1", t + lw.STAMP_TTL_S + 60), first)

    def test_stale_stamps_pruned_and_write_failure_still_returns_line(self):
        t = time.time()
        old = Path(lw.cache_file(str(self.repo)) + ".gone")
        old.write_text("x")
        os.utime(old, (t - lw.PRUNE_S - 60, t - lw.PRUNE_S - 60))
        self.assertTrue(self.hook("s1", t))
        self.assertFalse(old.exists())
        with mock.patch("builtins.open", side_effect=OSError("ro")), mock.patch.object(lw, "_line", return_value="L"):
            self.assertEqual(self.hook("s3", t), "L")

    def test_nul_in_session_id_still_returns_line(self):
        with mock.patch.object(lw, "_line", return_value="L"):
            self.assertEqual(self.hook("a\x00b", time.time()), "L")


if __name__ == "__main__":
    unittest.main()
