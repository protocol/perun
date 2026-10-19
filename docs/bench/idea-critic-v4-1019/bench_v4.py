#!/usr/bin/env python3
"""idea-critic V4 bench. See PREREG.md (frozen) and README.md.
Reuses ../../idea-critic-outcome-1019/bench_outcome.py (PCSS call, parser, scoring); only the arms, corpus and report differ.
PCSS only (free); PCSS_ENV must point at a file holding PCSS_KEY (never printed).
usage: [V4_VARIANT=<name>] bench_v4.py SPLIT check | run MODEL | report MODEL
  SPLIT = dev     the 88 cases of the three earlier idea-critic benches (outcome, calibration, V2 held-out; V4 is designed on
                  these, and V3's held-out is not used); only the V4 arm is generated, V0 and BASE are read from those benches'
                  committed outputs. V4_VARIANT=<name> reads dev/skill_<name>.txt and writes dev/<name>/.
        | heldout the 30 fresh frozen cases in corpus.json; arms V0, V4, BASE all generated here, and only after the
                  `preregistered` line is the first line of ledger.jsonl"""
import json, os, sys
from pathlib import Path

N = Path(__file__).resolve().parent
OUT = N.parents[1] / "idea-critic-outcome-1019"
CAL = N.parents[1] / "idea-critic-calibration-1019"
V2 = N.parent / "idea-critic-v2-1019"
sys.path[:0] = [str(OUT), str(N.parents[2] / "scripts")]
import bench_outcome as bo  # noqa: E402

SPLIT = sys.argv[1]
VARIANT = os.environ.get("V4_VARIANT", "")
PROMPT = N / "dev" / f"skill_{VARIANT}.txt" if SPLIT == "dev" else N / "prompts/skill_v4.txt"
ARMS = {"V0": V2 / "prompts/skill_v0.txt", "V4": PROMPT, "BASE": None}
_corpus = bo.corpus


def load(d):
    """Validated corpus.json of bench dir d (bo.corpus asserts keys, sources and no name leak)."""
    h, bo.H = bo.H, d
    try:
        return [dict(x, src=d) for x in _corpus()]
    finally:
        bo.H = h


CASES = load(N) if SPLIT == "heldout" else load(OUT) + load(CAL) + load(V2)
bo.H = N if SPLIT == "heldout" else N / "dev" / VARIANT  # outputs, ledger.jsonl and results of this split land here
bo.ARMS = ARMS if SPLIT == "heldout" else {"V4": ARMS["V4"]}  # arms bo.run generates
bo.corpus = lambda: CASES


def out(model, arm, x, r):
    """Output file of one call; dev V0 and BASE come from the earlier bench that made them (V0 was named PERUN there)."""
    if SPLIT == "heldout" or arm == "V4":
        return bo.path(model, arm, x["id"], r)
    return x["src"] / "outputs" / model / ("PERUN" if arm == "V0" and x["src"] == OUT else arm) / f"{x['id']}.{r}.txt"


def tokens(model):
    """{(arm, case, rep): completion tokens} from this split's ledger; the `preregistered` event line carries no tag."""
    t = {}
    for l in (bo.H / "ledger.jsonl").read_text().splitlines():
        j = json.loads(l)
        p = j.get("tag", "").split("/")
        if p[0] == "out" and p[1] == model and not j["err"]:
            t[(p[2], p[3], int(p[4]))] = j["usage"].get("completion_tokens", 0)
    return t


def verdict(res):
    """Frozen rule (PREREG.md): WIN when the V4-V0 paired accuracy CI lower bound > 0 and V4 makes no false GO at all."""
    d, a = res["paired"]["V4_minus_V0"]["accuracy"], res["arms"]
    guard = a["V4"]["false_go_rate"]["mean"] == 0
    return "WIN" if d["ci95"][0] > 0 and guard else "LOSS" if d["ci95"][1] < 0 or not guard else "TIE"


def run(model):
    """Generate missing outputs; a held-out run needs the preregistration line first in the ledger."""
    if SPLIT == "heldout":
        first = json.loads((N / "ledger.jsonl").read_text().splitlines()[0])
        assert first.get("event") == "preregistered", "held-out run before preregistration"
    bo.H.mkdir(parents=True, exist_ok=True)
    bo.run(model)


def report(model):
    from rival_eval import boot
    tk = tokens(model)
    ids = [x["id"] for x in CASES]
    bad, good = [x["id"] for x in CASES if x["key"] == "bad"], [x["id"] for x in CASES if x["key"] == "good"]
    per, inv, tok = {}, {}, {}
    for a in ARMS:
        per[a], inv[a], tok[a] = {}, 0, []
        for x in CASES:
            ds = []
            for r in range(bo.REPS):
                p = out(model, a, x, r)
                d = bo.parse(p.read_text(encoding="utf-8")) if p.exists() else None
                inv[a] += d is None
                ds.append(d)
                if (a, x["id"], r) in tk:
                    tok[a].append(tk[(a, x["id"], r)])
            per[a][x["id"]] = dict(acc=sum(bo.right(x, d) for d in ds) / bo.REPS, go=sum(d == "GO" for d in ds) / bo.REPS)

    def m(v):
        lo, hi = boot(v)
        return dict(mean=round(sum(v) / len(v), 3), ci95=[round(lo, 3), round(hi, 3)], n=len(v))
    res = dict(model=model, split=SPLIT, n_cases=len(CASES), n_good=len(good), n_bad=len(bad), reps=bo.REPS, arms={}, paired={})
    for a in ARMS:
        res["arms"][a] = dict(accuracy=m([per[a][i]["acc"] for i in ids]), false_go_rate=m([per[a][i]["go"] for i in bad]),
                              false_no_go_rate=m([1 - per[a][i]["go"] for i in good]), invalid_decisions=inv[a],
                              completion_tokens_per_call=round(sum(tok[a]) / len(tok[a])) if tok[a] else None)
    for o in ("V0", "BASE"):
        res["paired"][f"V4_minus_{o}"] = dict(accuracy=m([per["V4"][i]["acc"] - per[o][i]["acc"] for i in ids]),
                                              false_go_rate=m([per["V4"][i]["go"] - per[o][i]["go"] for i in bad]))
    res["verdict"] = verdict(res)
    (bo.H / f"results-{model}.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"check": lambda *_: print(len(CASES), "cases ok"), "run": run, "report": report}[sys.argv[2]](*sys.argv[3:])
