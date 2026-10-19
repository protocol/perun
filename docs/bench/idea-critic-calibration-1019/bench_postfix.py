#!/usr/bin/env python3
"""Post-hoc, NOT preregistered: the shipped SKILL.md (V1T) is V1 minus 498 bytes of non-decision prose (the 16000-byte core cap
forced the cut). Runs V1T on the frozen held-out corpus once and compares it with the preregistered V0/V1/BASE outputs. Outside the
verdict in PREREG.md. See README.md. PCSS only (free); PCSS_ENV must point at a file holding PCSS_KEY (never printed).
usage: bench_postfix.py run MODEL | report MODEL"""
import json, sys
from pathlib import Path

N = Path(__file__).resolve().parent
B = N.parent / "idea-critic-outcome-1019"
sys.path[:0] = [str(B), str(N.parents[2] / "scripts")]
import bench_outcome as bo  # noqa: E402

bo.H = N / "postfix"  # V1T outputs and its own ledger.jsonl land here
bo.ARMS = {"V1T": N / "prompts/skill_v1t.txt"}
CASES = json.loads((N / "corpus.json").read_text(encoding="utf-8"))
bo.corpus = lambda: CASES


def acc(model, arm, root):
    """{case: mean decision accuracy over the 3 samples} from root/outputs."""
    return {x["id"]: sum(bo.right(x, bo.parse((root / "outputs" / model / arm / f"{x['id']}.{r}.txt").read_text(encoding="utf-8")))
                         for r in range(bo.REPS)) / bo.REPS for x in CASES}


def report(model):
    from rival_eval import boot
    ids = [x["id"] for x in CASES]
    bad = [x["id"] for x in CASES if x["key"] == "bad"]
    mine = {a: acc(model, a, bo.H) for a in bo.ARMS}["V1T"]
    base = {a: acc(model, a, N) for a in ("V0", "V1", "BASE")}

    def m(v):
        lo, hi = boot(v)
        return dict(mean=round(sum(v) / len(v), 3), ci95=[round(lo, 3), round(hi, 3)], n=len(v))
    go = {}  # false-go per bad case: the share of GO decisions
    for i in bad:
        go[i] = sum(bo.parse((bo.H / "outputs" / model / "V1T" / f"{i}.{r}.txt").read_text(encoding="utf-8")) == "GO" for r in range(bo.REPS)) / bo.REPS
    res = dict(model=model, preregistered=False, accuracy=m([mine[i] for i in ids]), false_go_rate=m(list(go.values())),
               paired_accuracy={f"V1T_minus_{a}": m([mine[i] - base[a][i] for i in ids]) for a in base})
    (bo.H / f"results-{model}.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"run": bo.run, "report": report}[sys.argv[1]](*sys.argv[2:])
