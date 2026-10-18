#!/usr/bin/env python3
"""Replication driver, idea-critic only (see PREREGISTERED.md). Derived from ../idea-critic-r9-1018/bench9.py with the tune stage, the v0 arm and the paired test removed; reuses ../exec-1017/bench.py (PCSS call, bootstrap, JSON parse).
PCSS only; PCSS_ENV must point at a file holding PCSS_KEY (never printed). Records are never overwritten: a judge record is written only when all six calls parsed, a
generation only when absent. BANLIST points the privacy gate at a banlist whose sibling .banlist.local.txt it reads in place.
usage: bench9.py seeds | scen | check | rival | run | decide
HELD (n=150): fresh scenarios rp-001.., ids/names/texts disjoint and 6-word shingle overlap <= 0.10 (unrounded) with every docs/bench text (this directory excluded)."""
import concurrent.futures as cf, glob, hashlib, json, os, random, re, subprocess, sys, tempfile
from pathlib import Path

H = Path(__file__).resolve().parent
X = H.parent / "exec-1017"
sys.path.insert(0, str(X))
import bench as b

ROOT = H.parents[2]
BAN = os.environ.get("BANLIST", str(ROOT / ".banlist.txt"))
JUDGES = [("GLM-5.1", True), ("GLM-5.2", True), ("gpt-oss_120b", False)]  # (model, thinking off); the generator Qwen3.5-397B-A17B never judges
SK, JP, NHELD, MAXOV, ARM = "idea-critic", "v2", 150, 0.10, "SHIPPED"
b.D = H


def load():
    return json.loads((H / "scenarios-held.json").read_text())


def out(arm, s):
    return H / "outputs" / "held" / arm / f"{s['id']}.txt"


def rec(arm, s):
    return H / "judge" / JP / "held" / arm / f"{s['id']}.json"


def clean(text):
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "s.txt").write_text(text)
        return subprocess.run(["bash", str(ROOT / "scripts/ci-gates.sh"), "privacy", "--banlist", BAN, d], capture_output=True).returncode == 0


def words(t):
    return re.findall(r"\w+", t.lower())


def grams(w, k=6):
    return zip(*[w[i:] for i in range(k)])


def strings(x):
    return [x] if isinstance(x, str) else [s for v in (x.values() if isinstance(x, dict) else x if isinstance(x, list) else []) for s in strings(v)]


def corpus():
    """Every text file the round could collide with: docs/bench outside this directory, eval fixtures, idea-critic evals (JSON read as its decoded strings)."""
    roots = (H.parent, ROOT / "scripts" / "eval-fixtures", ROOT / ".claude" / "skills" / "idea-critic" / "evals")
    for f in sorted(g for r in roots for g in glob.glob(str(r / "**" / "*"), recursive=True)):
        p = Path(f)
        if not p.is_file() or H in p.parents or p.suffix not in (".json", ".md", ".txt", ".jsonl", ".py", ".tsv"):
            continue
        t = p.read_text(errors="ignore")
        if p.suffix == ".json":
            try:
                t = "\n".join(strings(json.loads(t)))
            except ValueError:
                pass
        yield t


def overlaps(texts):
    """Per text: share of its 6-word shingles found anywhere in the corpus (unrounded), plus the worst pairwise share inside the batch."""
    m = {}
    for i, t in enumerate(texts):
        for g in set(grams(words(t))):
            m.setdefault(g, set()).add(i)
    hit = [set() for _ in texts]
    for t in corpus():
        for g in grams(words(t)):
            if g in m:
                for i in m[g]:
                    hit[i].add(g)
    n = [len(set(grams(words(t)))) or 1 for t in texts]
    pair = [max([len({g for g in set(grams(words(t))) if i in m[g] and j in m[g]}) / n[i] for j in range(len(texts)) if j != i] or [0]) for i, t in enumerate(texts)]
    return [len(h) / k for h, k in zip(hit, n)], pair


def seeds():
    f = H / "prompts" / "seeds.txt"
    assert not f.exists(), "seeds already frozen"
    old = "\n".join(corpus())
    got, tries = [], 0
    while len(got) < NHELD and tries < 24:
        tries += 1
        t = b.call(b.WRITER, "You invent fictional business settings for test scenarios.",
                   "List 40 varied, distinct settings, one per line, each exactly: a short description of an organisation weighing a plan, then an invented, unusual two-word "
                   "company name in parentheses, e.g. 'a regional freight broker building an in-house load-matching app (Quillfeather Logistics)'. Mix industries, sizes and "
                   f"countries; no real brands, no markdown, no numbering. Batch {tries}.", f"seeds/{tries}", 4000, 0.9)
        for ln in t.splitlines():
            m = re.search(r"\(([A-Z][\w'&-]+(?: [A-Z][\w'&-]+)+)\)\s*$", ln.strip())
            if m and m.group(1).lower() not in old.lower() and not any(m.group(1) in g for g in got) and clean(ln):
                got.append(ln.strip())
    assert len(got) >= NHELD, f"only {len(got)} seeds"
    f.write_text("\n".join(got[:NHELD]) + "\n")


