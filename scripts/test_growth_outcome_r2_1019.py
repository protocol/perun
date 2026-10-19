#!/usr/bin/env python3
"""Offline tests for docs/bench/growth-outcome-r2-1019: the computed-error generator and key, readouts that name no error, the calibration rule, the deterministic parser and scorer, the keep rule, the frozen hashes and ledger order, and that the committed verdict follows from the committed scores.

No PCSS call is made. There is no model grader in this bench, so the generator, the parser and the scorer are what is validated.
"""
import copy, hashlib, json, re, sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "docs/bench/growth-outcome-r2-1019"
sys.path.insert(0, str(D))
import bench as b
import key as K


def load(name):
    return json.loads((D / name).read_text())


def test_committed_keys_are_exactly_what_key_py_generates():
    assert load("key_held.json") == K.make("held", load("calibration.json")["level"])
    assert load("key_tune.json") == [k for lv in range(4) for k in K.make("tune", lv)]
    assert load("scenarios_held.json") == K.scenarios(load("key_held.json"))
    assert load("scenarios_tune.json") == K.scenarios(load("key_tune.json"))


def test_held_is_balanced_and_disjoint_from_tune():
    key = load("key_held.json")
    assert len(key) == 96 and [sum(len(k["planted"]) == n for k in key) for n in range(4)] == [24] * 4
    ids = {k["id"] for k in key} | {k["id"] for k in load("key_tune.json")}
    assert len(ids) == 96 + 192  # no id shared
    held = {s["spec"] for s in load("scenarios_held.json")}
    assert not held & {s["spec"] for s in load("scenarios_tune.json")}


def test_planted_set_is_recomputed_from_the_numbers():
    for k in load("key_held.json") + load("key_tune.json"):
        assert K.truth(k["data"]) == set(k["planted"]), k["id"]


def scale_treatment(x, f):
    """Grow the treatment arm by factor f everywhere (users, orders, device rows), leaving every rate unchanged."""
    y = copy.deepcopy(x)
    y["n"]["t"] = round(y["n"]["t"] * f)
    y["orders"]["t"] = round(y["orders"]["t"] * f)
    for d in y["seg"].values():
        d["t"] = [round(v * f) for v in d["t"]]
    return y


def test_truth_flips_one_error_at_a_time_and_rejects_gray_zones():
    x = next(k for k in load("key_held.json") if not k["planted"])["data"]
    assert K.truth(x) == set()
    assert "SRM" in K.truth(scale_treatment(x, 1.02))  # a 2% arm gap at this size is far past 3.5 sigma
    y = copy.deepcopy(x)
    y["end"] = y["start"]  # zero days run
    assert "PEEK" in K.truth(y)
    y = copy.deepcopy(x)
    y["reported"]["c"] = round(100 * y["orders"]["c"] / y["sessions"]["c"], 3)
    assert ("DENOM" in K.truth(y)) == (abs(y["sessions"]["c"] / y["n"]["c"] - 1) > 0.005)  # only distinguishable when sessions differ from users
    y = copy.deepcopy(x)
    y["series"] = [10.0] * 3 + [1.0] * 3
    assert "NOVELTY" in K.truth(y)
    y = copy.deepcopy(x)
    y["series"] = [10.0] * 3 + [6.0] * 3  # ratio 0.6: between the planted and the sound limit
    assert K.truth(y) is None
    n = x["n"]
    gap = 2.5 * (n["c"] + n["t"]) ** 0.5  # |z| = 2.5: between the sound and the planted limit
    assert K.truth(scale_treatment(x, (n["c"] + gap) / n["t"])) is None


def test_n_required_matches_exact_normal_quantiles():
    from statistics import NormalDist
    z, p1, p2 = NormalDist().inv_cdf, 0.05, 0.055  # 5% baseline, +10% relative lift, 80% power, two-sided 5%
    exact = (z(0.975) + z(0.8)) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2)) / (p2 - p1) ** 2
    assert abs(K.n_required(0.05, 0.10) - exact) < 1 and round(exact) == 31231


def test_readouts_name_no_error():
    banned = re.compile(r"mismatch|\bSRM\b|peek|underpower|simpson|paradox|novelty|denominator|stopped|early|fading|decay|too small|wrong|incorrect|error|bias|invalid|flaw", re.I)
    for s in load("scenarios_held.json") + load("scenarios_tune.json"):
        assert not banned.search(s["spec"]), (s["id"], banned.search(s["spec"]).group())


def test_levels_change_the_rendering_as_documented():
    spec = lambda lv: K.render(next(k for k in load("key_tune.json") if k["level"] == lv))
    assert "users," in spec(1).split("Arms:")[1].split("By device")[0] and "users," not in spec(2).split("Arms:")[1].split("By device")[0]
    assert "planned duration" in spec(2) and "planned end" in spec(3)


def test_parse_shapes():
    assert b.parse("review\nERRORS: SRM, PEEK\nDECISION: HOLD") == ({"SRM", "PEEK"}, "HOLD")
    assert b.parse("**ERRORS:** NONE\n**DECISION:** SHIP") == (set(), "SHIP")
    assert b.parse("ERRORS: SRM\nDECISION: SHIP\nlater\nERRORS: PEEK\nDECISION: HOLD") == ({"PEEK"}, "HOLD")  # the last lines count
    assert b.parse("The SRM issue is serious. Decision: hold") == (None, None)  # prose is not the protocol
    assert b.parse("ERRORS: unclear\nDECISION: SHIP") == (None, "SHIP")
    assert b.parse("ERRORS: SRM, FOO\nDECISION: HOLD") == ({"SRM"}, "HOLD")


