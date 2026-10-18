#!/usr/bin/env python3
"""Re-judge the v0-vs-rival pairs of the spent growth-r1 held-out set (GLM-5.1, protocol v2, both orders), keeping the judge's
analysis text, and write the reasons of every order the rival won to OUT.json. Cached verdicts of earlier runs hold no reasons.
usage: losses.py OUT.json  (run from the repo root; PCSS only)"""
import concurrent.futures as cf, json, sys
from pathlib import Path
sys.path.insert(0, "scripts")
import rival_eval as R

B = Path("docs/bench/growth-r1-1018")
scs = json.loads((B / "scenarios-heldout.json").read_text())
outs = {"PERUN": {}, "RIVAL": {}}
for s in scs:
    outs["PERUN"][s["id"]] = next((B / "results/outputs/v0").glob(s["id"] + "-*.txt")).read_text()
    outs["RIVAL"][s["id"]] = next((B / "results/outputs/rival").glob(s["id"] + "-*.txt")).read_text()


def one(args):
    sc, (a, b) = args
    x, y = R.labels(sc, outs[a][sc["id"]], outs[b][sc["id"]])
    user = f"REQUEST:\n{sc['prompt']}\n\n=== Response {x} ===\n{outs[a][sc['id']]}\n\n=== Response {y} ===\n{outs[b][sc['id']]}\n"
    txt = R.chat(R.JUDGE_MODEL, R.JUDGE_SYSTEM.format(a=x, b=y), user, max_tokens=3000)
    winner = {"1": a, "2": b}.get(R.parse_verdict(txt, x, y), "tie")
    return {"id": sc["id"], "order": f"{a}__{b}", "winner": winner, "analysis": txt}


jobs = [(s, o) for s in scs for o in (R.ARMS, R.ARMS[::-1])]
with cf.ThreadPoolExecutor(6) as ex:
    res = list(ex.map(one, jobs))
Path(sys.argv[1]).write_text(json.dumps([r for r in res if r["winner"] == "RIVAL"], indent=1))
print(len(res), "orders;", sum(r["winner"] == "RIVAL" for r in res), "rival wins;", sum(r["winner"] == "PERUN" for r in res), "perun wins")