VOICE = ["an email you are drafting to a colleague", "a chat message", "a short memo-style note", "a voice note typed out", "rough notes written as flowing prose",
         "a message sent the night before the meeting", "a forwarded question with your own context added"]
ASK = ["ask whether you should take it forward, where it is weakest, and what early sign should end it",
       "ask for a straight call, the holes in it, and the point at which you should pull the plug",
       "ask the assistant to play devil's advocate and say what would change your mind",
       "ask what could sink it, whether there is a smarter way in, and a clear condition for walking away",
       "ask for a verdict you can defend out loud, the main risks, and the tripwire for stopping",
       "ask the assistant to pressure-test it and tell you the first thing you would watch that says stop",
       "ask what you are not seeing, what you would do instead, and what outcome should make you back out"]


def scen():
    """150 held-out scenarios by the writer model, a different voice and phrasing of the ask per scenario (drawn from a fixed RNG) so the shared template tail of earlier
    rounds is not reused; a scenario is kept only when its 6-word shingle overlap with the corpus and with the rest of the batch is <= MAXOV (unrounded)."""
    f = H / "scenarios-held.json"
    if f.exists():
        return print("cached", f)
    sd = (H / "prompts" / "seeds.txt").read_text().strip().splitlines()
    sysm, brief = (X / "prompts" / "writer_common.txt").read_text(), (X / "prompts" / f"writer_{SK}.txt").read_text()
    pf = H / "scen-progress.json"  # kept scenarios survive a failed run, so a resumed run redraws only the rest
    got = {int(k): v for k, v in json.loads(pf.read_text()).items()} if pf.exists() else {}

    def one(i, att):
        r = random.Random(f"rep-{i}")
        extra = (f"Write it as {r.choice(VOICE)}. In your own words, {r.choice(ASK)}. Use fresh wording throughout; avoid stock phrases such as 'pre-agreed', "
                 "'biggest ways', 'I need your help stress-testing', 'one clear recommendation'.")
        t = b.call(b.WRITER, sysm, f"{brief}\n{extra}\nSetting: {sd[i]}\nWrite the scenario now.", f"scen/{i}/{att}", 4000, 0.95)
        return t if 100 <= len(t.split()) <= 280 and clean(t) else None

    for att in range(40):  # round 9 used range(10); the corpus has grown, so more redraw rounds are needed to reach NHELD under the same <= MAXOV rule
        todo = [i for i in range(NHELD) if i not in got]
        if not todo:
            break
        with cf.ThreadPoolExecutor(b.JOBS) as ex:
            new = dict(zip(todo, ex.map(lambda i: one(i, att), todo)))
        cand = {**got, **{i: t for i, t in new.items() if t}}
        ids = sorted(cand)
        ov, pair = overlaps([cand[i] for i in ids])
        got = {i: cand[i] for i, o, p in zip(ids, ov, pair) if o <= MAXOV and p <= MAXOV}
        pf.write_text(json.dumps(got))
        print(f"round {att}: kept {len(got)}/{NHELD}; worst overlap {max(ov):.3f}")
    assert len(got) == NHELD, f"only {len(got)} scenarios passed"
    f.write_text(json.dumps([dict(id=f"rp-{i + 1:03d}", split="held", setting=sd[i], prompt=got[i]) for i in range(NHELD)], indent=1) + "\n")


def check():
    """Final disjointness of the held set: ids, company names, exact texts, 6-word shingles (corpus and batch, unrounded <= MAXOV)."""
    s = load()
    corp = "\n".join(corpus())
    bad = [x["id"] for x in s if f'"{x["id"]}"' in corp or re.search(r"\(([^)]+)\)\s*$", x["setting"]).group(1).lower() in corp.lower() or x["prompt"] in corp]
    ov, pair = overlaps([x["prompt"] for x in s])
    bad += [x["id"] for x, o, p in zip(s, ov, pair) if o > MAXOV or p > MAXOV]
    print(f"held {len(s)}; max corpus overlap {max(ov):.4f}, max in-batch overlap {max(pair):.4f}; offenders {bad or 'none'}")
    assert not bad and len({x['id'] for x in s}) == len(s)


