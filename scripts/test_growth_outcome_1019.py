#!/usr/bin/env python3
"""Offline tests for docs/bench/growth-outcome-1019: the answer key, the deterministic parser and scorer, the readout validity check, the keep rule, the frozen hashes, and that the committed verdict follows from the committed scores.

No PCSS call is made. There is no model grader in this bench, so the parser and the scorer are what is validated, against hand-written answers in the shapes the arms produce.
"""
import hashlib, json, sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "docs/bench/growth-outcome-1019"
sys.path.insert(0, str(D))
import bench as b
import key as K


def test_key_is_balanced_and_consistent_with_its_anchors():
    key = json.loads((D / "key.json").read_text())
    assert key == K.make()  # key.json is exactly what key.py writes
    assert len(key) == 96 and len({k["id"] for k in key}) == 96
    assert [sum(len(k["planted"]) == n for k in key) for n in (0, 1, 2, 3)] == [24] * 4
    for k in key:
        for c, a in zip(K.CODES, k["required"]):
            assert a in K.ANCHORS[c]["+" if c in k["planted"] else "-"], (k["id"], c)


def test_anchors_are_distinct_and_not_substrings_of_each_other():
    flat = [b.flat(p) for pols in K.ANCHORS.values() for ph in pols.values() for p in ph]
    assert len(flat) == 24 and len(set(flat)) == 24
    assert not [(x, y) for x in flat for y in flat if x != y and x in y]  # presence of one anchor can never imply another


def spec_for(item, extra=""):
    return "Parcelo ships next month to 400 pilot users. " + " and ".join(item["required"]) + ". " + extra + "The pilot runs six weeks. " * 8


def test_invalid_accepts_the_key_and_rejects_each_fault():
    item = json.loads((D / "key.json").read_text())[7]
    assert b.invalid(spec_for(item), item) is None
    assert "missing" in b.invalid(spec_for(item).replace(item["required"][0], "x"), item)
    assert "length" in b.invalid("short " + " ".join(item["required"]), item)
    flip = K.ANCHORS["SRM"]["-" if "SRM" in item["planted"] else "+"][0]  # the opposite polarity of the SRM anchor this item carries
    assert "opposite" in b.invalid(spec_for(item, flip + ". "), item)
    assert "stray" in b.invalid(spec_for(item, "Results differ by segment. "), item)
    assert "generic hedge" in b.invalid(spec_for(item, "However, we double-checked it. "), item)


def test_parse_shapes():
    assert b.parse("review\nERRORS: SRM, PEEK\nDECISION: HOLD") == ({"SRM", "PEEK"}, "HOLD")
    assert b.parse("**ERRORS:** NONE\n**DECISION:** SHIP") == (set(), "SHIP")
    assert b.parse("ERRORS: <SIMPSON>\nDECISION: **HOLD**") == ({"SIMPSON"}, "HOLD")
    assert b.parse("ERRORS: NOVELTY, DENOM, POWER\nDECISION: HOLD") == ({"NOVELTY", "DENOM", "POWER"}, "HOLD")
    assert b.parse("ERRORS: SRM\nDECISION: SHIP\nlater\nERRORS: PEEK\nDECISION: HOLD") == ({"PEEK"}, "HOLD")  # the last lines count
    assert b.parse("The SRM issue is serious. Decision: hold") == (None, None)  # prose is not the protocol
    assert b.parse("ERRORS: none found\nDECISION: SHIP") == (set(), "SHIP")
    assert b.parse("ERRORS: unclear\nDECISION: SHIP") == (None, "SHIP")
    assert b.parse("ERRORS: SRM, FOO\nDECISION: HOLD") == ({"SRM"}, "HOLD")


def test_score_one_recall_false_alarm_and_unparsed():
    r = b.score_one("ERRORS: SRM, DENOM\nDECISION: HOLD", ["SRM", "PEEK"], 10)
    assert (r["recall"], r["hold"], r["pass"], r["fa"], r["unparsed"]) == (0.5, 1.0, None, 1 / 4, 0.0)
    r = b.score_one("ERRORS: NONE\nDECISION: SHIP", [], 10)
    assert (r["recall"], r["hold"], r["pass"], r["fa"]) == (None, None, 1.0, 0.0)
    r = b.score_one("ERRORS: PEEK\nDECISION: HOLD", [], 10)
    assert (r["pass"], r["fa"]) == (0.0, 1 / 6)  # a sound readout held, one false alarm
    r = b.score_one("no protocol lines at all", ["SRM"], 10)
    assert (r["recall"], r["hold"], r["unparsed"]) == (0.0, 0.0, 1.0)  # unusable answer: no flags, wrong decision
    assert b.score_one("no protocol lines", [], 10)["pass"] == 0.0


