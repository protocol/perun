#!/usr/bin/env python3
"""Offline tests for docs/bench/comms-outcome-1019: the deterministic scoring, the scenario audit and the committed scenario files.

No PCSS call is made. Each test fails if the scorer drifts from the preregistered definitions.
"""
import json, sys
from pathlib import Path

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parent.parent / "docs/bench/comms-outcome-1019"
sys.path.insert(0, str(D))
import audit, bench as b
import fixed  # noqa: F401  patches bench._numbers (amendment A2)


def test_norm_matches_number_and_date_spellings():
    assert not b.dropped("Pick by October 24: $2.4 million, 15 percent faster.", ["2.4M", "Oct 24", "15%"])
    assert b.dropped("Pick by Friday.", ["Thursday", "2.4M"]) == ["Thursday", "2.4M"]


def test_invented_counts_derived_figures_and_weekdays_not_list_markers():
    src = "A costs 2.4M, B costs 3.1M. Decide by Thursday."
    assert b.invented("1. A is 2.4M\n2. B is 3.1M, decide Thursday", src) == []
    assert b.invented("B costs 0.7M more; decide Friday", src) == ["0.7", "fri"]
    assert b.invented("decide Thursday", "decide Thu, 2") == []


def test_parse_json_and_words():
    assert b.parse_json('noise {"decision": true} tail') == {"decision": True}
    assert b.parse_json("no json here") is None and b.parse_json("{bad json}") is None
    assert b.words("one two  three") == 3


def test_paired_mean_and_ci_order():
    m, lo, hi = b.paired([1, 1, 1, 0.5], [0, 0, 0, 0.5])
    assert abs(m - 0.75) < 1e-9 and lo <= m <= hi
    assert b.paired([1, 0], [1, 0]) == (0.0, 0.0, 0.0)


def test_audit_flags_gold_figure_absent_from_notes():
    sc = {"prompt": "Cost 5k by Tuesday.", "decision": "pick", "action": "reply Tuesday", "owner": "Jo", "deadline": "Tuesday", "number": "5k"}
    assert audit.bad(sc) == []
    assert audit.bad({**sc, "number": "7k difference"}) == ["number"]


def test_committed_scenarios_are_valid():
    for split, n in (("tune", 40), ("held", 30)):
        p = D / f"scenarios_{split}.json"
        if not p.exists():  # held-out is written after the selection is frozen
            continue
        S = json.loads(p.read_text())
        assert len(S) >= n and len({s["id"] for s in S}) == len(S), split
        for s in S:
            assert not b.dropped(s["prompt"], s["facts"]) and not audit.bad(s), s["id"]
            assert set(b.QS) <= set(s) and s["split"] == split


def test_arm_prompts_exist():
    for a in ("V0", "NONE", "RIVAL"):
        assert b.arm_system(a).strip()


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
for t in TESTS:
    t()
print(f"test_comms_outcome_bench: Tests: {len(TESTS)}/{len(TESTS)} ok")
