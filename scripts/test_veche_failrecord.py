#!/usr/bin/env python3
"""A COULD_NOT_DECIDE record from veche.py keeps what the council spent and why each seat dropped (#2135). Stdlib only."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

SK = Path(__file__).resolve().parent.parent / ".claude/skills/idea-critic/scripts"
OK = json.dumps({"verdict": "REVISE", "claims": [], "would_change_it": "w"})
FAKE = '''import sys, json
cfg = json.load(open(sys.argv[1])); p = sys.stdin.read()
for lens, out in cfg.items():
    if "LENS: " + lens + " " in p:
        if out is None: sys.exit(2)
        print(out)
'''


def council(answers, *extra):
    """Run veche.py over a fake --cmd that answers per lens (None = exit 2); -> (exit code, record, stdout)."""
    d = Path(tempfile.mkdtemp())
    (d / "fake.py").write_text(FAKE)
    (d / "cfg.json").write_text(json.dumps(answers))
    r = subprocess.run([sys.executable, str(SK / "veche.py"), "--cmd", f"{sys.executable} {d / 'fake.py'} {d / 'cfg.json'}",
                        "--claim", "c", "--steelman", "s", "--root", str(d), "--review-date", "2030-01-31", *extra],
                       capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout), r.stdout


class FailRecord(unittest.TestCase):
    def test_too_few_seats_keeps_each_seats_reason_and_the_call_cost(self):
        rc, rec, out = council({"skeptic": OK, "better-way": None, "kill-criteria": "not json at all"})
        self.assertEqual((rc, rec["verdict"]), (3, "COULD_NOT_DECIDE"))
        rows = dict(rec["dropped"])
        self.assertEqual(set(rows), {"better-way", "kill-criteria"})
        self.assertEqual(rows["better-way"], "cmd exit 2")
        self.assertIn("no JSON object", rows["kill-criteria"])  # the specific parse failure, not a generic line
        self.assertEqual(rec["cost"]["calls"], 3)
        self.assertGreater(rec["cost"]["chars"], 0)
        self.assertIn("wall_s", rec["cost"])
        self.assertTrue(rec["reason"].strip())

    def test_cap_hit_names_the_capped_seat_and_counts_only_paid_calls(self):
        rc, rec, _ = council({l: OK for l in ("skeptic", "better-way", "kill-criteria")}, "--max-calls", "2")
        self.assertEqual((rc, rec["verdict"], rec["reason"]), (3, "COULD_NOT_DECIDE", "cap reached before call"))
        self.assertEqual(rec["cost"]["calls"], 2)
        self.assertEqual([r[1] for r in rec["dropped"]], ["cap reached before call"])  # exactly one seat was refused

    def test_malformed_answers_say_why(self):
        bad = {"skeptic": json.dumps({"verdict": "MAYBE", "claims": []}), "better-way": json.dumps({"verdict": "HOLD", "claims": 3}),
               "kill-criteria": ""}
        rc, rec, _ = council(bad)
        self.assertEqual(rc, 3)
        rows = dict(rec["dropped"])
        self.assertIn("bad verdict", rows["skeptic"])
        self.assertIn("bad shape", rows["better-way"])
        self.assertIn("no JSON object", rows["kill-criteria"])

    def test_record_still_validates(self):
        _, rec, out = council({"skeptic": OK, "better-way": None, "kill-criteria": None})
        f = Path(tempfile.mkdtemp()) / "rec.json"
        f.write_text(out)
        r = subprocess.run([sys.executable, str(SK / "validate_verdict.py"), "--file", str(f)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(rec["dropped"]), 2)


if __name__ == "__main__":
    unittest.main()
