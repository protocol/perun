#!/usr/bin/env python3
"""Tests for Veche (idea-critic decision council, scripts/veche.py) using a fake cmd with canned answers. Stdlib only.

Covers the council practices: independent first round, decorrelated seats, criteria fixed before scoring,
deterministic aggregate with a chair tie-break, the evil twin and minority report, the closing record
(decision, kill criteria, leading metric, review date) and the convene-only-when-high-stakes gate.
"""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SK = ROOT / ".claude/skills/idea-critic/scripts"
SEATS = ("cpo", "cto", "cfo", "ciso", "user-advocate")
FAKE = '''import sys, json
cfg = json.load(open(sys.argv[1])); p = sys.stdin.read()
open(cfg["log"], "a").write(json.dumps(p) + "\\n")
if "STAGE: TWIN" in p:
    print(cfg.get("twin", "")); sys.exit()
if "STAGE: CRITIQUE" in p:
    print(cfg.get("critique", "{}")); sys.exit()
for lens, out in cfg["answers"].items():
    if "LENS: " + lens + " " in p: print(out); sys.exit()
'''
OPTS = ["--option", "ship", "--option", "wait", "--criteria", "impact:3,cost:1"]


def ans(v="REVISE", scores=None, **kw):
    d = {"verdict": v, "claims": [{"text": "c", "evidence": "README.md:1", "quote": "one"}], "would_change_it": "w",
         "premortem": "it failed because X", "kill_criterion": "metric M below 5 by day 30", "leading_metric": "weekly M"}
    if scores is not None:
        d["scores"] = scores
    d.update(kw)
    return json.dumps(d)


def sc(ship, wait, nothing=(0, 0)):
    """scores for the three options as (impact, cost) pairs"""
    return {o: {"impact": i, "cost": c} for o, (i, c) in (("do-nothing", nothing), ("ship", ship), ("wait", wait))}


