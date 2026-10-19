#!/usr/bin/env python3
"""Outcome bench for idea-critic: does a skill's go/no-go call match what really happened? See README.md.
PCSS only (free); PCSS_ENV must point at a file holding PCSS_KEY (never printed). Reuses ../exec-1017/bench.py (PCSS call) and
scripts/rival_eval.py (bootstrap). An existing output is reused, a missing one is regenerated.
usage: bench_outcome.py check | run MODEL | report MODEL        (MODEL = PCSS model id, e.g. Qwen3.5-397B-A17B)"""
import concurrent.futures as cf, json, re, sys
from pathlib import Path

H = Path(__file__).resolve().parent
ROOT = H.parents[2]
sys.path[:0] = [str(H.parent / "exec-1017"), str(ROOT / "scripts")]
ARMS = {"PERUN": ROOT / ".claude/skills/idea-critic/SKILL.md", "RIVAL": H.parent / "exec-1017/prompts/rival_idea-critic.txt", "BASE": None}
REPS = 3
TASK = ("A proposal is below, brought to the executive team. You have no tools, no network and no files: use only the facts given. "
        "Keep your whole answer under 350 words and do not name which skills or frameworks you use. "
        "Your LAST line must be exactly `DECISION: GO` (approve as proposed, now) or `DECISION: NO-GO` (do not approve as proposed now; "
        "this includes 'revise first' and 'hold').\n\nPROPOSAL:\n")


def corpus():
    c = json.loads((H / "corpus.json").read_text(encoding="utf-8"))
    for x in c:
        assert x["key"] in ("good", "bad") and x["source_urls"] and x["evidence_quote"] and x["prompt"], x["id"]
        assert not any(n.lower() in x["prompt"].lower() for n in x["names"]), f"name leak in {x['id']}"
    return c


def parse(text):
    m = re.findall(r"DECISION:\s*\**\s*(NO-GO|GO)\b", text or "")
    return m[-1] if m else None


def right(x, d):  # invalid or missing decision counts as wrong for every arm
    return float(d == ("GO" if x["key"] == "good" else "NO-GO"))


def path(model, arm, cid, rep):
    return H / "outputs" / model / arm / f"{cid}.{rep}.txt"


def run(model):
    import bench as b
    b.D = H  # ledger.jsonl goes here, not into exec-1017
    jobs = [(a, x, r) for a in ARMS for x in corpus() for r in range(REPS) if not path(model, a, x["id"], r).exists()]
    think = model.startswith("gpt-oss")  # reasoning model: cannot disable thinking, needs a larger budget

    def one(j):
        a, x, r = j
        sysm = ARMS[a].read_text(encoding="utf-8") if ARMS[a] else ""
        t = b.call(model, sysm, TASK + x["prompt"], f"out/{model}/{a}/{x['id']}/{r}", 6000 if think else 3000, 0.7, not think)
        if t:
            p = path(model, a, x["id"], r)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(t, encoding="utf-8")
        else:
            print("GEN FAIL", model, a, x["id"], r)
    with cf.ThreadPoolExecutor(b.JOBS) as ex:
        list(ex.map(one, jobs))


def tokens(model):
    """{(arm, case, rep): (prompt, completion)} from the successful ledger line of each call."""
    t = {}
    for l in (H / "ledger.jsonl").read_text().splitlines():
        j = json.loads(l)
        p = j["tag"].split("/")
        if p[0] == "out" and p[1] == model and not j["err"]:
            t[(p[2], p[3], int(p[4]))] = (j["usage"].get("prompt_tokens", 0), j["usage"].get("completion_tokens", 0))
    return t


def report(model):
    from rival_eval import boot
    c, tk = corpus(), tokens(model)
    per, inv, tok = {}, {}, {}
    for a in ARMS:
        per[a], inv[a], tok[a] = {}, 0, []
        for x in c:
            ds = []
            for r in range(REPS):
                p = path(model, a, x["id"], r)
                d = parse(p.read_text(encoding="utf-8")) if p.exists() else None
                inv[a] += d is None
                ds.append(d)
                tok[a].append(tk.get((a, x["id"], r), (0, 0)))
            per[a][x["id"]] = dict(acc=sum(right(x, d) for d in ds) / REPS, go=sum(d == "GO" for d in ds) / REPS)
    ids = [x["id"] for x in c]
    bad, good = [x["id"] for x in c if x["key"] == "bad"], [x["id"] for x in c if x["key"] == "good"]

    def m(vals):
        lo, hi = boot(vals)
        return dict(mean=round(sum(vals) / len(vals), 3), ci95=[round(lo, 3), round(hi, 3)], n=len(vals))
    res = dict(model=model, n_cases=len(c), n_good=len(good), n_bad=len(bad), reps=REPS, arms={}, paired={})
    for a in ARMS:
        n = len(tok[a])
        res["arms"][a] = dict(accuracy=m([per[a][i]["acc"] for i in ids]), false_go_rate=m([per[a][i]["go"] for i in bad]),
                              false_no_go_rate=m([1 - per[a][i]["go"] for i in good]), invalid_decisions=inv[a], calls=n,
                              prompt_tokens_per_call=round(sum(p for p, _ in tok[a]) / n), completion_tokens_per_call=round(sum(q for _, q in tok[a]) / n))
    for o in ("RIVAL", "BASE"):
        res["paired"][f"PERUN_minus_{o}"] = dict(accuracy=m([per["PERUN"][i]["acc"] - per[o][i]["acc"] for i in ids]),
                                                 false_go_rate=m([per["PERUN"][i]["go"] - per[o][i]["go"] for i in bad]))
    (H / f"results-{model}.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"check": lambda *_: print(len(corpus()), "cases ok"), "run": run, "report": report}[sys.argv[1]](*sys.argv[2:])