def gen(arm, s):
    p = out(arm, s)
    if p.exists():
        return
    f = X / "prompts" / f"rival_{SK}.txt" if arm == "RIVAL" else H / "prompts" / f"perun_{SK}_{arm}.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    t = b.call(b.GEN, f.read_text(), (X / "prompts" / "gen_task.txt").read_text() + s["prompt"], f"gen/{arm}/{s['id']}", 3000, 0.7, True)
    p.write_text(t) if t else print("GEN FAIL", arm, s["id"])


def sha():
    return {s["id"]: hashlib.sha256(out("RIVAL", s).read_bytes()).hexdigest() for s in load()}


def rival():
    with cf.ThreadPoolExecutor(b.JOBS) as ex:
        list(ex.map(lambda s: gen("RIVAL", s), load()))
    f = H / "RIVAL-sha256-held.json"
    assert not f.exists(), "RIVAL already frozen"
    f.write_text(json.dumps(sha(), indent=1) + "\n")


def one(model, nothink, s, first, second, tag):
    prompt = f"REQUEST:\n{s['prompt']}\n\n=== Response 1 ===\n{out(first, s).read_text()}\n\n=== Response 2 ===\n{out(second, s).read_text()}\n"
    for _ in range(2):
        j = b.jparse(b.call(model, (H / "prompts" / f"judge_{JP}.txt").read_text(), prompt, tag, 2500, 0.0, no_think=nothink))
        if isinstance(j, dict) and j.get("verdict") in ("1", "2", "tie"):
            return dict(winner={"1": first, "2": second, "tie": "tie"}[j["verdict"]], slot=j["verdict"], reason=j.get("reason", ""))
    return None


def judge(arm, s):
    p = rec(arm, s)
    if p.exists() or not out(arm, s).exists():
        return
    votes, verdicts = {}, []
    for model, nt in JUDGES:
        o = [arm, "RIVAL"]
        random.Random(f"{JP}-{arm}-{s['id']}-{model}").shuffle(o)
        r = [one(model, nt, s, x, y, f"judge/{arm}/{s['id']}/{model}/{k}") for k, (x, y) in enumerate((o, o[::-1]))]
        w = [x["winner"] if x else "fail" for x in r]
        v = w[0] if w[0] == w[1] and w[0] in (arm, "RIVAL") else "tie"
        votes[model] = dict(orders=r, verdict=v)
        verdicts.append(v)
    if any(x is None for v in votes.values() for x in v["orders"]):
        return print("INCOMPLETE (not written; rerun)", arm, s["id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "x") as f:  # 'x': never overwrite a complete record
        f.write(json.dumps(dict(votes=votes, final=next((x for x in (arm, "RIVAL") if verdicts.count(x) >= 2), "tie")), indent=1) + "\n")


def run():
    f = H / "RIVAL-sha256-held.json"
    assert f.exists() and json.loads(f.read_text()) == sha(), "RIVAL files missing or changed since frozen"
    scs = load()
    with cf.ThreadPoolExecutor(b.JOBS) as ex:
        list(ex.map(lambda s: gen(ARM, s), scs))
        list(ex.map(lambda s: judge(ARM, s), scs))
    print("done; run decide")


def decide():
    """Decision per PREREGISTERED.md section 3: win replicated iff the 95% bootstrap lower bound of the SHIPPED-vs-rival score is above 0.5."""
    per, recs = {}, []
    for s in load():
        p = rec(ARM, s)
        if p.exists():
            recs.append(json.loads(p.read_text()))
            per[s["id"]] = {ARM: 1.0, "RIVAL": 0.0}.get(recs[-1]["final"], 0.5)
    v = list(per.values())
    cells = [m["orders"] for r in recs for m in r["votes"].values()]
    dis = sum(1 for o in cells if o[0]["winner"] != o[1]["winner"])
    lo, hi = b.boot(v)
    res = dict(arm=ARM, split="held", judge_prompt=JP, n=len(v), win_rate=round(sum(v) / len(v), 3), wins_ties_losses=[v.count(1.0), v.count(0.5), v.count(0.0)],
               order_disagree_rate=round(dis / len(cells), 3), ci95=[round(lo, 3), round(hi, 3)], judges=[m for m, _ in JUDGES],
               bootstrap="10000 resamples, seed 1, percentile, over scenarios", replicated=lo > 0.5 and len(v) == NHELD, per_scenario=per)
    (H / "results-held-v2.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps({k: res[k] for k in res if k != "per_scenario"}))


if __name__ == "__main__":
    {"seeds": seeds, "scen": scen, "check": check, "rival": rival, "run": run, "decide": decide}[sys.argv[1]]()
