#!/usr/bin/env python3
"""Round 2 driver (see PREREGISTERED-ADDENDUM-2.md). Reuses bench.py for calls, generation and bootstrap.
usage: bench2.py scen SKILL | run SKILL ARM SPLIT | report SKILL ARM SPLIT
SPLIT = tune (scenarios/<skill>.json ids 01-10) or h2 (scenarios2/<skill>-h2.json, 20 fresh scenarios, ids h01-h20).
Judges: DeepSeek-V4-Flash, GLM-5.2 (thinking off) and MiniMax-M2.5. Each judge sees every pair in BOTH orders (amendment 2a); its
verdict is an arm only if both orders agree, else a tie. The majority of the three judge verdicts decides (two judges on one arm;
anything else is a tie worth 0.5). Qwen is the generator, so it never judges. Records: judge4/, results4-*.json."""
import concurrent.futures as cf, json, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I drops the script dir; bench.py is our own sibling
import bench as b

D, P = b.D, b.P
MINI = "MiniMax-M2.5"
JUDGES = [(b.JUDGE, False), (b.TIE, True), (MINI, False)]


def load(skill, split):
    if split == "tune":
        return b.load(skill, "tune")
    return json.loads((D / "scenarios2" / f"{skill}-h2.json").read_text())


def scen(skill):
    out = D / "scenarios2" / f"{skill}-h2.json"
    if out.exists():
        return print("cached", out)
    seeds = (P / "seeds2.txt").read_text().strip().splitlines()
    r = 5 * b.SKILLS.index(skill)
    seeds = seeds[r:] + seeds[:r]
    sysm, brief = (P / "writer_common.txt").read_text(), (P / f"writer_{skill}.txt").read_text()

    def one(i):
        for _ in range(3):
            t = b.call(b.WRITER, sysm, f"{brief}\nSetting: {seeds[i]}\nWrite the scenario now.", f"scen2/{skill}/{i}", 4000, 0.9)
            if 100 <= len(t.split()) <= 280:
                return dict(id=f"h{i + 1:02d}", split="h2", setting=seeds[i], prompt=t)
        raise SystemExit(f"scenario {skill}/{i} failed word-count after 3 tries")

    with cf.ThreadPoolExecutor(b.JOBS) as ex:
        arr = list(ex.map(one, range(20)))
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(arr, indent=1) + "\n")


def one_judge(model, nothink, sc, first, second, tag, skill):
    a, c = (D / "outputs" / skill / x / f"{sc['id']}.txt" for x in (first, second))
    prompt = f"REQUEST:\n{sc['prompt']}\n\n=== Response 1 ===\n{a.read_text()}\n\n=== Response 2 ===\n{c.read_text()}\n"
    for _ in range(2):
        j = b.jparse(b.call(model, (P / "judge.txt").read_text(), prompt, tag, 600 if nothink or model == b.JUDGE else 1500, 0.0, no_think=nothink))
        if isinstance(j, dict) and j.get("verdict") in ("1", "2", "tie"):
            return dict(winner={"1": first, "2": second, "tie": "tie"}[j["verdict"]], slot=j["verdict"], reason=j.get("reason", ""))
    return None


def judge(skill, arm, sc):
    p = D / "judge4" / skill / arm / f"{sc['id']}.json"
    if p.exists() or not all((D / "outputs" / skill / x / f"{sc['id']}.txt").exists() for x in (arm, "RIVAL")):
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    votes, verdicts = {}, []
    for model, nt in JUDGES:
        o = [arm, "RIVAL"]
        random.Random(f"{skill}-{arm}-{sc['id']}-{model}").shuffle(o)
        r = [one_judge(model, nt, sc, x, y, f"judge4/{skill}/{arm}/{sc['id']}/{model}/{k}", skill) for k, (x, y) in enumerate((o, o[::-1]))]
        w = [x["winner"] if x else "fail" for x in r]
        v = w[0] if w[0] == w[1] and w[0] in (arm, "RIVAL") else "tie"
        votes[model] = dict(orders=r, verdict=v)
        verdicts.append(v)
    final = next((x for x in (arm, "RIVAL") if verdicts.count(x) >= 2), "tie")
    p.write_text(json.dumps(dict(votes=votes, final=final), indent=1) + "\n")


def report(skill, arm, split):
    per, recs = {}, []
    for sc in load(skill, split):
        p = D / "judge4" / skill / arm / f"{sc['id']}.json"
        if p.exists():
            recs.append(json.loads(p.read_text()))
            per[sc["id"]] = {arm: 1.0, "RIVAL": 0.0}.get(recs[-1]["final"], 0.5)
    v = list(per.values())
    res = dict(skill=skill, arm=arm, split=split, n=len(v), win_rate=round(sum(v) / len(v), 3) if v else None, per_scenario=per,
               judges="DeepSeek-V4-Flash + GLM-5.2 + MiniMax-M2.5 majority", bootstrap="10000 resamples, seed 1, percentile, over scenarios")
    if v:
        lo, hi = b.boot(v)
        res.update(ci95=[round(lo, 3), round(hi, 3)], verdict="PASS" if lo > 0.5 and len(v) >= 20 else "FAIL")
    slots = {m: [x["slot"] for r in recs for x in r["votes"][m]["orders"] if x] for m in (j for j, _ in JUDGES)}
    res["slot1_rate"] = {m: round(v.count("1") / len(v), 3) for m, v in slots.items() if v}
    (D / f"results4-{skill}-{arm}-{split}.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in res if k != "per_scenario"}))


def run(skill, arm, split):
    scs = load(skill, split)
    with cf.ThreadPoolExecutor(b.JOBS) as ex:
        list(ex.map(lambda t: b.gen(skill, *t), [(a, s) for a in (arm, "RIVAL") for s in scs]))
    with cf.ThreadPoolExecutor(b.JOBS) as ex:
        list(ex.map(lambda s: judge(skill, arm, s), scs))
    report(skill, arm, split)


if __name__ == "__main__":
    c, a = sys.argv[1], sys.argv[2:]
    {"scen": scen, "run": run, "report": report}[c](*a)