class T(unittest.TestCase):
    def run_veche(self, answers, extra=(), script="veche.py", **cfg):
        d = Path(tempfile.mkdtemp())
        (d / "README.md").write_text("one\ntwo\n")
        (d / "fake.py").write_text(FAKE)
        (d / "cfg.json").write_text(json.dumps({"answers": answers, "log": str(d / "log"), **cfg}))
        args = ["--cmd", f"{sys.executable} {d/'fake.py'} {d/'cfg.json'}", "--claim", "do X", "--steelman", "X helps",
                "--root", str(d), "--review-date", "2030-01-31", *extra]
        r = subprocess.run([sys.executable, str(SK / script)] + args, capture_output=True, text=True)
        calls = [json.loads(x) for x in (d / "log").read_text().splitlines()] if (d / "log").exists() else []
        return r.returncode, json.loads(r.stdout), calls, d

    def valid(self, rec, d):
        f = d / "rec.json"
        f.write_text(json.dumps(rec))
        return subprocess.run([sys.executable, str(SK / "validate_verdict.py"), "--file", str(f)], capture_output=True).returncode

    def seats(self, *outs):
        return dict(zip(SEATS, outs))

    def test_council_shim_forwards_to_veche(self):
        answers = {l: ans() for l in ("skeptic", "better-way", "kill-criteria")}
        a = self.run_veche(answers, script="council.py")
        b = self.run_veche(answers, script="veche.py")
        self.assertEqual((a[0], a[1]["verdict"], len(a[2])), (b[0], b[1]["verdict"], len(b[2])))
        self.assertEqual((a[0], a[1]["verdict"]), (0, "REVISE"))
        rc, rec, calls, _ = self.run_veche(answers, ["--stakes", "low", "--reversibility", "easy"], script="council.py")
        self.assertEqual((rc, rec["verdict"], len(calls)), (4, "NOT_CONVENED", 0))  # exit codes pass through the shim
        rc, rec, _, _ = self.run_veche(answers, ["--max-calls", "1"], script="council.py")
        self.assertEqual((rc, rec["verdict"]), (3, "COULD_NOT_DECIDE"))

    def test_import_council_neither_exits_nor_runs_and_exposes_veche_names(self):
        code = ("import sys; sys.argv = ['x']; sys.path.insert(0, %r); import council; "
                "assert callable(council.run) and callable(council.cite_state) and callable(council.parse) "
                "and callable(council.fence) and callable(council.main); print('imported')" % str(SK))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip(), r.stderr), (0, "imported", ""))

    def test_seats_are_independent_and_decorrelated(self):
        rc, rec, calls, d = self.run_veche(self.seats(*[ans()] * 5), ["--lenses", ",".join(SEATS)])
        self.assertEqual((rc, len(calls), rec["lenses"]), (0, 5, list(SEATS)))
        for s in SEATS:  # first-round calls run in parallel, so their log order is not fixed
            self.assertEqual(sum(f"LENS: {s} " in p for p in calls), 1)  # each seat gets its own lens
        for p in calls:
            self.assertNotIn("ANSWER ", p)  # and never another seat's answer before its own is written
            self.assertNotIn("it failed because X", p)
        self.assertEqual(self.valid(rec, d), 0)

    def test_criteria_fixed_before_scoring_and_aggregate_is_deterministic(self):
        # weights impact .75 / cost .25 (from 3:1); member-reported weights must be ignored
        a = ans(scores=sc((5, 1), (2, 5)), weights={"impact": 0})  # ship 4.0, wait 2.75
        b = ans(scores=sc((4, 1), (2, 5)))  # ship 3.25, wait 2.75
        rc, rec, calls, d = self.run_veche(self.seats(a, b, a), ["--lenses", "cpo,cto,cfo", *OPTS])
        self.assertEqual(rec["decision"], "ship")
        self.assertAlmostEqual(rec["scores"]["ship"], 0.75 * (14 / 3) + 0.25 * 1, places=6)
        self.assertEqual(rec["criteria"], {"impact": 0.75, "cost": 0.25})
        for p in calls:  # every seat saw the same fixed criteria and the options, including do-nothing
            self.assertIn("impact (0.750); cost (0.250)", p)
            self.assertIn("OPTIONS: do-nothing; ship; wait", p)
        self.assertEqual(self.valid(rec, d), 0)

    def test_tie_goes_to_chair_else_do_nothing_first(self):
        tie = sc((3, 3), (3, 3), (3, 3))  # every option scores the same for this seat
        cpo = ans(scores=sc((4, 4), (3, 3), (0, 0)))
        cto = ans(scores=sc((2, 2), (3, 3), (4, 4)))  # means tie ship=3, wait=3, do-nothing=2
        rc, rec, _, _ = self.run_veche(self.seats(cpo, cto), ["--lenses", "cpo,cto", *OPTS, "--chair", "cpo"])
        self.assertEqual((rec["scores"]["ship"], rec["scores"]["wait"]), (rec["scores"]["wait"], rec["scores"]["wait"]))
        self.assertEqual(rec["decision"], "ship")  # chair cpo scores ship above wait
        rc, rec, _, _ = self.run_veche(self.seats(cpo, cto), ["--lenses", "cpo,cto", *OPTS, "--chair", "cto"])
        self.assertEqual(rec["decision"], "wait")  # chair cto prefers wait among the tied
        rc, rec, _, _ = self.run_veche(self.seats(ans(scores=tie), ans(scores=tie)), ["--lenses", "cpo,cto", *OPTS])
        self.assertEqual(rec["decision"], "do-nothing")  # no chair: the cautious option wins a dead heat

    def test_chair_breaks_a_verdict_tie_else_most_cautious(self):
        answers = self.seats(ans("PASS_TO_USER"), ans("HOLD"))
        _, rec, _, _ = self.run_veche(answers, ["--lenses", "cpo,cto", "--chair", "cpo"])
        self.assertEqual(rec["verdict"], "PASS_TO_USER")
        _, rec, _, _ = self.run_veche(answers, ["--lenses", "cpo,cto"])
        self.assertEqual(rec["verdict"], "HOLD")

    def test_do_nothing_decision_downgrades_pass(self):
        s = ans("PASS_TO_USER", scores=sc((1, 1), (1, 1), (5, 5)))
        _, rec, _, _ = self.run_veche(self.seats(s, s), ["--lenses", "cpo,cto", *OPTS])
        self.assertEqual((rec["decision"], rec["verdict"]), ("do-nothing", "REVISE"))

    def test_bad_scores_drop_the_seat(self):
        good = ans(scores=sc((5, 5), (1, 1)))
        for bad in (ans(), ans(scores=sc((9, 1), (1, 1))), ans(scores={"ship": {"impact": 1}})):
            rc, rec, _, _ = self.run_veche(self.seats(good, good, bad), ["--lenses", "cpo,cto,cfo", *OPTS])
            self.assertEqual((rc, rec["dropped"][0][0]), (0, "cfo"))

    def test_options_and_criteria_must_go_together_and_be_sane(self):
        for extra in (["--criteria", "a:1"], ["--option", "x"], [*OPTS[:-1], "a:0"], [*OPTS[:-1], "a:1,a:2"], [*OPTS[:-1], "a:x"]):
            rc, rec, calls, _ = self.run_veche(self.seats(ans()), extra)
            self.assertEqual((rc, rec["verdict"], len(calls)), (3, "COULD_NOT_DECIDE", 0), extra)

    def test_twin_dissent_premortem_and_minority_report(self):
        twin = json.dumps({"dissent": "ship fails when load doubles", "kill_criterion": "p95 above 2s for 7 days",
                           "claims": [{"text": "t", "evidence": "README.md:2", "quote": "two"}]})
        s = ans(scores=sc((5, 1), (1, 1)))
        rc, rec, calls, d = self.run_veche(self.seats(s, s, ans(scores=sc((5, 1), (1, 1)), kill_criterion="metric M below 5 by day 30")),
                                          ["--lenses", "cpo,cto,cfo", *OPTS, "--twin"], twin=twin)
        self.assertEqual(len(calls), 4)
        self.assertIn("DECISION: ship", calls[3])
        self.assertIn("LENS: evil-twin", calls[3])
        self.assertNotIn("ANSWER ", calls[3])
        mr = rec["minority_report"]["twin"]
        self.assertEqual((mr["dissent"], mr["claims"][0]["state"]), ("ship fails when load doubles", "verified"))
        self.assertEqual(rec["kill_criteria"], ["metric M below 5 by day 30", "p95 above 2s for 7 days"])
        self.assertEqual(rec["premortems"][0], {"lens": "cpo", "text": "it failed because X"})
        self.assertEqual(self.valid(rec, d), 0)

    def test_unparseable_twin_is_dropped_not_fatal(self):
        s = ans(scores=sc((5, 1), (1, 1)))
        rc, rec, _, _ = self.run_veche(self.seats(s, s), ["--lenses", "cpo,cto", *OPTS, "--twin"], twin="not json")
        self.assertEqual((rc, rec["minority_report"]["twin"], rec["dropped"][-1][0]), (0, None, "evil-twin"))

    def test_record_closes_with_decision_kill_metric_review_date(self):
        s = ans(scores=sc((5, 1), (1, 1)))
        rc, rec, _, d = self.run_veche(self.seats(s, s), ["--lenses", "cpo,cto", *OPTS, "--chair", "cto"])
        self.assertEqual((rec["decision"], rec["leading_metric"], rec["review_date"]), ("ship", "weekly M", "2030-01-31"))
        self.assertEqual(rec["kill_criteria"], ["metric M below 5 by day 30"])
        self.assertEqual(self.valid(rec, d), 0)
        for k in ("review_date", "kill_criteria", "leading_metric"):  # the validator rejects a decision missing a closer
            bad = {x: y for x, y in rec.items() if x != k}
            self.assertEqual(self.valid(bad, d), 1, k)

    def test_missing_closers_are_marked_unverified_not_invented(self):
        bare = json.dumps({"verdict": "REVISE", "claims": [], "would_change_it": "w"})
        rc, rec, _, _ = self.run_veche(self.seats(bare, bare), ["--lenses", "cpo,cto"])
        self.assertTrue(rec["kill_criteria"][0].startswith("UNVERIFIED"))
        self.assertTrue(rec["leading_metric"].startswith("UNVERIFIED"))

    def test_convene_only_for_high_stakes_or_hard_reversibility(self):
        a = self.seats(ans(), ans())
        for extra, convened in ((["--stakes", "low", "--reversibility", "easy"], False), (["--stakes", "medium", "--reversibility", "easy"], False),
                                (["--stakes", "high", "--reversibility", "easy"], True), (["--stakes", "low", "--reversibility", "hard"], True),
                                (["--stakes", "low"], True), ([], True)):
            rc, rec, calls, d = self.run_veche(a, ["--lenses", "cpo,cto", *extra])
            self.assertEqual(rec["verdict"] != "NOT_CONVENED", convened, extra)
            self.assertEqual((rc, len(calls)), (0, 2) if convened else (4, 0), extra)
            self.assertEqual(self.valid(rec, d), 0, extra)

    def test_lens_names_cannot_escape_the_lens_dir(self):
        for bad in ("cpo,../../README", "cpo,/etc/passwd", "cpo", "cpo,cpo"):
            rc, rec, calls, _ = self.run_veche({}, ["--lenses", bad])
            self.assertEqual((rc, len(calls)), (3, 0), bad)

    def test_hat_verdict_closers_are_optional_but_never_empty(self):
        v = {"verdict": "PASS_TO_USER", "independence": "inline", "origin": "agent-originated", "claim": "c", "steelman": "s",
             "hats_run": "skeptic, better-way, kill-criteria", "assumptions": "NONE", "better_ways": "NONE", "kill_criteria": "NONE",
             "strongest_attack_survived": "load doubling; the rollback covers it", "questions_parent_must_resolve": "NONE",
             "user_question": "NONE", "dissent_ledger": "none", "remaining_risk": "low"}
        d = Path(tempfile.mkdtemp())
        self.assertEqual(self.valid(v, d), 0)
        self.assertEqual(self.valid({**v, "decision": "go-if the canary holds", "leading_metric": "p95 latency, review 2030-01-31"}, d), 0)
        for k in ("decision", "leading_metric"):
            for bad in ("", "  ", None, ["x"]):
                self.assertEqual(self.valid({**v, k: bad}, d), 1, (k, bad))

    def test_dry_run_counts_the_twin(self):
        rc, rec, calls, _ = self.run_veche({}, ["--lenses", "cpo,cto,cfo", "--twin", "--dry-run"])
        self.assertEqual((rc, rec["verdict"], rec["planned_calls"], len(calls)), (0, "DRY_RUN", 4, 0))


if __name__ == "__main__":
    unittest.main()
