#!/usr/bin/env python3
"""Preregistered paired test of the candidate contribution skill against its rival (PCSS only, $0; no claude -p).

  bench.py write            draw the held-out scenarios from prompts/seeds.txt with the blind writer (never shows skill text)
  bench.py run OUT          v0, v1 (frozen/) and the rival (frozen/rival.md) on the scenarios; raw files go under OUT
  bench.py fold OUT         copy OUT outputs into results/ and fold the judge caches into results/judge-verdicts.json
Reuses scripts/rival_eval.py (generator, rubric-free judge in both orders, slot-1 gate, bootstrap seed 1). The rival's
answers are generated once per scenario and shared by both arms, so (v1 - v0) is a paired difference.
The decision rule is in PREREGISTERED.md; it is computed here from the outputs.
"""
import concurrent.futures as cf, json, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent.parent / "scripts"))
import rival_eval as R

SCEN = HERE / "scenarios-heldout60.json"


def write():
    seeds = [l for l in (HERE / "prompts/seeds.txt").read_text().splitlines() if l[:2].isdigit()]
    brief, out = (HERE / "prompts/brief.txt").read_text(), []
    for i in range(0, len(seeds), 10):
        use = seeds[i:i + 10]
        for _ in range(6):
            txt = R.chat(R.GEN_MODEL, "You write evaluation scenarios.", brief.replace("{N}", str(len(use))) + "\n" + "\n".join(use) + "\n", max_tokens=12000, temperature=0.7)
            arr = R.jparse(txt)
            if not isinstance(arr, list):  # writer ignored JSON: "NN text" paragraphs
                bits = re.split(r"(?m)^(\d\d)[ \t]*\n?", txt)
                arr = [{"id": a, "prompt": " ".join(b.split())} for a, b in zip(bits[1::2], bits[2::2]) if b.strip()]
            if isinstance(arr, list) and len(arr) == len(use) and all(isinstance(x, dict) and "prompt" in x for x in arr):
                out += [{"id": "r2h" + u[:2], "prompt": x["prompt"]} for u, x in zip(use, arr)]
                break
        else:
            raise SystemExit(f"writer failed for seeds {i}")
    assert not SCEN.exists(), "never overwrite a record: " + str(SCEN)
    SCEN.write_text(json.dumps(out, indent=1) + "\n")
    print(len(out), R.sha(SCEN.read_bytes()))


def paired_boot(d, n=10000, seed=1):
    import random
    rng, m = random.Random(seed), len(d)
    bs = sorted(sum(d[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return bs[int(0.025 * n)], bs[int(0.975 * n) - 1]


def run(out):
    scs, out = json.loads(SCEN.read_text()), Path(out)
    texts = {"v0": (HERE / "frozen/contribution.v0.md").read_text(), "v1": (HERE / "frozen/contribution.v1.md").read_text(), "rival": (HERE / "frozen/rival.md").read_text()}
    outs, errs = {k: {} for k in texts}, []

    def gen(k, sc):
        p = out / "outputs" / k / f"{sc['id']}-{R.sha(sc['prompt'])[:8]}-{R.sha(texts[k])[:8]}.txt"
        if not p.exists():
            try:
                R.save(p, R.chat(R.GEN_MODEL, texts[k], R.GEN_TASK + sc["prompt"], temperature=0.3))
            except RuntimeError as e:
                return errs.append(f"gen {k}/{sc['id']}: {e}")
        outs[k][sc["id"]] = p.read_text()

    with cf.ThreadPoolExecutor(6) as ex:
        list(ex.map(lambda t: gen(*t), [(k, s) for k in texts for s in scs]))
    ok = [s for s in scs if all(s["id"] in outs[k] for k in texts)]
    res = dict(n_scenarios=len(scs), n_generated=len(ok), errors=errs, sha256={k: R.sha(v) for k, v in texts.items()}, judges={})
    for model in R.JUDGES:
        sc_scores, raw = {}, {}
        for arm in ("v0", "v1"):
            o = {"PERUN": outs[arm], "RIVAL": outs["rival"]}
            d = out / "judge" / arm
            def both(sc):
                return sc["id"], [R.judge_one(model, sc, a, b, d, o) for a, b in (R.ARMS, R.ARMS[::-1])]
            with cf.ThreadPoolExecutor(6) as ex:
                vs = dict(ex.map(both, ok))
            raw[arm] = vs
            sc_scores[arm] = {i: R.scenario_score([R.order_score(x, a) for x, a in zip(p, R.ARMS)]) for i, p in vs.items() if None not in p}
        rate = R.slot1_rate([x for arm in raw.values() for p in arm.values() for x in p])
        ids = sorted(set(sc_scores["v0"]) & set(sc_scores["v1"]))
        v0, v1 = [sc_scores["v0"][i] for i in ids], [sc_scores["v1"][i] for i in ids]
        diff = [b - a for a, b in zip(v0, v1)]
        r = dict(slot1=None if rate is None else round(rate, 3), healthy=rate is not None and R.SLOT1_OK[0] <= rate <= R.SLOT1_OK[1], n_scored=len(ids))
        if ids:
            r.update(win_v0=round(sum(v0) / len(v0), 3), ci_v0=[round(x, 3) for x in R.boot(v0)], win_v1=round(sum(v1) / len(v1), 3), ci_v1=[round(x, 3) for x in R.boot(v1)],
                     paired_diff=round(sum(diff) / len(diff), 3), ci_diff=[round(x, 3) for x in paired_boot(diff)],
                     strict_v1={"win": v1.count(1.0), "tie_or_split": v1.count(0.5), "loss": v1.count(0.0)})
        res["judges"][model] = r
        if r["healthy"] and "used" not in res:
            res["used"] = model
            res["keep"] = bool(r["n_scored"] >= 54 and r["ci_diff"][0] > 0)
            res["superior"] = bool(r["n_scored"] >= 54 and r["ci_v1"][0] > 0.5)
    (out / "verdict.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: v for k, v in res.items() if k != "sha256"}, indent=1))


def fold(out):
    """Keep every output file; fold the one-file-per-verdict judge caches into one json (file-count limit of the privacy gate)."""
    import shutil
    out, dest = Path(out), HERE / "results"
    shutil.copytree(out / "outputs", dest / "outputs")
    shutil.copy(out / "verdict.json", dest / "verdict.json")
    (dest / "judge-verdicts.json").write_text(json.dumps({str(p.relative_to(out / "judge")): json.loads(p.read_text())["verdict"]
                                                         for p in sorted((out / "judge").rglob("*.json"))}, indent=1) + "\n")


if __name__ == "__main__":
    {"write": lambda: write(), "run": lambda: run(sys.argv[2]), "fold": lambda: fold(sys.argv[2])}[sys.argv[1]]()
