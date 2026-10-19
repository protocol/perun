#!/usr/bin/env python3
"""idea-critic V4 cross-model bench. See PREREG.md (frozen).
Reuses ../idea-critic-v4-1019/bench_v4.py unchanged (frozen held-out corpus, arms V0/V4/BASE, per-model report and verdict);
only the model, the output directory and the pooled report differ. PCSS only (free); PCSS_ENV must point at a file holding
PCSS_KEY (never printed).
usage: bench_xmodel.py check | run MODEL | report MODEL | pooled"""
import json
import sys
from pathlib import Path

N = Path(__file__).resolve().parent
V4 = N.parent / "idea-critic-v4-1019"
CMD = sys.argv[1]
sys.argv[1:2] = ["heldout"]  # bench_v4 reads its SPLIT from argv[1] at import
sys.path[:0] = [str(V4)]
import bench_v4 as v4  # noqa: E402
from rival_eval import boot  # noqa: E402

bo = v4.bo
bo.H = N  # outputs, ledger.jsonl and results of this bench land here, never in the V4 dir
MODELS = ["DeepSeek-V4-Flash", "GLM-5.2"]
QWEN = "Qwen3.5-397B-A17B"


def run(model):
    """Generate missing outputs; needs the preregistration line first in this bench's ledger."""
    first = json.loads((N / "ledger.jsonl").read_text().splitlines()[0])
    assert first.get("event") == "preregistered", "run before preregistration"
    bo.run(model)


def percase(model, h):
    """{arm: {case id: {acc, go}}} from the outputs under h (this bench dir, or the V4 dir for Qwen)."""
    bo.H = h
    try:
        per = {}
        for a in v4.ARMS:
            per[a] = {}
            for x in v4.CASES:
                ds = []
                for r in range(bo.REPS):
                    p = v4.out(model, a, x, r)
                    ds.append(bo.parse(p.read_text(encoding="utf-8")) if p.exists() else None)
                per[a][x["id"]] = dict(acc=sum(bo.right(x, d) for d in ds) / bo.REPS, go=sum(d == "GO" for d in ds) / bo.REPS)
        return per
    finally:
        bo.H = N


def pool(sources):
    """Pooled report over [(model, outputs dir)]: per case, average each arm's acc and GO rate over the models, bootstrap over cases."""
    ps = [percase(m, h) for m, h in sources]
    ids = [x["id"] for x in v4.CASES]
    bad, good = [x["id"] for x in v4.CASES if x["key"] == "bad"], [x["id"] for x in v4.CASES if x["key"] == "good"]
    avg = lambda a, i, k: sum(p[a][i][k] for p in ps) / len(ps)  # noqa: E731

    def m(v):
        lo, hi = boot(v)
        return dict(mean=round(sum(v) / len(v), 3), ci95=[round(lo, 3), round(hi, 3)], n=len(v))
    res = dict(models=[s[0] for s in sources], n_cases=len(ids), reps=bo.REPS, arms={}, paired={})
    for a in v4.ARMS:
        res["arms"][a] = dict(accuracy=m([avg(a, i, "acc") for i in ids]), false_go_rate=m([avg(a, i, "go") for i in bad]),
                              false_no_go_rate=m([1 - avg(a, i, "go") for i in good]))
    for o in ("V0", "BASE"):
        res["paired"][f"V4_minus_{o}"] = dict(accuracy=m([avg("V4", i, "acc") - avg(o, i, "acc") for i in ids]),
                                              false_go_rate=m([avg("V4", i, "go") - avg(o, i, "go") for i in bad]))
    return res


def pooled():
    """results-pooled.json: `new_models` decides (frozen rule); `with_qwen` is descriptive and carries no verdict."""
    new = pool([(m, N) for m in MODELS])
    new["verdict"] = v4.verdict(new)
    out = dict(new_models=new, with_qwen=pool([(m, N) for m in MODELS] + [(QWEN, V4)]))
    (N / "results-pooled.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    {"check": lambda *_: print(len(v4.CASES), "cases ok"), "run": run, "report": v4.report, "pooled": lambda *_: pooled()}[CMD](*sys.argv[2:])