def synth(recall, fa, pass_, tokens=100, unparsed=0.0, n=40):
    rows = [{"id": f"s{i}", "recall": recall + 0.01 * (i % 3), "hold": 1.0, "pass": None, "fa": fa, "unparsed": unparsed, "words": 50, "tokens": tokens} for i in range(n)]
    return rows + [{"id": f"b{i}", "recall": None, "hold": None, "pass": pass_, "fa": fa, "unparsed": unparsed, "words": 50, "tokens": tokens} for i in range(n // 2)]


def test_keep_rule_each_condition_can_fail_alone():
    miss = {"A": 0, "B": 0}
    good = {"A": synth(0.9, 0.0, 1.0), "B": synth(0.5, 0.0, 1.0)}
    assert b.verdict(good, "A", "B", miss)[1] == "WIN"
    worse = {"A": synth(0.5, 0.0, 1.0), "B": synth(0.9, 0.0, 1.0)}
    assert b.verdict(worse, "A", "B", miss)[1] == "LOSS"
    tie = {"A": synth(0.5, 0.0, 1.0), "B": synth(0.5, 0.0, 1.0)}
    assert b.verdict(tie, "A", "B", miss)[1] == "NOT A WIN"
    for name, a in (("false alarm", synth(0.9, 0.2, 1.0)), ("benign pass", synth(0.9, 0.0, 0.5)), ("tokens", synth(0.9, 0.0, 1.0, tokens=200)), ("unparsed", synth(0.9, 0.0, 1.0, unparsed=0.2))):
        checks, label = b.verdict({"A": a, "B": good["B"]}, "A", "B", miss)
        assert label == "NOT A WIN" and list(checks.values()).count(False) == 1, name
    assert b.verdict(good, "A", "B", {"A": 1, "B": 0})[1] == "NOT A WIN"  # a missing answer fails completeness


def test_keep_rule_constants_and_frozen_texts():
    assert (b.MARGIN_FA, b.NONINF_PASS, b.TOKENS_X, b.MAX_UNPARSED, b.SAMPLES) == (0.03, -0.15, 1.25, 0.05, 2)
    assert (D / "prompts/NONE.txt").read_text() == "You are a helpful assistant.\n"
    assert "ERRORS:" in (D / "prompts/task.txt").read_text()
    assert (D / "prompts/V0.md").read_bytes() == (ROOT / "docs/bench/growth-r5-1018/frozen/growth-analytics.v0.md").read_bytes()  # the shipped text the rounds used
    assert (D / "prompts/RIVAL.txt").read_bytes() == (ROOT / "docs/bench/growth-analytics-rubricfree-1016/prompts/rival.txt").read_bytes()


def test_frozen_hashes_match_files_and_ledger_precedes_scenarios():
    lines = (D / "SHA256-frozen.txt").read_text().splitlines()
    assert len(lines) == 10
    for ln in lines:
        h, p = ln.split("  ")
        assert hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h, p
    led = [json.loads(x) for x in (D / "ledger.jsonl").read_text().splitlines()]
    pre = hashlib.sha256(("\n".join(lines[:9]) + "\n").encode()).hexdigest()
    assert led[0]["event"] == "preregistered" and led[0]["sha256"] == pre
    assert next(i for i, e in enumerate(led) if e["event"] == "scenarios_frozen") < next(i for i, e in enumerate(led) if e["event"] == "call" and e["role"] == "answer")


def test_committed_scenarios_carry_the_key():
    S, key = json.loads((D / "scenarios_held.json").read_text()), {k["id"]: k for k in json.loads((D / "key.json").read_text())}
    assert len(S) >= 80 and sum(not key[s["id"]]["planted"] for s in S) >= 20
    for s in S:
        assert not b.invalid(s["spec"], key[s["id"]]), s["id"]


def test_committed_verdict_follows_from_committed_scores():
    S = json.loads((D / "per_scenario_held.json").read_text())
    rep = (D / "report_held.txt").read_text().splitlines()
    for base in ("RIVAL", "NONE"):
        miss = {"V0": 0, "RIVAL": 0, "NONE": 0}  # report_held.txt shows missing=0 for every arm (asserted next)
        assert all(line.endswith("missing=0") for line in rep if line.split(":")[0] in S)
        assert f"-> {b.verdict(S, 'V0', base, miss)[1]} (V0 against {base})" in rep


if __name__ == "__main__":
    tests = [fn for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for fn in tests:
        fn()
    print(f"{len(tests)}/{len(tests)} passed")
