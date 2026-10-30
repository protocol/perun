#!/usr/bin/env python3
"""The veche.py decision record explains itself (#2140): why the verdict differs from the tally top,
each dissenting answer appears once, near-duplicate kill criteria collapse. Stdlib only."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

SK = Path(__file__).resolve().parent.parent / ".claude/skills/idea-critic/scripts"
LENSES = ("skeptic", "better-way", "kill-criteria")
FAKE = '''import sys, json
cfg = json.load(open(sys.argv[1])); p = sys.stdin.read()
if "STAGE: CRITIQUE" in p: print("{}"); sys.exit()
for lens, out in cfg.items():
    if "LENS: " + lens + " " in p: print(out)
'''


def reply(v, kill="M below 5 by day 30", text="c", scores=None):
    d = {"verdict": v, "claims": [{"text": text, "evidence": "README.md:1", "quote": "one"}], "would_change_it": "w", "kill_criterion": kill}
    if scores:
        d["scores"] = scores
    return json.dumps(d)


def council(answers, *extra):
    """answers: one raw reply per lens, in LENSES order; -> (exit code, record)."""
    d = Path(tempfile.mkdtemp())
    (d / "README.md").write_text("one\ntwo\n")
    (d / "fake.py").write_text(FAKE)
    (d / "cfg.json").write_text(json.dumps(dict(zip(LENSES, answers))))
    r = subprocess.run([sys.executable, str(SK / "veche.py"), "--cmd", f"{sys.executable} {d / 'fake.py'} {d / 'cfg.json'}",
                        "--claim", "c", "--steelman", "s", "--root", str(d), "--review-date", "2030-01-31", *extra],
                       capture_output=True, text=True)
    return r.returncode, json.loads(r.stdout)


class VerdictBasis(unittest.TestCase):
    def test_majority_and_unanimity_are_stated(self):
        _, rec = council([reply("REVISE"), reply("REVISE"), reply("HOLD")])
        self.assertEqual(rec["verdict"], "REVISE")
        self.assertIn("2 of 3", rec["verdict_basis"])
        _, rec = council([reply("HOLD")] * 3)
        self.assertIn("3 of 3", rec["verdict_basis"])

    def test_tie_is_explained_as_the_cautious_pick_or_the_chair(self):
        votes = [reply("HOLD"), reply("REVISE"), reply("PASS_TO_USER")]
        _, rec = council(votes)
        self.assertEqual((rec["verdict"], rec["tally"]), ("HOLD", {"HOLD": 1, "REVISE": 1, "PASS_TO_USER": 1}))
        self.assertIn("tie", rec["verdict_basis"])
        self.assertIn("cautious", rec["verdict_basis"])
        _, rec = council(votes, "--chair", "better-way")
        self.assertEqual(rec["verdict"], "REVISE")
        self.assertIn("tie", rec["verdict_basis"])
        self.assertIn("chair better-way", rec["verdict_basis"])

    def test_owner_request_hold_is_explained(self):
        _, rec = council([reply("HOLD")] * 3, "--origin", "owner-request")
        self.assertEqual(rec["verdict"], "REVISE")
        self.assertIn("owner-request", rec["verdict_basis"])
        self.assertIn("HOLD", rec["verdict_basis"])

    def test_do_nothing_downgrade_is_explained(self):
        sc = {"do-nothing": {"impact": 5, "cost": 5}, "ship": {"impact": 1, "cost": 1}}
        _, rec = council([reply("PASS_TO_USER", scores=sc)] * 3, "--option", "ship", "--criteria", "impact:3,cost:1")
        self.assertEqual((rec["decision"], rec["verdict"]), ("do-nothing", "REVISE"))
        self.assertIn("do-nothing", rec["verdict_basis"])
        self.assertIn("PASS_TO_USER", rec["verdict_basis"])


class Duplicates(unittest.TestCase):
    def test_a_dissenting_answer_appears_once_in_the_record(self):
        mark = "UNIQUE-DISSENT-MARK"
        rc, rec = council([reply("REVISE"), reply("REVISE"), reply("HOLD", text=mark)])
        self.assertEqual(rc, 0)
        self.assertEqual(len(rec["dissent"]), 1)
        self.assertIn(mark, rec["dissent"][0])  # `dissent` keeps the verbatim answers (the validator requires the key)
        self.assertEqual(rec["minority_report"]["dissenting_seats"], ["kill-criteria"])  # the other view only names the seats
        self.assertEqual(json.dumps(rec).count(mark), 1)

    def test_no_dissent_means_no_dissenting_seats(self):
        _, rec = council([reply("REVISE")] * 3)
        self.assertEqual((rec["dissent"], rec["minority_report"]["dissenting_seats"]), ([], []))

    def test_near_duplicate_kill_criteria_collapse_but_different_numbers_stay(self):
        kills = ["Churn above 5% by 2030-01-31.", "churn  above 5% by 2030-01-31", "Churn above 6% by 2030-01-31"]
        _, rec = council([reply("REVISE", kill=k) for k in kills])
        self.assertEqual(rec["kill_criteria"], [kills[0], kills[2]])  # first wording kept, order kept, 5% vs 6% not merged

    def test_exact_duplicates_still_collapse_and_none_is_unverified(self):
        _, rec = council([reply("REVISE")] * 3)
        self.assertEqual(rec["kill_criteria"], ["M below 5 by day 30"])
        _, rec = council([reply("REVISE", kill="")] * 3)
        self.assertEqual(len(rec["kill_criteria"]), 1)
        self.assertTrue(rec["kill_criteria"][0].startswith("UNVERIFIED"))


if __name__ == "__main__":
    unittest.main()
