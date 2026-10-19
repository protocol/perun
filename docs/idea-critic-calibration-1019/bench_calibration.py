#!/usr/bin/env python3
"""Calibration bench for the idea-critic over-blocking fix. See PREREG.md (frozen) and README.md.
Reuses bench_outcome.py (PCSS call, parser, scoring) from ../idea-critic-outcome-1019; only the arms, corpus and report differ.
PCSS only (free); PCSS_ENV must point at a file holding PCSS_KEY (never printed).
usage: bench_calibration.py SPLIT check | run MODEL | report MODEL     SPLIT = dev (the 36 cases the fix was tuned on) | heldout (the 24 frozen cases)"""
import json, sys
from pathlib import Path

N = Path(__file__).resolve().parent
B = N.parent / "idea-critic-outcome-1019"
sys.path[:0] = [str(B), str(N.parents[1] / "scripts")]
import bench_outcome as bo  # noqa: E402

SPLIT = sys.argv[1]
SRC = B if SPLIT == "dev" else N  # where corpus.json lives
bo.H = N if SPLIT == "heldout" else N / "dev"  # outputs, ledger.jsonl and results land here (held-out ones at the bench root)
bo.ARMS = {"V0": N / "prompts/skill_v0.txt", "V1": N / "prompts/skill_v1.txt", "BASE": None}
if SPLIT == "heldout":
    bo.ARMS["RIVAL"] = N.parent / "bench/exec-1017/prompts/rival_idea-critic.txt"  # reference only, not tuned against
_corpus = bo.corpus


def corpus():
    h, bo.H = bo.H, SRC  # bo.corpus reads H/corpus.json
    try:
        return _corpus()
    finally:
        bo.H = h


bo.corpus = corpus


def tokens(model):
    """{(arm, case, rep): (prompt, completion)} from successful call lines; the leading `preregistered` event has no tag."""
    t = {}
    for l in (bo.H / "ledger.jsonl").read_text().splitlines():
        j = json.loads(l)
        p = j.get("tag", "").split("/")
        if p[0] == "out" and p[1] == model and not j["err"]:
            t[(p[2], p[3], int(p[4]))] = (j["usage"].get("prompt_tokens", 0), j["usage"].get("completion_tokens", 0))
    return t


def report(model):
    from rival_eval import boot
    c, tk = corpus(), tokens(model)
    ids = [x["id"] for x in c]
    bad, good = [x["id"] for x in c if x["key"] == "bad"], [x["id"] for x in c if x["key"] == "good"]
    per, inv, tok = {}, {}, {}
    for a in bo.ARMS:
        per[a], inv[a], tok[a] = {}, 0, []
        for x in c:
            ds = []
            for r in range(bo.REPS):
                p = bo.path(model, a, x["id"], r)
                d = bo.parse(p.read_text(encoding="utf-8")) if p.exists() else None
                inv[a] += d is None
                ds.append(d)
                tok[a].append(tk.get((a, x["id"], r), (0, 0)))
            per[a][x["id"]] = dict(acc=sum(bo.right(x, d) for d in ds) / bo.REPS, go=sum(d == "GO" for d in ds) / bo.REPS)

    def m(v):
        lo, hi = boot(v)
        return dict(mean=round(sum(v) / len(v), 3), ci95=[round(lo, 3), round(hi, 3)], n=len(v))
    res = dict(model=model, split=SPLIT, n_cases=len(c), n_good=len(good), n_bad=len(bad), reps=bo.REPS, arms={}, paired={})
    for a in bo.ARMS:
        res["arms"][a] = dict(accuracy=m([per[a][i]["acc"] for i in ids]), false_go_rate=m([per[a][i]["go"] for i in bad]),
                              false_no_go_rate=m([1 - per[a][i]["go"] for i in good]), invalid_decisions=inv[a], calls=len(tok[a]),
                              completion_tokens_per_call=round(sum(q for _, q in tok[a]) / len(tok[a])))
    for o in bo.ARMS:
        if o != "V1":
            res["paired"][f"V1_minus_{o}"] = dict(accuracy=m([per["V1"][i]["acc"] - per[o][i]["acc"] for i in ids]),
                                                  false_go_rate=m([per["V1"][i]["go"] - per[o][i]["go"] for i in bad]))
    (bo.H / f"results-{model}.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"check": lambda *_: print(len(corpus()), "cases ok"), "run": bo.run, "report": report}[sys.argv[2]](*sys.argv[3:])
