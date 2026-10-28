#!/usr/bin/env python3
"""Tests for Veche's timebox default, blocking alarm and anonymized peer ranking (scripts/veche.py). Stdlib only."""
import json, re, subprocess, sys, tempfile, unittest
from pathlib import Path

SK = Path(__file__).resolve().parent.parent / ".claude/skills/idea-critic/scripts"
FAKE = '''import sys, json, re
p = sys.stdin.read()
if "STAGE: CRITIQUE" in p:
    labels = sorted(set(re.findall(r"ANSWER ([A-H]) \\(data", p)))
    print(json.dumps({"verdict": "REVISE", "attacks": [], "ranking": labels}))
elif "LENS: cpo " in p:
    print(json.dumps({"verdict": "HOLD", "claims": [], "would_change_it": "w"}))
else:
    print(json.dumps({"verdict": "REVISE", "claims": [], "would_change_it": "w"}))
'''

Q = '''import sys, json, re
p = sys.stdin.read()
if "STAGE: CRITIQUE" in p:
    open(sys.argv[0] + ".log", "a").write(p)
    qual = {m.group(1): int(m.group(2)) for m in re.finditer(r"ANSWER ([A-H]) \\(data.*?QUAL=(\\d)", p, re.S)}
    print(json.dumps({"verdict": "REVISE", "attacks": [], "ranking": sorted(qual, key=qual.get, reverse=True)}))
else:
    lens = re.search(r"LENS: ([a-z-]+) ", p).group(1)
    q = {"cpo": 9, "cto": 5, "cfo": 1}[lens]
    print(json.dumps({"verdict": "HOLD" if lens == "cpo" else "REVISE", "claims": [], "would_change_it": f"QUAL={q} from {lens}"}))
'''


class T(unittest.TestCase):
    def run_v(self, cmd=None, extra=()):
        d = Path(tempfile.mkdtemp())
        (d / "fake.py").write_text(FAKE)
        cmd = cmd or f"{sys.executable} {d / 'fake.py'}"
        r = subprocess.run([sys.executable, str(SK / "veche.py"), "--cmd", cmd, "--claim", "c", "--steelman", "s",
                            "--root", str(d), "--review-date", "2030-01-31", *extra], capture_output=True, text=True)
        return r.returncode, json.loads(r.stdout), r.stderr

    def test_peer_ranking_is_borda_over_anonymized_labels(self):
        rc, rec, _ = self.run_v(extra=["--lenses", "cpo,cto,cfo"])
        self.assertEqual((rc, rec["critique_ran"]), (0, True))
        self.assertEqual(set(rec["peer_ranking"]), {"cpo", "cto", "cfo"})

    def test_borda_direction_top_ranked_gets_highest_mean(self):
        d = Path(tempfile.mkdtemp())
        (d / "q.py").write_text(Q)
        rc, rec, _ = self.run_v(cmd=f"{sys.executable} {d / 'q.py'}", extra=["--lenses", "cpo,cto,cfo"])
        self.assertEqual(rec["peer_ranking"], {"cpo": 1.0, "cto": 0.5, "cfo": 0.0})

    def test_peer_prompts_hide_lens_names(self):
        d = Path(tempfile.mkdtemp())
        (d / "q.py").write_text(Q)
        self.run_v(cmd=f"{sys.executable} {d / 'q.py'}", extra=["--lenses", "cpo,cto,cfo"])
        seen = (d / "q.py.log").read_text()
        self.assertIn("[seat]", seen)
        self.assertNotRegex(seen, r"from (cpo|cto|cfo)")

    def test_failed_twin_keeps_the_verdict(self):
        d = Path(tempfile.mkdtemp())
        (d / "t.py").write_text(FAKE.replace('if "STAGE: CRITIQUE"', 'if "STAGE: TWIN" in p:\n    sys.exit(1)\nif "STAGE: CRITIQUE"'))
        rc, rec, _ = self.run_v(cmd=f"{sys.executable} {d / 't.py'}", extra=["--lenses", "cpo,cto", "--twin"])
        self.assertEqual((rc, rec["verdict"]), (0, "HOLD"))
        self.assertIn("evil-twin", [x[0] for x in rec["dropped"]])

    def test_one_failed_seat_is_dropped_not_fatal(self):
        d = Path(tempfile.mkdtemp())
        (d / "f.py").write_text(FAKE.replace('elif "LENS: cpo "', 'elif "LENS: cfo " in p:\n    sys.exit(1)\nelif "LENS: cpo "'))
        rc, rec, _ = self.run_v(cmd=f"{sys.executable} {d / 'f.py'}", extra=["--lenses", "cpo,cto,cfo"])
        self.assertEqual(rc, 0)
        self.assertEqual([x[0] for x in rec["dropped"]], ["cfo"])

    def test_stuck_council_gets_default_and_alarm(self):
        for rev, act in (("easy", "proceed"), ("hard", "hold"), (None, "hold")):
            extra = ["--stakes", "high", "--max-calls", "1"] + (["--reversibility", rev] if rev else [])
            rc, rec, err = self.run_v(extra=extra)
            self.assertEqual((rc, rec["verdict"], rec["default_action"], rec["blocking_alarm"]), (3, "COULD_NOT_DECIDE", act, True), rev)
            self.assertIn("COUNCIL_BLOCKING_WORK", err)

    def test_slow_council_alarms_but_keeps_its_verdict(self):
        rc, rec, err = self.run_v(extra=["--lenses", "cpo,cto", "--alarm-s", "0"])
        self.assertEqual(rc, 0)
        self.assertTrue(rec["blocking_alarm"] and "default_action" not in rec)
        self.assertIn("COUNCIL_BLOCKING_WORK", err)

    def test_fast_decided_council_is_quiet(self):
        rc, rec, err = self.run_v(extra=["--lenses", "cpo,cto"])
        self.assertEqual((rc, "blocking_alarm" in rec, err), (0, False, ""))

    def test_criteria_error_shows_expected_format(self):
        rc, rec, _ = self.run_v(extra=["--option", "ship", "--criteria", "impact is key"])
        self.assertEqual(rc, 3)
        self.assertIn("name:weight", rec["reason"])
        self.assertIn("impact:3,cost:2", rec["reason"])

    def test_seats_run_in_parallel(self):
        d = Path(tempfile.mkdtemp())
        (d / "slow.py").write_text("import sys, time, json\nsys.stdin.read(); time.sleep(1)\n"
                                   "print(json.dumps({'verdict': 'REVISE', 'claims': [], 'would_change_it': 'w'}))\n")
        rc, rec, _ = self.run_v(cmd=f"{sys.executable} {d / 'slow.py'}", extra=["--lenses", "cpo,cto,cfo"])
        self.assertEqual(rc, 0)
        self.assertLess(rec["cost"]["round1_s"], 2.5)  # serial would be >= 3s


if __name__ == "__main__":
    unittest.main()
