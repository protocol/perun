#!/usr/bin/env python3
"""idea-critic V5 bench. See PREREGISTERED.md (frozen) and README.md.
Reuses ../../idea-critic-outcome-1019/bench_outcome.py (PCSS call, parser, scoring); only the arms, corpora and report differ.
PCSS only (free); PCSS_ENV must point at a file holding PCSS_KEY (never printed).
usage: [V5_VARIANT=<name>] bench_v5.py SPLIT check | run MODEL | report MODEL | pooled
  SPLIT = tune    the 118 tune cases: the 88 of the three earlier idea-critic benches plus the 30 V4 held-out cases (spent for V4, so
                  free for tuning V5); only the V5 arm is generated (dev/skill_<name>.txt -> tune/<name>/), V0, V4 and BASE are read
                  from the committed outputs of the benches that made them. Run on the first model only.
                  Selection rule, fixed before any tune call: among variants with tune false-GO <= 0.03 pick the highest tune
                  accuracy (a gap under 0.01 goes to lower false-GO, then fewer completion tokens); if none is eligible pick the
                  lowest false-GO, ties by accuracy.
        | heldout the 30 fresh frozen cases in corpus.json; arms V0, V4, V5, BASE all generated here, only after the
                  `preregistered` line is the first line of ledger.jsonl. `pooled` = headline over all MODELS."""
import json, os, sys
from pathlib import Path

N = Path(__file__).resolve().parent
OUT = N.parents[1] / "idea-critic-outcome-1019"
CAL = N.parents[1] / "idea-critic-calibration-1019"
V2 = N.parent / "idea-critic-v2-1019"
V4 = N.parent / "idea-critic-v4-1019"
sys.path[:0] = [str(OUT), str(N.parents[2] / "scripts")]
import bench_outcome as bo  # noqa: E402

SPLIT = sys.argv[1]
TUNE = SPLIT == "tune"
VARIANT = os.environ.get("V5_VARIANT", "")
MODELS = ["Qwen3.5-397B-A17B", "DeepSeek-V4-Flash", "GLM-5.2"]
ARMS = {"V0": V2 / "prompts/skill_v0.txt", "V4": V4 / "prompts/skill_v4.txt",
        "V5": N / "dev" / f"skill_{VARIANT}.txt" if TUNE else N / "prompts/skill_v5.txt", "BASE": None}
_corpus = bo.corpus


def load(d):
    """Validated corpus.json of bench dir d (bo.corpus asserts keys, sources and no name leak)."""
    h, bo.H = bo.H, d
    try:
        return [dict(x, src=d) for x in _corpus()]
    finally:
        bo.H = h


CASES = load(OUT) + load(CAL) + load(V2) + load(V4) if TUNE else load(N)
bo.H = N / "tune" / VARIANT if TUNE else N  # outputs, ledger.jsonl and results of this split land here
bo.ARMS = {"V5": ARMS["V5"]} if TUNE else ARMS  # arms bo.run generates
bo.corpus = lambda: CASES


def out(model, arm, x, r):
    """Output file of one call. Tune V0, V4 and BASE come from the earlier bench that made them (V0 was named PERUN in the
    outcome bench; V4 on the 88 earlier cases is the dev run of its final wording, skill_v4b)."""
    if arm == "V5" or not TUNE:
        return bo.path(model, arm, x["id"], r)
    if arm == "V4" and x["src"] != V4:
        return V4 / "dev/v4b/outputs" / model / "V4" / f"{x['id']}.{r}.txt"
    return x["src"] / "outputs" / model / ("PERUN" if arm == "V0" and x["src"] == OUT else arm) / f"{x['id']}.{r}.txt"


def verdict(res):
    """Frozen keep rule: WIN when the V5-V0 paired accuracy CI lower bound > 0 and V5 makes no false GO at all."""
    d, g = res["paired"]["V5_minus_V0"]["accuracy"], res["arms"]["V5"]["false_go_rate"]["mean"] == 0
    return "WIN" if d["ci95"][0] > 0 and g else "LOSS" if d["ci95"][1] < 0 or not g else "TIE"


