#!/usr/bin/env python3
"""Veche closers: a go/go-if decision needs a measurable kill criterion (validator + veche output agree),
--twin-cmd / twin_cmd_distinct, and --due lists overdue records. Stdlib only, stub commands, no model calls."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

SK = Path(__file__).resolve().parent.parent / ".claude/skills/idea-critic/scripts"
FAKE = '''import sys, json
p = sys.stdin.read(); kill = sys.argv[1]
if "STAGE: CRITIQUE" in p: print("{}"); sys.exit()
if "DECISION:" in p: print(json.dumps({"dissent": "d", "kill_criterion": kill})); sys.exit()
print(json.dumps({"verdict": "REVISE", "claims": [], "would_change_it": "w", "kill_criterion": kill,
                  "scores": {"go": {"impact": 5}, "do-nothing": {"impact": 1}}}))
'''


def run(kill, *extra, cmds=1):
    d = Path(tempfile.mkdtemp())
    (d / "fake.py").write_text(FAKE)
    cmd = []
    for _ in range(cmds):
        cmd += ["--cmd", f"{sys.executable} {d / 'fake.py'} '{kill}'"]
    seat = f"{sys.executable} {d / 'fake.py'} '{kill}'"
    extra = [seat.replace(" '", "   '") if x == "@SEAT@" else x for x in extra]  # same argv, extra spaces
    r = subprocess.run([sys.executable, str(SK / "veche.py"), *cmd, "--claim", "c", "--steelman", "s", "--root", str(d),
                        "--review-date", "2030-01-31", "--option", "go", "--criteria", "impact:1", *extra],
                       capture_output=True, text=True)
    return json.loads(r.stdout), d


def validate(rec, d):
    f = d / "rec.json"
    f.write_text(json.dumps(rec))
    return subprocess.run([sys.executable, str(SK / "validate_verdict.py"), "--file", str(f)], capture_output=True, text=True)


class Closers(unittest.TestCase):
    def test_validator_rejects_unmeasurable_go_and_accepts_digit_or_window(self):
        rec, d = run("M below 5 by day 30")
        self.assertEqual(rec["decision"], "go")
        self.assertEqual(validate(rec, d).returncode, 0)
        for bad in (["revert if flaky"], ["UNVERIFIED: 30 days"], []):
            r = validate(dict(rec, kill_criteria=bad), d)
            self.assertEqual(r.returncode, 1)
        for ok in ("by 2026-12-01 revert", "within 7 days no uptake"):
            self.assertEqual(validate(dict(rec, kill_criteria=[ok], decision="go-if x"), d).returncode, 0)
        self.assertEqual(validate(dict(rec, kill_criteria=["revert if flaky"], decision="no-go"), d).returncode, 0)

    def test_veche_output_stays_valid_when_no_measurable_kill(self):
        rec, d = run("revert if flaky")
        self.assertEqual(rec["decision"], "flag")
        self.assertEqual(validate(rec, d).returncode, 0)

    def test_twin_cmd_distinct(self):
        rec, _ = run("x 1", "--twin")
        self.assertFalse(rec["twin_cmd_distinct"])
        rec, d = run("x 1", "--twin", "--twin-cmd", f"{sys.executable} {Path(tempfile.mkdtemp())}/none.py")
        self.assertTrue(rec["twin_cmd_distinct"])
        self.assertNotIn("twin_cmd_distinct", run("x 1")[0])

    def test_due_lists_overdue_without_outcome(self):
        d = Path(tempfile.mkdtemp())
        for n, r in {"a": {"review_date": "2020-01-01", "claim": "c"}, "b": {"review_date": "2020-01-01", "outcome": "ok"},
                     "c": {"review_date": "2999-01-01"}}.items():
            (d / f"{n}.json").write_text(json.dumps(r))
        (d / "bad.json").write_text("{")
        p = subprocess.run([sys.executable, str(SK / "veche.py"), "--due", str(d)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertEqual([x["file"] for x in json.loads(p.stdout)], ["a.json", "bad.json"])

    def test_go_detection_and_measurable_words(self):
        rec, d = run("M below 5 by day 30")
        for dec in ("GO", "Go-if: x", " go now", "go, if x", "go\tx", "go-if(x)"):
            self.assertEqual(validate(dict(rec, kill_criteria=["revert if flaky"], decision=dec), d).returncode, 1, dec)
        for dec in ("going", "no-go", "gone"):
            self.assertEqual(validate(dict(rec, kill_criteria=["revert if flaky"], decision=dec), d).returncode, 0, dec)
        for ok in ("revert if flaky within 7 days", "stop by next quarter", "revisit after the next release"):
            self.assertEqual(validate(dict(rec, kill_criteria=[ok]), d).returncode, 0, ok)
        self.assertEqual(validate(dict(rec, kill_criteria=["Phase two fails"]), d).returncode, 1)

    def test_downgrade_recorded_and_twin_kill_rescues(self):
        rec, _ = run("revert if flaky")
        self.assertEqual(rec["decision_downgraded_from"], "go")
        rec, _ = run("revert if flaky", "--twin")
        self.assertEqual(rec["decision_downgraded_from"], "go")
        self.assertNotIn("decision_downgraded_from", run("x 1")[0])

    def test_twin_cmd_rules(self):
        rec, d = run("x 1", "--twin", "--twin-cmd", "@SEAT@")
        self.assertFalse(rec["twin_cmd_distinct"])
        seat = f"{sys.executable} {d / 'fake.py'} 'x 1'"
        base = [sys.executable, str(SK / "veche.py"), "--cmd", seat, "--claim", "c", "--steelman", "s", "--root", str(d)]
        for extra in (["--twin", "--twin-cmd", "  "], ["--twin-cmd", seat]):
            p = subprocess.run(base + extra, capture_output=True, text=True)
            self.assertEqual(p.returncode, 2, extra)
        p = subprocess.run(base + ["--tw"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

    def test_due_edge_cases(self):
        d = Path(tempfile.mkdtemp())
        today = __import__("datetime").date.today().isoformat()
        for n, r in {"today": {"review_date": today}, "null": {"review_date": "2020-01-01", "outcome": None},
                     "short": {"review_date": "2026-1-5"}, "none": {}, "list": []}.items():
            (d / f"{n}.json").write_text(json.dumps(r))
        (d / "empty.json").write_text("")
        p = subprocess.run([sys.executable, str(SK / "veche.py"), "--due", str(d)], capture_output=True, text=True)
        got = {x["file"]: x for x in json.loads(p.stdout)}
        self.assertEqual(p.returncode, 0)
        self.assertEqual(sorted(got), ["empty.json", "list.json", "none.json", "null.json", "short.json", "today.json"])
        self.assertNotIn("error", got["today.json"])
        self.assertNotIn("error", got["null.json"])
        for n in ("empty", "list", "none", "short"):
            self.assertIn("error", got[n + ".json"])
        p = subprocess.run([sys.executable, str(SK / "veche.py"), "--due", str(d / "missing")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        e = Path(tempfile.mkdtemp())
        p = subprocess.run([sys.executable, str(SK / "veche.py"), "--due", str(e)], capture_output=True, text=True)
        self.assertEqual((p.returncode, json.loads(p.stdout)), (0, []))

    def test_bad_twin_cmd_quote_fails_before_any_seat_runs(self):
        d = Path(tempfile.mkdtemp())
        mark = d / "seat-ran"
        (d / "seat.py").write_text(f"open({str(mark)!r}, 'w').close()")
        r = subprocess.run([sys.executable, str(SK / "veche.py"), "--cmd", f"{sys.executable} {d / 'seat.py'}", "--twin",
                            "--twin-cmd", "echo 'x", "--claim", "c", "--steelman", "s", "--root", str(d),
                            "--review-date", "2030-01-31", "--option", "go", "--criteria", "impact:1"],
                           capture_output=True, text=True)
        rec = json.loads(r.stdout)
        self.assertEqual((r.returncode, rec["verdict"]), (3, "COULD_NOT_DECIDE"))
        self.assertIn("--twin-cmd", rec["reason"])
        self.assertFalse(mark.exists())

    def test_is_go_word_boundary(self):
        sys.path.insert(0, str(SK))
        from validate_verdict import is_go
        self.assertFalse(any(map(is_go, ("go-live", "goal", "go_x"))))
        self.assertTrue(all(map(is_go, ("go", "go-if x", "Go: y", " go, z", "go (a)", "go\tq"))))


if __name__ == "__main__":
    unittest.main()
