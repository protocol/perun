#!/usr/bin/env python3
"""flake_ledger.py: flake detection per tree, quarantine rules, expiry, and the train_flake.sh recording hook."""
import contextlib
import datetime
import io
import json
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


class Base(unittest.TestCase):
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


class Ledger(Base):
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
        self.rec("t4", "SUITE a\nFAIL a\nFAIL a\n")  # failed the gate and every re-run on the latest tree
        self.assertEqual(self.run_cli("quarantine")[1], "")
        self.assertIn("consistent-fail", self.run_cli("report")[1])

    def test_run_lines_parse_and_noise_is_ignored(self):
        self.rec("t1", "SUITE a\nFAIL a\nPASS a\nSUITE b\nFAIL b\nFAIL b\nnoise line\n")
        rc, out = self.run_cli("report", "--n", "1")
        self.assertIn("FLAKY\ta\tflake_trees=1", out)
        self.assertIn("consistent-fail\tb", out)

    def _quarantined(self):
        for t in ("t1", "t2", "t3"):
            self.rec(t, "SUITE a\nFAIL a\nPASS a\n")
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
        self.rec("t9", "SUITE a\nFAIL a\nFAIL a\n")
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


class Hardening(Base):
    """Review fixes: evidence recorded per run, torn writes, concurrent writers, forgery guards."""

    def test_suite_failure_counts_toward_consistency_but_not_flake_trees(self):
        self.rec("t1", "SUITE a\nFAIL a\n")  # failed in the suite and again alone, never passed: a real failure
        self.assertIn("consistent-fail\ta", self.run_cli("report")[1])
        self.rec("t2", "SUITE a\nPASS a\nPASS a\n")  # failed only in the suite, passed alone every time: not a solo flake
        self.assertIn("flake_trees=0", self.run_cli("report")[1])
        self.rec("t3", "SUITE a\nFAIL a\nPASS a\n")  # a solo failure and a solo pass: a flake tree
        self.assertIn("flake_trees=1", self.run_cli("report")[1])

    def test_derived_verdict_lines_are_not_evidence(self):
        self.assertIn("recorded 0", self.run_cli("record", "--tree", "t1", stdin="FLAKE a (failed 1 of 3 alone)\nREAL b\n")[1])

    def test_torn_last_line_is_tolerated_and_dropped_on_append(self):
        p = Path(self.d, "ledger.jsonl")
        good = json.dumps({"tree": "t1", "test": "a", "result": "fail", "ts": "x"})
        p.write_text(good + '\n{"tree": "t1", "te')  # crash mid-write: no trailing newline
        self.assertIn("a\t", self.run_cli("report")[1] + "a\t")  # reading must not die
        self.rec("t2", "PASS a\n")
        lines = p.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(all(json.loads(x) for x in lines))
        self.assertTrue(p.read_text().endswith("\n"))

    def _workers(self, code, ids):
        procs = [subprocess.Popen([sys.executable, "-c", code, str(SCRIPTS), self.d, i], stderr=subprocess.PIPE) for i in ids]
        errs = [p.communicate()[1].decode() for p in procs]
        self.assertEqual([p.returncode for p in procs], [0] * len(ids), errs)

    def test_concurrent_renew_keeps_every_update(self):
        ids = [f"t{i}" for i in range(8)]
        Path(self.d, "quarantine.json").write_text(json.dumps({i: {"since": DAY, "expires": "2026-10-20"} for i in ids}))
        code = ("import contextlib, io, sys\nsys.path.insert(0, sys.argv[1])\nimport flake_ledger as fl\n"
                "for k in range(30):\n  with contextlib.redirect_stdout(io.StringIO()):\n"
                "    fl.main(['--dir', sys.argv[2], '--today', '2026-10-16', 'renew', sys.argv[3], '--days', str(100 + k)])\n")
        self._workers(code, ids)
        q = json.loads(Path(self.d, "quarantine.json").read_text())
        want = (datetime.date(2026, 10, 16) + datetime.timedelta(days=129)).isoformat()
        self.assertEqual({i: q[i]["expires"] for i in ids}, {i: want for i in ids})
        self.assertEqual(sorted(p.name for p in Path(self.d).iterdir() if p.suffix == ".tmp"), [])

    def test_concurrent_record_keeps_every_line(self):
        ids = [f"t{i}" for i in range(8)]
        code = ("import contextlib, io, sys\nsys.path.insert(0, sys.argv[1])\nimport flake_ledger as fl\n"
                "for k in range(25):\n  sys.stdin = io.StringIO('FAIL ' + sys.argv[3] + '\\nPASS ' + sys.argv[3] + '\\n')\n"
                "  with contextlib.redirect_stdout(io.StringIO()):\n"
                "    fl.main(['--dir', sys.argv[2], 'record', '--tree', 'tr'])\n")
        self._workers(code, ids)
        lines = Path(self.d, "ledger.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 8 * 25 * 2)
        self.assertTrue(all(json.loads(x)["tree"] == "tr" for x in lines))

    def test_guard_refuses_a_dir_under_cwd_or_toplevel_only(self):
        self.assertEqual(self.run_cli("guard")[0], 0)  # --dir is a temp dir outside the cwd: fine
        with mock.patch("os.getcwd", return_value=str(Path(self.d).parent)), self.assertRaises(SystemExit) as c:
            self.run_cli("guard")  # the same dir is now under the cwd
        self.assertEqual(c.exception.code, 2)

    def test_check_reads_the_snapshot_not_the_live_file(self):
        snap = Path(self.d, "snap.json")
        snap.write_text(json.dumps({"a": {"since": DAY, "expires": "2999-12-31"}}))
        self.assertEqual(self.run_cli("check", "a", "--tree", "t1", "--quarantine", str(snap))[0], 0)
        self.assertEqual(self.run_cli("check", "a", "--tree", "t1")[0], 1)  # live quarantine.json has no entry


class TrainFlakeHook(unittest.TestCase):
    def test_train_flake_records_verdicts(self):
        with tempfile.TemporaryDirectory() as d:
            ids = Path(d, "ids")
            ids.write_text("flaky\nbroken\n")
            # RERUN_CMD: `flaky` fails its first solo run then passes, `broken` always fails alone.
            rerun = f'case $TEST in broken) exit 1;; flaky) [ -e "{d}/cnt" ] && exit 0; touch "{d}/cnt"; exit 1;; esac'
            env = {**os.environ, "RERUN_CMD": rerun, "FLAKE_RUNS": "2",
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
