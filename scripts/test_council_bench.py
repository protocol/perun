#!/usr/bin/env python3
"""Tests for scripts/council_bench.py: stub seats and a stub judge (no network, no model), the real veche.py run as a subprocess. Stdlib only.

A six-case synthetic corpus gives each case a council verdict through a marker word in its proposal. The tests pin the harness (scoring, key isolation,
resume, replay, spend cap, twin and judge wiring) and, through the real veche.py, the record fields the harness reads.
"""
import contextlib, io, json, shutil, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import council_bench as C

CORPUS = """=== a1 | flawed
PROPOSAL: Acme pilot one, marker HOLDME. Quote this line.
KEY: SECRET-a1 survivorship bias.
=== a2 | flawed
PROPOSAL: Acme pilot two, marker REVISEME. Quote this line.
KEY: SECRET-a2 no control group.
=== a3 | flawed
PROPOSAL: Acme pilot three, marker PASSME. Quote this line.
KEY: SECRET-a3 double counted savings.
=== c1 | control
PROPOSAL: Acme sound plan one, marker HOLDME. Quote this line.
KEY: none, SECRET-c1 minor issues only.
=== c2 | control
PROPOSAL: Acme sound plan two, marker PASSME. Quote this line.
KEY: none, SECRET-c2 minor issues only.
=== c3 | control
PROPOSAL: Acme sound plan three, marker BROKENME. Quote this line.
KEY: none, SECRET-c3 minor issues only.
"""
SEAT = '''import json, os, sys
cfg = json.load(open(sys.argv[1])); p = sys.stdin.read()
open(cfg["log"], "a").write(json.dumps(p) + "\\n")
open(cfg["log"] + ".cwd", "a").write(json.dumps(sorted(os.listdir("."))) + "\\n")
if "STAGE: TWIN" in p:
    print(json.dumps({"dissent": "TWINMARK it fails in week one", "kill_criterion": "metric M below 5 by day 30", "claims": []})); sys.exit()
if "BROKENME" in p:
    print("no json here"); sys.exit()
v = next(x for w, x in (("HOLDME", "HOLD"), ("REVISEME", "REVISE"), ("PASSME", "PASS_TO_USER")) if w in p)
print(json.dumps({"verdict": v, "claims": [{"text": "c", "evidence": "proposal.txt:1", "quote": "Quote this line"}], "would_change_it": "w",
                  "premortem": "PREMORTEM it failed because X", "kill_criterion": "metric M below 5 by day 30", "leading_metric": "weekly M"}))
'''
JUDGE = '''import json, sys
cfg = json.load(open(sys.argv[1])); p = sys.stdin.read()
open(cfg["log"], "a").write(json.dumps(p) + "\\n")
if cfg.get("fail"):
    sys.exit(3)
if cfg.get("garbage"):
    print("I refuse to grade"); sys.exit()
caught, killed = int("COUNCIL VERDICT: PASS_TO_USER" not in p), int("COUNCIL VERDICT: HOLD" in p)
print(f"REASON: stub\\nFLAW_CAUGHT: {caught}\\nKILLED: {killed}\\nBLOCKED: {caught}")
'''


def bench(argv):
    """Run C.main with its report muted -> the results dict."""
    with contextlib.redirect_stdout(io.StringIO()):
        return C.main(argv)


def lines(f):
    return [json.loads(x) for x in Path(f).read_text().splitlines()] if Path(f).exists() else []


