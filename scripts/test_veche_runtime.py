#!/usr/bin/env python3
"""veche.py run-time output: stderr is not silent while a long council runs and --alarm-s fires in flight (#2138),
--json-out writes the record to a file and a gate skip is announced on stderr (#2139). Stdlib only."""
import json, re, subprocess, sys, tempfile, unittest
from pathlib import Path

VECHE = Path(__file__).resolve().parent.parent / ".claude/skills/idea-critic/scripts/veche.py"
SEAT = '''import sys, json, os, time
cfg = json.load(open(sys.argv[1])); sys.stdin.read()
open(cfg["log"], "a").write("call\\n")
for _ in range(cfg["hold"] * 20):  # slow seat: wait until the test releases it (bounded, so a hung test cannot hang CI)
    if os.path.exists(cfg["release"]): break
    time.sleep(0.05)
open(cfg["finished"], "w").close()
if cfg["fail"]: sys.exit(1)
print(json.dumps({"verdict": "REVISE", "claims": [], "would_change_it": "w"}))
'''


def args(d, hold=0, fail=False, extra=()):
    """veche.py argv over two fake seats; with hold > 0 they wait for d/release (up to `hold` seconds) and then write d/finished."""
    (d / "seat.py").write_text(SEAT)
    (d / "cfg.json").write_text(json.dumps({"log": str(d / "log"), "hold": hold, "fail": fail,
                                            "release": str(d / "release"), "finished": str(d / "finished")}))
    return [sys.executable, str(VECHE), "--cmd", f"{sys.executable} {d / 'seat.py'} {d / 'cfg.json'}", "--claim", "c", "--steelman", "s",
            "--root", str(d), "--review-date", "2030-01-31", "--lenses", "skeptic,better-way", *extra]


def run(extra=()):
    d = Path(tempfile.mkdtemp())
    r = subprocess.run(args(d, extra=extra), capture_output=True, text=True)
    return r, d


class Held:
    """A council whose seats stay busy until release(); `first` is its first stderr line, read while they are still busy."""

    def __init__(self, case, fail=False, extra=()):
        self.d = Path(tempfile.mkdtemp())
        self.p = subprocess.Popen(args(self.d, 10, fail, extra), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.first = self.p.stderr.readline()
        self.busy = not (self.d / "finished").exists()  # no seat had finished when that line was printed
        case.addCleanup(self.p.kill)

    def release(self):
        (self.d / "release").touch()
        out, err = self.p.communicate(timeout=30)
        return json.loads(out), self.first + err


class InFlight(unittest.TestCase):
    """#2138: a council that runs long says so while it runs, not only after it finished."""

    def test_alarm_fires_while_the_council_is_still_running(self):
        h = Held(self, extra=["--alarm-s", "1"])
        self.assertIn("COUNCIL_BLOCKING_WORK", h.first)
        self.assertIn("still running", h.first)
        self.assertTrue(h.busy)  # printed before any seat finished, not after the run
        rec, err = h.release()
        self.assertEqual((h.p.returncode, rec["verdict"], rec["blocking_alarm"]), (0, "REVISE", True))
        self.assertEqual(err.count("COUNCIL_BLOCKING_WORK"), 1)  # the finished run does not repeat it

    def test_alarm_line_counts_the_calls_started(self):
        h = Held(self, extra=["--alarm-s", "1"])
        self.assertRegex(h.first, r"COUNCIL_BLOCKING_WORK: council still running after 1s \(2 calls started\); default_action=hold")
        h.release()

    def test_heartbeat_while_running(self):
        h = Held(self, extra=["--progress-s", "1"])
        self.assertRegex(h.first, r"^veche: running \d+s, 2 calls started$")
        self.assertTrue(h.busy)
        rec, err = h.release()
        self.assertNotIn("COUNCIL_BLOCKING_WORK", err)  # the default --alarm-s (300) is far away
        self.assertEqual(rec["verdict"], "REVISE")

    def test_heartbeat_can_be_turned_off(self):
        r, _ = run(["--progress-s", "0", "--alarm-s", "100"])
        self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_failed_run_still_reports_its_outcome_after_an_in_flight_alarm(self):
        h = Held(self, fail=True, extra=["--alarm-s", "1"])
        self.assertIn("still running", h.first)
        rec, err = h.release()
        lines = [l for l in err.splitlines() if "COUNCIL_BLOCKING_WORK" in l]
        self.assertEqual((h.p.returncode, rec["verdict"], len(lines)), (3, "COULD_NOT_DECIDE", 2))
        self.assertIn("default_action=hold", lines[1])


class JsonOut(unittest.TestCase):
    """#2139: --json-out PATH keeps the record in a file; a skipped council is announced on stderr."""

    def test_record_is_written_to_the_path_and_still_printed(self):
        d = Path(tempfile.mkdtemp())
        out = d / "rec.json"
        out.write_text("stale")
        r = subprocess.run(args(d, extra=["--json-out", str(out)]), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(out.read_text()), json.loads(r.stdout))
        self.assertEqual(json.loads(out.read_text())["verdict"], "REVISE")

    def test_failure_and_gate_records_are_written_too(self):
        d = Path(tempfile.mkdtemp())
        for extra, rc, verdict in ((["--max-calls", "1"], 3, "COULD_NOT_DECIDE"), (["--stakes", "low", "--reversibility", "easy"], 4, "NOT_CONVENED")):
            out = d / f"{verdict}.json"
            r = subprocess.run(args(d, extra=["--json-out", str(out), *extra]), capture_output=True, text=True)
            self.assertEqual((r.returncode, json.loads(out.read_text())["verdict"]), (rc, verdict))

    def test_unwritable_path_is_refused_before_any_call(self):
        d = Path(tempfile.mkdtemp())
        r = subprocess.run(args(d, extra=["--json-out", str(d / "missing" / "rec.json")]), capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--json-out", r.stderr)
        self.assertIn("cannot write", r.stderr)
        self.assertFalse((d / "log").exists())  # no seat was paid for

    def test_gate_skip_is_announced_and_says_the_twin_was_ignored(self):
        gate = ["--stakes", "low", "--reversibility", "easy"]
        r, d = run(extra=gate + ["--twin"])
        self.assertEqual((r.returncode, json.loads(r.stdout)["verdict"]), (4, "NOT_CONVENED"))
        self.assertIn("NOT_CONVENED", r.stderr)
        self.assertIn("stakes=low", r.stderr)
        self.assertIn("--twin ignored", r.stderr)
        self.assertFalse((d / "log").exists())
        r, _ = run(extra=gate)
        self.assertIn("NOT_CONVENED", r.stderr)
        self.assertNotIn("--twin", r.stderr)

    def test_a_convened_council_does_not_announce_a_skip(self):
        r, _ = run(extra=["--stakes", "high", "--reversibility", "hard", "--twin"])
        self.assertNotIn("NOT_CONVENED", r.stderr)


if __name__ == "__main__":
    unittest.main()
