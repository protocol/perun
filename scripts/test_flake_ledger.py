#!/usr/bin/env python3
"""flake_ledger.py: flake detection per tree, quarantine rules, expiry, and the train_flake.sh recording hook."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SCRIPTS))
import flake_ledger as fl  # noqa: E402

DAY = "2026-10-16"


class Ledger(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = self._t.name
        self.addCleanup(self._t.cleanup)

    def run_cli(self, *args, stdin="", today=DAY):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), contextlib.redirect_stdout(out):
            rc = fl.main(["--dir", self.d, "--today", today, *args])
        return rc, out.getvalue()

    def rec(self, tree, text):
        self.run_cli("record", "--tree", tree, stdin=text)

    def test_fail_then_pass_same_tree_is_flake_and_n_trees_quarantine(self):
        for t in ("t1", "t2"):
            self.rec(t, "FAIL a\nPASS a\n")
        rc, out = self.run_cli("quarantine")
        self.assertEqual(out, "")  # 2 flake trees < default 3
        self.rec("t3", "FAIL a\nPASS a\n")
        rc, out = self.run_cli("quarantine")
        self.assertEqual(out, "QUARANTINE a expires=2026-10-30\n")

    def test_same_tree_repeats_count_once(self):
        for _ in range(5):
            self.rec("t1", "FAIL a\nPASS a\n")
        self.assertEqual(self.run_cli("quarantine")[1], "")

    def test_fail_on_one_tree_pass_on_another_is_not_flake(self):
        self.rec("t1", "FAIL a\nFAIL a\n")
        self.rec("t2", "PASS a\n")
        self.rec("t3", "FAIL a\n")
        self.rec("t4", "PASS a\n")
        self.assertEqual(self.run_cli("quarantine", "--n", "1")[1], "")

    def test_consistent_failure_never_quarantined(self):
        for t in ("t1", "t2", "t3"):
            self.rec(t, "FAIL a\nPASS a\n")
        self.rec("t4", "REAL a\n")  # failed the gate and every re-run on the latest tree
        self.assertEqual(self.run_cli("quarantine")[1], "")
        self.assertIn("consistent-fail", self.run_cli("report")[1])

    def test_train_flake_verdict_lines_parse(self):
        self.rec("t1", "FLAKE a (failed 1 of 3 alone)\nREAL b\nnoise line\n")
        rc, out = self.run_cli("report", "--n", "1")
        self.assertIn("FLAKY\ta\tflake_trees=1", out)
        self.assertIn("consistent-fail\tb", out)

    def _quarantined(self):
        for t in ("t1", "t2", "t3"):
            self.rec(t, "FLAKE a\n")
        self.run_cli("quarantine")

    def test_check_quarantined_is_non_blocking_unlisted_blocks(self):
        self._quarantined()
        rc, out = self.run_cli("check", "a", "--tree", "t9")
        self.assertEqual((rc, out), (0, "QUARANTINED a (expires 2026-10-30)\n"))
        rc, out = self.run_cli("check", "a", "z", "--tree", "t9")
        self.assertEqual(rc, 1)
        self.assertIn("BLOCKING z (not quarantined)", out)

    def test_check_blocks_when_consistent_on_tree(self):
        self._quarantined()
        self.rec("t9", "REAL a\n")
        rc, out = self.run_cli("check", "a", "--tree", "t9")
        self.assertEqual(rc, 1)
        self.assertIn("real failure", out)

    def test_expiry_blocks_until_owner_renews(self):
        self._quarantined()
        rc, out = self.run_cli("check", "a", "--tree", "t9", today="2026-11-01")
        self.assertEqual(rc, 1)
        self.assertIn("expired 2026-10-30", out)
        self.run_cli("quarantine")  # never extends an existing entry
        self.assertIn("expires=2026-10-30", self.run_cli("report")[1])
        self.assertIn("RENEWED a expires=2026-11-15", self.run_cli("renew", "a", "--expires", "2026-11-15")[1])
        self.assertEqual(self.run_cli("check", "a", "--tree", "t9")[0], 0)

    def test_malformed_ledger_and_unknown_renew_fail_closed(self):
        Path(self.d, "ledger.jsonl").write_text("not json\n")
        with self.assertRaises(SystemExit) as c:
            self.run_cli("report")
        self.assertEqual(c.exception.code, 2)
        Path(self.d, "ledger.jsonl").write_text("")
        with self.assertRaises(SystemExit) as c:
            self.run_cli("renew", "nope", "--days", "3")
        self.assertEqual(c.exception.code, 2)


class TrainFlakeHook(unittest.TestCase):
    def test_train_flake_records_verdicts(self):
        with tempfile.TemporaryDirectory() as d:
            ids = Path(d, "ids")
            ids.write_text("flaky\nbroken\n")
            # RERUN_CMD: `flaky` passes alone, `broken` always fails alone.
            env = {**os.environ, "RERUN_CMD": '[ "$TEST" != broken ]', "FLAKE_RUNS": "2",
                   "FLAKE_LEDGER_DIR": d + "/led", "FLAKE_TREE": "tree1", "TMPDIR": d}
            r = subprocess.run(["bash", str(SCRIPTS / "train_flake.sh"), str(ids)], env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, r.stderr)  # REAL present: exit code unchanged by the ledger
            self.assertIn("REAL broken", r.stdout)
            r = subprocess.run([sys.executable, str(SCRIPTS / "flake_ledger.py"), "--dir", d + "/led", "report", "--n", "1"],
                               capture_output=True, text=True)
            self.assertIn("FLAKY\tflaky\tflake_trees=1", r.stdout)
            self.assertIn("consistent-fail\tbroken", r.stdout)


if __name__ == "__main__":
    unittest.main()
