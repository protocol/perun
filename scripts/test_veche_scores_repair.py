#!/usr/bin/env python3
"""Tests for veche.py scores normalization, the one repair re-ask, and the diagnosable dropped entry. Offline fake cmd."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VECHE = ROOT / ".claude/skills/idea-critic/scripts/veche.py"
FAKE = '''import sys, json
cfg = json.load(open(sys.argv[1])); p = sys.stdin.read()
open(cfg["log"], "a").write(json.dumps("REPAIR" if "STAGE: SCORES REPAIR" in p else "MAIN") + "\\n")
if "STAGE: SCORES REPAIR" in p:
    if "do X" in p and "ANSWER SELF" in p: open(cfg["log"], "a").write(json.dumps("CTX") + "\\n")
    print(cfg.get("repair", "")); sys.exit()
if "STAGE: TWIN" in p or "STAGE: CRITIQUE" in p:
    print("{}"); sys.exit()
for lens, out in cfg["answers"].items():
    if "LENS: " + lens + " " in p: print(out); sys.exit()
'''
GOOD = {o: {"impact": 3, "cost": 2} for o in ("do-nothing", "ship", "wait")}


def ans(scores):
    return json.dumps({"verdict": "REVISE", "claims": [{"text": "c", "evidence": "README.md:1", "quote": "one"}],
                       "would_change_it": "w", "premortem": "p", "kill_criterion": "k", "leading_metric": "m", "scores": scores})


class T(unittest.TestCase):
    def run_veche(self, bad, repair="", extra=()):
        d = Path(tempfile.mkdtemp())
        (d / "README.md").write_text("one\ntwo\n")
        (d / "fake.py").write_text(FAKE)
        # cpo and cto answer well; ciso answers `bad`
        (d / "cfg.json").write_text(json.dumps({"answers": {"cpo": ans(GOOD), "cto": ans(GOOD), "ciso": bad}, "repair": repair, "log": str(d / "log")}))
        r = subprocess.run([sys.executable, str(VECHE), "--cmd", f"{sys.executable} {d/'fake.py'} {d/'cfg.json'}", "--claim", "do X",
                            "--steelman", "X helps", "--root", str(d), "--review-date", "2030-01-31", "--option", "ship", "--option", "wait",
                            "--criteria", "impact:3,cost:1", "--lenses", "cpo,cto,ciso", *extra], capture_output=True, text=True)
        log = (d / "log").read_text().split() if (d / "log").exists() else []
        return r, log

    def dropped(self, r):
        return [x for x in json.loads(r.stdout).get("dropped", []) if "scores" in x[1]]

    def assert_normalized(self, scores):
        r, log = self.run_veche(ans(scores))
        self.assertEqual(self.dropped(r), [], r.stdout + r.stderr)
        self.assertNotIn('"REPAIR"', log)

    def test_case_and_punctuation_keys(self):
        self.assert_normalized({"Do Nothing": {"Impact": 3, "COST!": 2}, "SHIP": {"impact": 3, "cost": 2}, "wait.": {"impact": 3, "cost": 2}})

    def test_numeric_strings(self):
        self.assert_normalized({o: {"impact": "4", "cost": "4.5"} for o in GOOD})

    def test_transposed_matrix(self):
        self.assert_normalized({"impact": {o: 3 for o in GOOD}, "cost": {o: 2 for o in GOOD}})

    def test_out_of_range_still_fails(self):
        r, _ = self.run_veche(ans({o: {"impact": 9, "cost": 2} for o in GOOD}))
        self.assertEqual(len(self.dropped(r)), 1)

    def test_missing_cell_still_fails(self):
        r, _ = self.run_veche(ans({o: {"impact": 3} for o in GOOD}))
        self.assertEqual(len(self.dropped(r)), 1)

    def test_repair_success(self):
        r, log = self.run_veche(ans("garbage"), repair=json.dumps({"scores": GOOD}))
        self.assertEqual(self.dropped(r), [], r.stdout + r.stderr)
        self.assertEqual(log.count('"REPAIR"'), 1)
        self.assertIn('"CTX"', log)  # the repair call sees the question and its own earlier answer

    def test_repair_failure_keeps_excerpt(self):
        r, log = self.run_veche(ans("garbage" * 100), repair="nope")
        dr = self.dropped(r)
        self.assertEqual(len(dr), 1)
        self.assertIn("garbagegarbage", dr[0][1])
        self.assertLessEqual(len(dr[0][1]), 300 + 80)
        self.assertEqual(log.count('"REPAIR"'), 1)

    def test_cap_hit_during_repair_fails_closed(self):
        r, log = self.run_veche(ans("garbage"), repair=json.dumps({"scores": GOOD}), extra=("--max-calls", "3"))
        self.assertNotIn('"REPAIR"', log)
        dr = self.dropped(r)
        self.assertEqual(len(dr), 1)
        self.assertIn("cap reached", dr[0][1])


if __name__ == "__main__":
    unittest.main()
