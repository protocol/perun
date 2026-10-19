#!/usr/bin/env python3
"""Offline tests for docs/bench/comms-e4-confirm-1019: the powered confirmation of edit E4 reuses r2's harness unchanged, copies its keep rule verbatim,
holds enough valid fresh scenarios, and the committed verdict follows from the committed scores and matches what the skill ships. No PCSS call is made."""
import json, re, sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "docs/bench/comms-e4-confirm-1019"
R2 = ROOT / "docs/bench/comms-outcome-r2-1019"
SKILL = ROOT / ".claude/skills/communication-structure/SKILL.md"
sys.path.insert(0, str(D))
sys.path.insert(0, str(ROOT / "scripts"))
import fabjudge as f  # noqa: E402
import bench_check as bc  # noqa: E402

b = f.b
E4_LINES = [l for l in (D / "prompts/E4.txt").read_text().splitlines(keepends=True) if l not in (D / "prompts/V0.txt").read_text().splitlines(keepends=True)]


def keep_rule(path):
    t = path.read_text()
    return t[t.index("## Keep rule for E4"):t.index("## Procedure")].rstrip()


def test_harness_and_prompts_are_r2_byte_for_byte():
    for n in ("fabjudge.py", "run_held.py", "report.py", *(f"prompts/{p}.txt" for p in ("V0", "E4", "reader", "grader", "writer_brief", "fab_judge"))):
        assert (D / n).read_bytes() == (R2 / n).read_bytes(), n


def test_keep_rule_is_r2s_verbatim():
    assert keep_rule(D / "PREREGISTERED.md") == keep_rule(R2 / "PREREGISTERED.md")
    import report
    assert (report.MARGIN, report.WORDS_X) == (0.02, 1.25)


def test_e4_is_v0_plus_two_bullets():
    assert len(E4_LINES) == 2 and all(l.startswith("- **") for l in E4_LINES)


def test_scenarios_are_enough_valid_and_fresh():
    S = json.loads((D / "scenarios_held.json").read_text())
    assert len(S) >= 243 and len({s["id"] for s in S}) == len(S)  # 243: n at which an upper bound of +0.02 is reachable at r2's variance
    for s in S:
        assert s["split"] == "held" and not b.dropped(s["prompt"], s["facts"]) and not f.fixed2.bad(s), s["id"]
    prior = [s for p, sp in ((f.R1, "tune"), (f.R1, "held"), (R2, "held")) for s in json.loads((p / f"scenarios_{sp}.json").read_text())]
    pool = set().union(*[bc.shingles(" ".join(str(v) for k, v in s.items() if k != "id")) for s in prior])
    for s in S:
        sh = bc.shingles(" ".join(str(v) for k, v in s.items() if k != "id"))
        assert len(sh & pool) <= 0.2 * len(sh), s["id"]


def test_committed_verdict_follows_from_committed_scores_and_the_skill():
    S = json.loads((D / "per_scenario_held.json").read_text())
    rep = (D / "report_held.txt").read_text()
    col = lambda a, k: [r[k] for r in S[a]]
    acc, fab = b.paired(col("E4", "acc"), col("V0", "acc")), b.paired(col("E4", "real_fab"), col("V0", "real_fab"))
    unl = {m[0]: int(m[1]) for m in re.findall(r"^(\w+): .*unlabelled_figures=(\d+)", rep, re.M)}
    keep = acc[1] > 0 and fab[2] <= 0.02 and sum(col("E4", "words")) <= 1.25 * sum(col("V0", "words")) and unl["E4"] == unl["V0"] == 0
    assert len(S["V0"]) == len(S["E4"]) == len(S["RIVAL"]) >= 243 and "missing_grades=0" in rep
    assert ("-> KEEP" if keep else "-> REVERT") in rep.splitlines()[-1]
    text = SKILL.read_text()
    assert all(l in text for l in E4_LINES) == keep  # the skill carries E4 exactly when the rule passed
    if not keep:
        assert text == (D / "prompts/V0.txt").read_text()


if __name__ == "__main__":
    t = [n for n in sorted(globals()) if n.startswith("test_")]
    for n in t:
        globals()[n]()
    print(f"{len(t)}/{len(t)} passed")
