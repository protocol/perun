#!/usr/bin/env python3
"""veche.py input handling: --option names must be short tokens (#2136) and seat replies are read tolerantly,
braces in surrounding prose or scores as a second JSON object included (#2137). Stdlib only."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path

SK = Path(__file__).resolve().parent.parent / ".claude/skills/idea-critic/scripts"
LENSES = ("skeptic", "better-way", "kill-criteria")
FAKE = '''import sys, json
cfg = json.load(open(sys.argv[1])); p = sys.stdin.read()
open(cfg["log"], "a").write("call\\n")
if "STAGE: TWIN" in p:
    print(cfg.get("twin", "")); sys.exit()
for lens, out in cfg["answers"].items():
    if "LENS: " + lens + " " in p: print(out)
'''
CRIT = ["--criteria", "impact:3,cost:1"]


def scores(*names):
    return {o: {"impact": 3 if o == "ship" else 1, "cost": 1} for o in ("do-nothing", *names)}


def reply(scores_=None, **kw):
    d = {"verdict": "REVISE", "claims": [], "would_change_it": "w", "kill_criterion": "M below 5 by day 30"}
    if scores_ is not None:
        d["scores"] = scores_
    d.update(kw)
    return json.dumps(d)


def council(answer, extra=(), **cfg):
    """Every seat gives `answer` verbatim; -> (exit code, record, number of cmd calls)."""
    d = Path(tempfile.mkdtemp())
    (d / "fake.py").write_text(FAKE)
    (d / "cfg.json").write_text(json.dumps({"answers": {l: answer for l in LENSES}, "log": str(d / "log"), **cfg}))
    r = subprocess.run([sys.executable, str(SK / "veche.py"), "--cmd", f"{sys.executable} {d / 'fake.py'} {d / 'cfg.json'}",
                        "--claim", "c", "--steelman", "s", "--root", str(d), "--review-date", "2030-01-31", *extra],
                       capture_output=True, text=True)
    log = d / "log"
    return r.returncode, json.loads(r.stdout), len(log.read_text().splitlines()) if log.exists() else 0


class Options(unittest.TestCase):
    """#2136: option names are echoed back as JSON keys by every seat, so only short tokens are accepted."""

    def test_odd_names_fail_closed_before_any_call(self):
        for bad in ("ship it now", "ship;wait", 'say "go"', "ship,wait", "a" * 33, "ship\nwait"):
            rc, rec, calls = council(reply(scores("ship")), ["--option", bad, *CRIT])
            self.assertEqual((rc, rec["verdict"], calls), (3, "COULD_NOT_DECIDE", 0), repr(bad))
            self.assertIn("--option", rec["reason"])
            self.assertIn("short token", rec["reason"])

    def test_short_tokens_are_accepted(self):
        for good in ("ship", "ship-v2", "plan_b", "A1", "a" * 32):
            rc, rec, calls = council(reply(scores(good)), ["--option", good, *CRIT])
            self.assertEqual((rc, rec["verdict"], calls), (0, "REVISE", 3), good)
            self.assertEqual(rec["options"], ["do-nothing", good])


class TolerantReply(unittest.TestCase):
    """#2137: a seat's reply may carry prose with braces around its JSON, or put the scores in a second object."""

    def test_braces_in_surrounding_prose(self):
        for wrap in ("My answer {as asked}:\n%s", "%s\nHope that helps :{", "{note}\n%s\n{tail}", "```json\n%s\n```"):
            rc, rec, _ = council(wrap % reply())
            self.assertEqual((rc, rec["verdict"], rec["dropped"]), (0, "REVISE", []), wrap)

    def test_scores_as_a_second_json_object(self):
        for second in (json.dumps({"scores": scores("ship")}), json.dumps(scores("ship"))):
            rc, rec, _ = council(reply() + "\n" + second, ["--option", "ship", *CRIT])
            self.assertEqual((rc, rec["verdict"], rec["dropped"]), (0, "REVISE", []), second)
            self.assertEqual(rec["decision"], "ship")

    def test_scores_object_first_then_the_verdict(self):
        rc, rec, _ = council(json.dumps({"scores": scores("ship")}) + "\nfinal: " + reply(), ["--option", "ship", *CRIT])
        self.assertEqual((rc, rec["decision"]), (0, "ship"))

    def test_an_object_without_a_verdict_is_still_rejected(self):
        rc, rec, _ = council('{"note": "no verdict here"} {"also": 1}')
        self.assertEqual((rc, rec["verdict"]), (3, "COULD_NOT_DECIDE"))
        self.assertTrue(all("bad verdict" in r for _, r in rec["dropped"]))

    def test_twin_reply_with_braces_in_prose(self):
        twin = "Sure {here it is}: " + json.dumps({"dissent": "ship fails under load", "kill_criterion": "p95 above 2s by day 30"}) + " {end}"
        rc, rec, _ = council(reply(), ["--twin"], twin=twin)
        self.assertEqual(rc, 0)
        self.assertEqual(rec["minority_report"]["twin"]["dissent"], "ship fails under load")
        self.assertNotIn("evil-twin", [r[0] for r in rec["dropped"]])


if __name__ == "__main__":
    unittest.main()