def run(model):
    """Generate missing outputs; a held-out run needs the preregistration line first in the ledger."""
    if not TUNE:
        first = json.loads((N / "ledger.jsonl").read_text().splitlines()[0])
        assert first.get("event") == "preregistered", "held-out run before preregistration"
    bo.H.mkdir(parents=True, exist_ok=True)
    bo.run(model)


def percase(model, cases):
    """({arm: {case id: {acc, go}}}, {arm: invalid decisions}) for one model; missing or unparseable decisions count wrong."""
    per, inv = {}, {}
    for a in ARMS:
        per[a], inv[a] = {}, 0
        for x in cases:
            ds = []
            for r in range(bo.REPS):
                p = out(model, a, x, r)
                ds.append(bo.parse(p.read_text(encoding="utf-8")) if p.exists() else None)
            inv[a] += sum(d is None for d in ds)
            per[a][x["id"]] = dict(acc=sum(bo.right(x, d) for d in ds) / bo.REPS, go=sum(d == "GO" for d in ds) / bo.REPS)
    return per, inv


def tokens(model):
    """{arm: completion tokens per call} from this split's ledger (the `preregistered` event line carries no tag)."""
    t, ids = {}, {x["id"] for x in CASES}  # calls on cases voided from the corpus (see PREREGISTERED.md amendment) are not counted
    for l in (bo.H / "ledger.jsonl").read_text().splitlines():
        j = json.loads(l)
        p = j.get("tag", "").split("/")
        if p[0] == "out" and p[1] == model and p[3] in ids and not j["err"]:
            t.setdefault(p[2], []).append(j["usage"].get("completion_tokens", 0))
    return {a: round(sum(v) / len(v)) for a, v in t.items()}


def summary(models, cases):
    """Report over cases for one model, or pooled over several: per case each arm's accuracy and GO rate are averaged over the
    models, then bootstrapped over cases (paired, 10,000 resamples, seed 1)."""
    from rival_eval import boot
    ps = [percase(m, cases) for m in models]
    ids = [x["id"] for x in cases]
    bad, good = [x["id"] for x in cases if x["key"] == "bad"], [x["id"] for x in cases if x["key"] == "good"]
    avg = lambda a, i, k: sum(p[0][a][i][k] for p in ps) / len(ps)  # noqa: E731

    def m(v):
        lo, hi = boot(v)
        return dict(mean=round(sum(v) / len(v), 3), ci95=[round(lo, 3), round(hi, 3)], n=len(v))
    res = dict(models=models, n_cases=len(ids), n_good=len(good), n_bad=len(bad), reps=bo.REPS, arms={}, paired={})
    for a in ARMS:
        res["arms"][a] = dict(accuracy=m([avg(a, i, "acc") for i in ids]), false_go_rate=m([avg(a, i, "go") for i in bad]),
                              false_no_go_rate=m([1 - avg(a, i, "go") for i in good]), invalid_decisions=sum(p[1][a] for p in ps))
    for o in ("V0", "V4", "BASE"):
        res["paired"][f"V5_minus_{o}"] = dict(accuracy=m([avg("V5", i, "acc") - avg(o, i, "acc") for i in ids]),
                                              false_go_rate=m([avg("V5", i, "go") - avg(o, i, "go") for i in bad]))
    res["verdict"] = verdict(res)
    return res


def report(model):
    """results-<model>.json; tune adds the 30 V4 held-out cases alone (`v4_heldout`), where V4 was never tuned."""
    res = summary([model], CASES)
    if TUNE:
        res["v4_heldout"] = summary([model], [x for x in CASES if x["src"] == V4])
    res["completion_tokens_per_call"] = tokens(model) if (bo.H / "ledger.jsonl").exists() else {}
    (bo.H / f"results-{model}.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


def pooled():
    """results-pooled.json (headline, frozen rule over all MODELS); each model's own verdict is in its results-<model>.json."""
    res = summary(MODELS, CASES)
    (N / "results-pooled.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"check": lambda *_: print(len(CASES), "cases ok"), "run": run, "report": report, "pooled": lambda *_: pooled()}[sys.argv[2]](*sys.argv[3:])
