#!/usr/bin/env python3
"""business-ops candidate e, confirmatory test (PCSS only, $0). Procedure: PREREGISTERED.md. Derived from ../bizops-call-1017/bench.py.

  bench.py seeds        draw 150 fresh one-line settings (3 calls of 50)
  bench.py write        150 scenarios, ids c150-001..c150-150, from the harness writer brief
  bench.py check        no identical prompt and no 6-word-shingle overlap above 0.3 with any earlier business-ops set (every earlier round, including the
                        round this tests) or inside this set; no id clash
  bench.py run v0 e     generate (rival once, shared), judge with the first healthy cascade judge, write results/c150-<arm>.json
  bench.py paired       per-scenario (e - v0) bootstrap, write results/paired-c150-e.json
Every step appends an event (ts, event, hashes) to ledger.jsonl; ledger and records are never rewritten."""
import concurrent.futures as cf, hashlib, json, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent.parent / "scripts"))
import rival_eval as R

P, SK, N, JOBS = HERE / "prompts", "business-ops", 150, 6
OLD_SEEDS = [HERE.parent / "bizops-r4-1017/prior/seeds_business-ops-r3.txt", HERE.parent / "bizops-r4-1017/prompts/seeds_business-ops.txt",
             HERE.parent / "bizops-call-1017/prompts/seeds_business-ops.txt"]
SEED_ASK = ("Write {n} distinct one-line settings for test scenarios, one per line, numbered 01 to {n}, same style as the examples. "
            "Each names a fictional-style product, who buys it and one tension. Cover many different industries and company sizes; "
            "avoid the example industries. About half should hinge on a legal, tax, accounting or regulatory question, the rest on pricing, "
            "unit economics, runway, market sizing or fundraising.\n\nTopic: {topic}\n\nExamples (do not reuse):\n{ex}\n")
TOPIC = "a founder or operator with a money or compliance question on taking a product to market (pricing, unit economics, runway, market sizing, legal, tax, fundraising)"
SCEN, SEEDS = HERE / "scenarios" / f"{SK}-c150.json", P / f"seeds_{SK}.txt"


def led(event, **kw):
    with open(HERE / "ledger.jsonl", "a") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **kw}) + "\n")


def fsha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def seeds():
    assert not SEEDS.exists(), "seeds are frozen"
    ex = "\n".join((R.FIX / SK / "seeds.txt").read_text().splitlines()[:5])
    strip = lambda l: re.sub(r"^\s*\d+[.)]?\s*", "", l).strip()
    used = [strip(l) for fn in OLD_SEEDS for l in fn.read_text().splitlines() if l.strip()]
    got = []
    for _ in range(3):
        for _try in range(2):  # one whole redraw per call
            txt = R.chat(R.GEN_MODEL, "You write evaluation settings.", SEED_ASK.format(n=50, topic=TOPIC, ex=ex) + "\nAlready used, do not repeat any of these products or industries:\n" + "\n".join(used + got) + "\n", max_tokens=12000, temperature=0.9)
            lines = [strip(l) for l in txt.splitlines() if re.match(r"\s*\d+", l)]
            if len(lines) == 50 and len(set(lines) | set(got)) == len(got) + 50:
                got += lines
                break
        else:
            raise SystemExit("seed writer failed twice")
    SEEDS.write_text("".join(f"{i % 10 + 1:02d} {l}\n" for i, l in enumerate(got)))
    led("seeds_drawn", file=str(SEEDS.relative_to(HERE)), sha256=fsha(SEEDS), n=len(got))


def write():
    assert not SCEN.exists(), "scenarios are frozen"
    seeds_ = SEEDS.read_text().splitlines()
    brief, out = (R.FIX / SK / "brief.txt").read_text(), []
    for i in range(0, N, 10):
        use = seeds_[i:i + 10]
        for _ in range(12):
            txt = R.chat(R.GEN_MODEL, "You write evaluation scenarios.", brief.replace("{N}", str(len(use))) + "\n" + "\n".join(use) + "\n", max_tokens=12000, temperature=0.7)
            arr = R.jparse(txt)
            if not isinstance(arr, list):  # writer sometimes answers "NN" then the text, no JSON
                bits = re.split(r"(?m)^(\d\d)[ \t]*\n?", txt)
                arr = [{"id": i, "prompt": " ".join(b.split())} for i, b in zip(bits[1::2], bits[2::2]) if b.strip()]
            if isinstance(arr, list) and len(arr) == len(use) and all(isinstance(x, dict) and "prompt" in x for x in arr):
                out += [{"id": f"c150-{i + k + 1:03d}", "setting": u, "prompt": x["prompt"]} for k, (u, x) in enumerate(zip(use, arr))]
                break
        else:
            raise SystemExit(f"writer failed on batch {i}")
    SCEN.parent.mkdir(exist_ok=True)
    SCEN.write_text(json.dumps(out, indent=1) + "\n")


def scen():
    return json.loads(SCEN.read_text())