class Bench(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        C.BOOT = 200
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.d = Path(tmp.name)
        cls.cases = str(cls.d / "cases.txt")
        (cls.d / "cases.txt").write_text(CORPUS)
        (cls.d / "seat.py").write_text(SEAT)
        (cls.d / "judge.py").write_text(JUDGE)
        cls.seat, cls.judge = cls.stub("seat"), cls.stub("judge")
        cls.recs = cls.d / "recs"
        cls.res = bench(cls.argv(cls.recs, "--judge", cls.judge))

    @classmethod
    def stub(cls, kind, tag="", **cfg):
        """A command template running the stub `kind` with its own log (<kind><tag>.log) and config -> the template."""
        (cls.d / f"{kind}{tag}.json").write_text(json.dumps({"log": str(cls.d / f"{kind}{tag}.log"), **cfg}))
        return f"{sys.executable} {cls.d / (kind + '.py')} {cls.d / (kind + tag + '.json')}"

    @classmethod
    def argv(cls, recs, *more, cmd=True):
        return ["--cases", cls.cases, "--records", str(recs), *(["--cmd", cls.seat, "--cap-calls", "100", "--max-calls", "3"] if cmd else []), *more]

    def rate(self, res, name):
        return res["stats"][name]["rate"]

    def test_default_corpus_is_the_r2_cases(self):
        cs = C.load_cases(C.CASES)
        self.assertEqual((len(cs), sum(c["kind"] == "flawed" for c in cs)), (36, 24))

    def test_bad_corpus_is_refused(self):
        for text in (CORPUS.replace("a1 |", "../a1 |"), CORPUS.split("=== c1")[0]):  # an id that names a path; no control case
            f = self.d / "bad.txt"
            f.write_text(text)
            with self.assertRaises(ValueError):
                C.load_cases(f)

    def test_verdict_scores_and_undecided(self):
        r = self.res
        self.assertEqual((r["n"], r["flawed"], r["control"], r["undecided"], r["calls"]), (6, 3, 3, ["c3"], 18))
        for name, want in (("flawed_blocked", 2 / 3), ("flawed_held", 1 / 3), ("control_blocked", 1 / 3), ("control_held", 1 / 3)):
            self.assertAlmostEqual(self.rate(r, name), want)
            lo, hi = r["stats"][name]["ci"]
            self.assertLessEqual(lo, hi)

    def test_judge_scores_use_the_r2_rubric_and_skip_undecided(self):
        self.assertAlmostEqual(self.rate(self.res, "recall"), 2 / 3)
        self.assertAlmostEqual(self.rate(self.res, "false_kill"), 1 / 3)
        self.assertEqual(self.res["unparsed"], 0)
        self.assertEqual(len(lines(self.d / "judge.log")), 5)  # the council that could not decide is not judged

    def test_key_reaches_the_judge_and_never_a_seat(self):
        seat = lines(self.d / "seat.log")
        self.assertEqual(len(seat), 18)
        self.assertFalse(any("SECRET" in p for p in seat))
        self.assertTrue(all("Quote this line" in p for p in seat))  # the proposal is the packet
        for p in lines(self.d / "judge.log"):
            self.assertTrue(p.startswith(C.E.JUDGE_SYSTEM) and "SECRET-" in p and "COUNCIL VERDICT:" in p and "PREMORTEM it failed" in p)

    def test_seats_run_in_the_packet_dir_and_see_only_the_proposal(self):
        cwds = lines(self.d / "seat.log.cwd")
        self.assertEqual(len(cwds), 18)
        self.assertTrue(all(c == ["proposal.txt"] for c in cwds))  # a seat that starts in the repo root can read the answer keys with file tools

    def test_packet_citations_verify_under_the_temp_root(self):
        rec = json.loads((self.recs / "a1.json").read_text())
        self.assertEqual((rec["verdict"], rec["unsupported_claims"], rec["cited_unverified"], rec["cost"]["calls"]), ("HOLD", [], [], 3))
        self.assertEqual(json.loads((self.recs / "c3.json").read_text())["verdict"], "COULD_NOT_DECIDE")

    def test_replay_is_offline_and_identical(self):
        before = (len(lines(self.d / "seat.log")), len(lines(self.d / "judge.log")))
        again = bench(self.argv(self.recs, "--judge", "saved", cmd=False))
        self.assertEqual(again, self.res)
        self.assertEqual((len(lines(self.d / "seat.log")), len(lines(self.d / "judge.log"))), before)

    def test_without_a_judge_only_verdict_scores(self):
        r = bench(self.argv(self.recs, cmd=False))
        self.assertEqual(sorted(r["stats"]), ["control_blocked", "control_held", "flawed_blocked", "flawed_held"])
        self.assertNotIn("unparsed", r)

    def test_missing_record_and_missing_judge_output_fail_closed(self):
        with self.assertRaises(SystemExit) as cm:
            bench(self.argv(self.d / "empty", cmd=False))
        self.assertIn("missing record", str(cm.exception.code))
        part = self.d / "nojudge"
        shutil.copytree(self.recs, part, ignore=shutil.ignore_patterns("*.judge.txt"))
        with self.assertRaises(SystemExit) as cm:
            bench(self.argv(part, "--judge", "saved", cmd=False))
        self.assertIn("missing judge output", str(cm.exception.code))

    def test_bad_record_fails_closed(self):
        bad = self.d / "bad"
        bad.mkdir()
        (bad / "a1.json").write_text('{"verdict": "HOLD"}')  # no cost
        with self.assertRaises(SystemExit) as cm:
            bench(self.argv(bad, cmd=False))
        self.assertIn("bad record", str(cm.exception.code))

    def test_live_run_needs_a_cap_and_stops_at_it(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            C.main(["--cases", self.cases, "--records", str(self.d / "nocap"), "--cmd", self.seat])
        self.assertEqual(cm.exception.code, 2)  # argparse error
        seat = self.stub("seat", "cap")
        recs = self.d / "capped"
        with self.assertRaises(SystemExit) as cm:  # one council reserves 3 of 4 calls; a second would pass the cap
            bench(["--cases", self.cases, "--records", str(recs), "--cmd", seat, "--cap-calls", "4", "--max-calls", "3", "--jobs", "1"])
        self.assertIn("cap reached", str(cm.exception.code))
        self.assertEqual((sorted(p.name for p in recs.iterdir()), len(lines(self.d / "seatcap.log"))), (["a1.json"], 3))

    def test_council_that_ends_early_refunds_its_reservation(self):
        seat = self.stub("seat", "refund")
        r = bench(["--cases", self.cases, "--records", str(self.d / "refund"), "--cmd", seat, "--cap-calls", "20", "--max-calls", "5", "--jobs", "1"])
        self.assertEqual((r["n"], r["calls"]), (6, 18))  # each reserves 5 and uses 3: without the refund the fifth would pass the cap

    def test_live_judge_needs_a_cap(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            C.main(["--cases", self.cases, "--records", str(self.recs), "--judge", self.judge])
        self.assertEqual(cm.exception.code, 2)  # argparse error: a judge command spends calls like a seat does

    def test_judge_calls_count_against_the_cap(self):
        recs, judge = self.d / "judgecap", self.stub("judge", "cap")
        shutil.copytree(self.recs, recs, ignore=shutil.ignore_patterns("*.judge.txt"))
        with self.assertRaises(SystemExit) as cm:  # five decided councils need five judge calls; the cap allows two
            bench(self.argv(recs, "--judge", judge, "--cap-calls", "2", "--jobs", "1", cmd=False))
        self.assertIn("cap reached", str(cm.exception.code))
        self.assertEqual((len(lines(self.d / "judgecap.log")), len(list(recs.glob("*.judge.txt")))), (2, 2))

    def test_failing_judge_stops_the_run_and_saves_nothing(self):
        recs = self.d / "judgefail"
        shutil.copytree(self.recs, recs, ignore=shutil.ignore_patterns("*.judge.txt"))
        with self.assertRaises(SystemExit) as cm:
            bench(self.argv(recs, "--judge", self.stub("judge", "fail", fail=True), "--cap-calls", "10", "--jobs", "1", cmd=False))
        self.assertIn("judge exit 3", str(cm.exception.code))
        self.assertEqual(list(recs.glob("*.judge.txt")), [])  # an empty answer saved from a failed call would poison every replay

    def test_resume_convenes_only_the_missing_cases(self):
        seat = self.stub("seat", "resume")
        recs = self.d / "resume"
        shutil.copytree(self.recs, recs, ignore=shutil.ignore_patterns("c1.json", "c1.judge.txt"))
        r = bench(["--cases", self.cases, "--records", str(recs), "--cmd", seat, "--cap-calls", "10", "--max-calls", "3"])
        self.assertEqual((len(lines(self.d / "seatresume.log")), (recs / "c1.json").exists(), r["calls"]), (3, True, 18))

    def test_twin_flag_reaches_veche_and_the_judge(self):
        seat, judge = self.stub("seat", "twin"), self.stub("judge", "twin")
        r = bench(["--cases", self.cases, "--records", str(self.d / "twin"), "--cmd", seat, "--veche=--twin", "--cap-calls", "100",
                   "--max-calls", "4", "--judge", judge])
        self.assertEqual(r["calls"], 5 * 4 + 3)  # three seats and the twin per decided council; the broken one stops after its seats
        for p in lines(self.d / "judgetwin.log"):
            self.assertIn("Evil twin dissent: TWINMARK", p)

    def test_harness_flags_win_over_veche_flags(self):
        seat = self.stub("seat", "flags")
        r = bench(["--cases", self.cases, "--records", str(self.d / "flags"), "--cmd", seat, "--veche=--max-calls 1 --seed 5", "--cap-calls", "100", "--max-calls", "3"])
        self.assertEqual((r["calls"], r["undecided"]), (18, ["c3"]))  # a --max-calls 1 that won would starve every council

    def test_garbage_judge_output_counts_unparsed_as_zero(self):
        recs = self.d / "garbage"
        shutil.copytree(self.recs, recs, ignore=shutil.ignore_patterns("*.judge.txt"))
        r = bench(self.argv(recs, "--judge", self.stub("judge", "garbage", garbage=True), "--cap-calls", "10", cmd=False))
        self.assertEqual((r["unparsed"], self.rate(r, "recall"), self.rate(r, "false_kill")), (5, 0.0, 0.0))

    def test_render_holds_the_deliverable_and_the_gloss_is_skill_wording(self):
        text = C.render(json.loads((self.recs / "a1.json").read_text()))
        self.assertTrue(text.startswith("COUNCIL VERDICT: HOLD (do not recommend it)"))
        self.assertIn("Pre-mortem: PREMORTEM it failed because X", text)
        self.assertIn("Kill criterion: metric M below 5 by day 30", text)
        skill = (C.ROOT / ".claude/skills/idea-critic/SKILL.md").read_text()
        for v, g in C.GLOSS.items():
            self.assertIn(f"`{v}`: {g}", skill)


if __name__ == "__main__":
    unittest.main()