def test_score_one_recall_false_alarm_and_unparsed():
    r = b.score_one("ERRORS: SRM, DENOM\nDECISION: HOLD", ["SRM", "PEEK"], 10)
    assert (r["recall"], r["hold"], r["pass"], r["fa"], r["unparsed"]) == (0.5, 1.0, None, 1 / 4, 0.0)
    r = b.score_one("ERRORS: NONE\nDECISION: SHIP", [], 10)
    assert (r["recall"], r["hold"], r["pass"], r["fa"]) == (None, None, 1.0, 0.0)
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
    assert b.verdict({"A": synth(0.5, 0.0, 1.0), "B": synth(0.9, 0.0, 1.0)}, "A", "B", miss)[1] == "LOSS"
    assert b.verdict({"A": synth(0.5, 0.0, 1.0), "B": synth(0.5, 0.0, 1.0)}, "A", "B", miss)[1] == "NOT A WIN"
    for name, a in (("false alarm", synth(0.9, 0.2, 1.0)), ("benign pass", synth(0.9, 0.0, 0.5)), ("tokens", synth(0.9, 0.0, 1.0, tokens=200)), ("unparsed", synth(0.9, 0.0, 1.0, unparsed=0.2))):
        checks, label = b.verdict({"A": a, "B": good["B"]}, "A", "B", miss)
        assert label == "NOT A WIN" and list(checks.values()).count(False) == 1, name
    assert b.verdict(good, "A", "B", {"A": 1, "B": 0})[1] == "NOT A WIN"  # a missing answer fails completeness


def test_constants_and_frozen_texts():
    assert (b.MARGIN_FA, b.NONINF_PASS, b.TOKENS_X, b.MAX_UNPARSED, b.SAMPLES, b.TARGET, b.RANGE) == (0.03, -0.15, 1.25, 0.05, 2, (0.5, 0.7), (0.4, 0.8))
    assert (D / "prompts/NONE.txt").read_text() == "You are a helpful assistant.\n"
    task = (D / "prompts/task.txt").read_text()
    assert "ERRORS:" in task and not re.search(r"\b3\.5\b|7\.85|0\.9 x|0\.8 x", task)  # definitions only: no threshold or formula to execute
    assert (D / "prompts/V0.md").read_bytes() == (ROOT / "docs/bench/growth-r5-1018/frozen/growth-analytics.v0.md").read_bytes()
    assert (D / "prompts/RIVAL.txt").read_bytes() == (ROOT / "docs/bench/growth-analytics-rubricfree-1016/prompts/rival.txt").read_bytes()


def test_calibration_level_is_the_lowest_in_the_band():
    cal = load("calibration.json")
    rec = cal["attempts"][-1]["recall_by_level"]
    assert cal["level"] == next(i for i, r in enumerate(rec) if b.TARGET[0] <= r <= b.TARGET[1])
    tune = (D / "report_tune.txt").read_text().splitlines()
    assert [float(re.search(r"NONE recall=([\d.]+)", ln).group(1)) for ln in tune] == rec
    assert all(max(a["recall_by_level"]) > b.TARGET[1] for a in cal["attempts"][:-1])  # earlier versions discarded for being too easy


def test_frozen_hashes_match_files_and_ledger_order():
    lines = (D / "SHA256-frozen.txt").read_text().splitlines()
    assert len(lines) == 13
    for ln in lines:
        h, p = ln.split("  ")
        assert hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h, p
    led = [json.loads(x) for x in (D / "ledger.jsonl").read_text().splitlines()]
    assert led[0]["event"] == "preregistered" and led[0]["sha256"] == hashlib.sha256(("\n".join(lines[:11]) + "\n").encode()).hexdigest()
    assert led[1]["event"] == "held_frozen" and led[1]["key_sha256"] == lines[11].split("  ")[0] and led[1]["scenarios_sha256"] == lines[12].split("  ")[0]
    assert all(e["event"] == "call" and e["role"] == "answer" for e in led[2:])
    tune = [json.loads(x) for x in (D / "tune_ledger.jsonl").read_text().splitlines()]
    assert tune and all(e["arm"] == "NONE" for e in tune)  # skill and rival never saw the tune split


def test_committed_verdict_follows_from_committed_scores():
    S = load("per_scenario_held.json")
    rep = (D / "report_held.txt").read_text().splitlines()
    assert all(line.endswith("missing=0") for line in rep if line.split(":")[0] in S)
    miss = {a: 0 for a in S}
    none = [r["recall"] for r in S["NONE"] if r["recall"] is not None]
    informative = b.RANGE[0] <= sum(none) / len(none) <= b.RANGE[1]
    for base in ("RIVAL", "NONE"):
        label = b.verdict(S, "V0", base, miss)[1]
        got = next(ln for ln in rep if ln.startswith("->") and ln.endswith(f"(V0 against {base})"))
        assert (label in got) and (informative == ("UNINFORMATIVE" not in got)), (base, got)


if __name__ == "__main__":
    tests = [fn for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for fn in tests:
        fn()
    print(f"{len(tests)}/{len(tests)} passed")