def check():
    files = list((R.FIX / SK).glob("*.json")) + list(HERE.parent.glob(f"**/*{SK}*.json")) + list(HERE.parent.glob("**/scenarios*/*business*.json"))
    old = [x for f in set(files) if f.name != "rival.json" and "bizops-e-confirm" not in str(f) and f.read_text().lstrip().startswith("[")
           for x in json.loads(f.read_text()) if isinstance(x, dict) and "prompt" in x]
    pool, bad = [(R.shingles(x["prompt"]), R.norm(x["prompt"])) for x in old], []
    ids = {x.get("id") for x in old}
    for x in scen():
        sh, n = R.shingles(x["prompt"]), R.norm(x["prompt"])
        if x["id"] in ids:
            bad.append(f"{x['id']} id clash")
        if any(n == m or len(sh & s) / max(1, min(len(sh), len(s))) > 0.3 for s, m in pool):
            bad.append(f"{x['id']} overlaps an earlier set or this one")
        pool.append((sh, n))
    print(SK, len(scen()), f"vs {len(old)} earlier prompts:", "BAD: " + "; ".join(bad) if bad else "clean")
    return not bad


def gen(arm, sc):
    p = HERE / "outputs" / arm / f"{sc['id']}.txt"
    if not p.exists():
        R.save(p, R.chat(R.GEN_MODEL, (P / (f"rival_{SK}.txt" if arm == "RIVAL" else f"perun_{SK}_{arm}.txt")).read_text(), R.GEN_TASK + sc["prompt"], temperature=0.3))
    return p.read_text()


def outhash(arms):
    return {a: hashlib.sha256("".join((HERE / "outputs" / a / f"{s['id']}.txt").read_text() for s in scen()).encode()).hexdigest() for a in arms}


def run(*arms):
    scs = scen()
    with cf.ThreadPoolExecutor(JOBS) as ex:
        list(ex.map(lambda t: gen(*t), [(a, s) for a in ("RIVAL", *arms) for s in scs]))
    outs = {a: {s["id"]: gen(a, s) for s in scs} for a in ("RIVAL", *arms)}
    led("gen", arms=["RIVAL", *arms], n=len(scs), outputs_sha256=outhash(("RIVAL", *arms)))
    health, used, vs = {}, None, {}
    for model in R.JUDGES:
        def both(t, model=model):
            a, sc = t
            o = {"PERUN": outs[a], "RIVAL": outs["RIVAL"]}
            return (a, sc["id"]), [R.judge_one(model, sc, x, y, HERE / "judge" / a, o) for x, y in (("PERUN", "RIVAL"), ("RIVAL", "PERUN"))]
        with cf.ThreadPoolExecutor(JOBS) as ex:
            vs = dict(ex.map(both, [(a, s) for a in arms for s in scs]))
        rate = R.slot1_rate([x for pair in vs.values() for x in pair])
        health[model] = None if rate is None else round(rate, 3)
        if rate is not None and R.SLOT1_OK[0] <= rate <= R.SLOT1_OK[1]:
            used = model
            break
    if used is None:
        led("judge", status="no healthy judge", health=health)
        raise SystemExit(f"no healthy judge {health}: no verdict")
    (HERE / "results").mkdir(exist_ok=True)
    for a in arms:
        f, per, failed = HERE / "results" / f"c150-{a}.json", {}, 0
        assert not f.exists(), f"{f} exists: records are never overwritten"
        for s in scs:
            pair = vs[(a, s["id"])]
            failed += None in pair
            per[s["id"]] = 0.5 if None in pair else R.scenario_score([R.order_score(x, o) for x, o in zip(pair, ("PERUN", "RIVAL"))])
        v = list(per.values())
        lo, hi = R.boot(v)
        res = dict(skill=SK, arm=a, split="c150", n=len(v), judge=used, slot1_rate=health, win_rate=round(sum(v) / len(v), 3), ci95=[round(lo, 3), round(hi, 3)],
                   wins=v.count(1.0), ties=v.count(0.5), losses=v.count(0.0), failed_judge_orders=failed, per_scenario=per,
                   bootstrap="10000 resamples, seed 1, percentile, over scenarios")
        f.write_text(json.dumps(res, indent=1) + "\n")
        led("judge", arm=a, judge=used, result_sha256=fsha(f), win_rate=res["win_rate"], failed_judge_orders=failed)
        print(json.dumps({k: res[k] for k in res if k != "per_scenario"}))


def paired():
    a, b = (json.loads((HERE / "results" / f"c150-{x}.json").read_text()) for x in ("e", "v0"))
    assert a["judge"] == b["judge"] and a["per_scenario"].keys() == b["per_scenario"].keys()
    d = [a["per_scenario"][k] - b["per_scenario"][k] for k in a["per_scenario"]]
    lo, hi = R.boot(d)
    res = dict(split="c150", edit="e", n=len(d), judge=a["judge"], paired_diff=round(sum(d) / len(d), 3), ci95=[round(lo, 3), round(hi, 3)],
               edit_win_rate=a["win_rate"], edit_ci95=a["ci95"], v0_win_rate=b["win_rate"], v0_ci95=b["ci95"],
               ship=bool(lo > 0), superior=bool(a["ci95"][0] > 0.5))
    f = HERE / "results" / "paired-c150-e.json"
    assert not f.exists(), f"{f} exists: records are never overwritten"
    f.write_text(json.dumps(res, indent=1) + "\n")
    led("paired", result_sha256=fsha(f), **{k: res[k] for k in ("paired_diff", "ci95", "ship", "superior")})
    print(json.dumps(res))


if __name__ == "__main__":
    c, a = sys.argv[1], sys.argv[2:]
    {"seeds": seeds, "write": write, "check": check, "run": run, "paired": paired}[c](*a)
