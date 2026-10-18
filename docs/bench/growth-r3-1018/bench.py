#!/usr/bin/env python3
"""Preregistered paired test of a one-edit growth-analytics skill (v1) against its text on origin/main (v0) and the H1 rival.
PCSS only ($0), no claude -p. Reuses scripts/rival_eval.py unchanged (generator, v2 judge in both orders, slot-1 gate, bootstrap).

  bench.py seeds SPLIT        draw fresh seeds (SPLIT = tune | heldout), rejecting any close to an existing bench seed
  bench.py scenarios SPLIT    write scenarios from the seeds with the blind writer; reject any that overlap the docs/bench corpus
  bench.py sha NAME           write SHA256-NAME.txt (prereg: before held-out seeds; frozen: before any held-out answer)
  bench.py prereg             append the ledger.jsonl "preregistered" event (sha256 of SHA256-frozen.txt)
  bench.py tune CAND.md       tuning run on the tune set: v0 and CAND against the rival; logged to ledger-tune.jsonl only
  bench.py run OUT            held-out run: v0, v1, rival; raw files go under OUT; verdict.json is the decision
  bench.py fold OUT           copy OUT outputs into results/ and fold the judge caches into results/judge-verdicts.json
The rival's answer to each scenario is generated once and shared by both skill arms, so (v1 - v0) is a paired difference.
The decision rule is in PREREGISTERED.md and is computed here from the outputs.
"""
import concurrent.futures as cf, json, os, random, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import rival_eval as R

BRIEF = ROOT / "docs/bench/growth-analytics-rubricfree-1016/prompts/writer_brief.txt"
RIVAL = ROOT / "docs/bench/growth-analytics-rubricfree-1016/prompts/rival.txt"
V0, V1 = HERE / "frozen/growth-analytics.v0.md", HERE / "frozen/growth-analytics.v1.md"
SPLITS = {"tune": (60, "gv", "scenarios-tune.json"), "heldout": (150, "gx", "scenarios-heldout.json")}  # (n, id prefix, file)
TOPIC = "a product manager, growth lead or analyst deciding what to measure (North Star metric, funnel, event list) or how to read an experiment for a product"
MAX_OVERLAP = 0.10


def words(t):
    return set(re.findall(r"[a-z]{3,}", t.lower()))


def near(seed, others, thr=0.5):
    a = words(seed)
    return any(len(a & words(o)) / max(1, min(len(a), len(words(o)))) > thr for o in others)


def seed_lines(p):
    return [re.sub(r"^\d+\s+", "", l) for l in p.read_text().splitlines() if re.match(r"\d{2,3} ", l)]


def corpus_shingles(extra=()):
    """6-word shingles of every text file under docs/bench (outputs, judge records, run records and this dir excluded) plus the rival fixtures."""
    out = set()
    for p in (ROOT / "docs/bench").rglob("*"):
        if p.is_file() and p.suffix in (".json", ".txt", ".md", ".py", ".jsonl") and not {"outputs", "judge", "run"} & set(p.parts) \
                and HERE not in p.parents and p.stat().st_size < 4_000_000:
            out |= R.shingles(p.read_text(errors="ignore").replace("\\n", " "))
    for p in list((ROOT / "scripts/eval-fixtures/rival").rglob("*.json")) + list((ROOT / "scripts/eval-fixtures/rival").rglob("*.txt")):
        out |= R.shingles(p.read_text(errors="ignore").replace("\\n", " "))
    for p in extra:
        out |= R.shingles(" ".join(x["prompt"] for x in json.loads(p.read_text())))
    return out


def overlap(prompt, sh):
    s = R.shingles(prompt)
    return len(s & sh) / max(1, len(s))


def seeds(split):
    n = SPLITS[split][0]
    p = HERE / "prompts" / f"seeds-{split}.txt"
    assert not p.exists(), "never overwrite a record: " + str(p)
    old = [re.sub(r"^\d+\s+", "", l) for q in (ROOT / "docs/bench").rglob("seeds*.txt") for l in q.read_text().splitlines() if re.match(r"\d{2,3} ", l)]
    mine, keep = seed_lines(ROOT / "docs/bench/growth-analytics-rubricfree-1016/prompts/seeds.txt"), []
    for _ in range(8):
        txt = R.chat(R.GEN_MODEL, "You write evaluation scenario seeds.", (
            f"Write 80 one-line seeds, one per line, no numbering, no commentary. Each seed is a distinct work situation about {TOPIC}. "
            "Vary industry, company size, stage, team size, constraint and country; fictional only. Each is 8 to 20 words, plain text. "
            "Do not repeat any of these:\n" + "\n".join(mine[:30])), max_tokens=6000, temperature=0.9)
        for l in txt.splitlines():
            l = re.sub(r"^[\s\-*\d.)]+", "", l).strip()
            if 5 <= len(l.split()) <= 30 and not near(l, old + keep):
                keep.append(l)
        if len(keep) >= n:
            break
    assert len(keep) >= n, f"only {len(keep)} seeds"
    p.parent.mkdir(exist_ok=True)
    p.write_text("\n".join(f"{i:03d} {l}" for i, l in enumerate(keep[:n], 1)) + "\n")
    if split.startswith("tune"):
        event("ledger-tune.jsonl", event="tune_seeds", sha256=R.sha(p.read_bytes()))
    print(split, "seeds", n)


def as_list(txt):
    arr = R.jparse(txt)
    if isinstance(arr, dict):
        arr = next(iter(arr.values())) if len(arr) == 1 and isinstance(next(iter(arr.values())), list) else [arr]
    if not isinstance(arr, list):  # writer ignored JSON: "NN" header lines plus prose
        bits = re.split(r"(?m)^(\d{2,3})[ \t]*$", txt)
        arr = [{"id": i, "prompt": b.strip()} for i, b in zip(bits[1::2], bits[2::2]) if b.strip()]
    return arr


def write_batch(prefix, brief, batch, sh):
    """Scenarios for the seeds in batch. A scenario that fails the length or overlap check is rewritten alone; accepted ones are kept
    (round 3: the all-or-nothing batch of rounds 1 and 2 never finished against the grown docs/bench corpus)."""
    done = {}
    for _ in range(16):
        todo = [b for b in batch if b not in done]
        txt = R.chat(R.GEN_MODEL, "You write evaluation scenarios.", brief.replace("{N}", str(len(todo))) + "\n" + "\n".join(todo) + "\n", max_tokens=12000, temperature=0.7)
        arr = as_list(txt)
        if not (isinstance(arr, list) and len(arr) == len(todo) and all(isinstance(x, dict) and isinstance(x.get("prompt"), str) for x in arr)):
            print(f"{batch[0].split()[0]}: unusable writer output", flush=True)
            continue
        for b, x in zip(todo, arr):
            if 70 <= len(x["prompt"].split()) <= 260 and overlap(x["prompt"], sh) <= MAX_OVERLAP:
                done[b] = {"id": prefix + b.split()[0], "prompt": x["prompt"]}
        if len(done) == len(batch):
            return [done[b] for b in batch]
        print(f"{batch[0].split()[0]}: {len(batch) - len(done)} of {len(batch)} still rejected", flush=True)
    raise SystemExit(f"batch starting {batch[0].split()[0]} failed after 16 tries")


def scenarios(split):
    n, prefix, name = SPLITS[split]
    out = HERE / name
    assert not out.exists(), "never overwrite a record: " + str(out)
    sh = corpus_shingles([HERE / SPLITS[t][2] for t in ("tune",) if (HERE / SPLITS[t][2]).exists() and t != split])
    brief = re.sub(r"\b10\b", "{N}", BRIEF.read_text())
    lines = (HERE / "prompts" / f"seeds-{split}.txt").read_text().splitlines()
    with cf.ThreadPoolExecutor(3) as ex:
        got = [x for b in ex.map(lambda i: write_batch(prefix, brief, lines[i:i + 10], sh), range(0, len(lines), 10)) for x in b]
    seen = set()
    for i, x in enumerate(got):  # no scenario may echo an earlier new one: rewrite the offender alone
        if overlap(x["prompt"], seen) > MAX_OVERLAP:
            got[i] = write_batch(prefix, brief, lines[i:i + 1], sh | seen)[0]
        seen |= R.shingles(got[i]["prompt"])
    assert len(got) == n and len({R.norm(x["prompt"]) for x in got}) == n
    out.write_text(json.dumps(got, indent=1) + "\n")
    if split.startswith("tune"):
        event("ledger-tune.jsonl", event="tune_scenarios", sha256=R.sha(out.read_bytes()))
    print(split, "scenarios", n, R.sha(out.read_bytes()))


def freeze_list():
    names = ["PREREGISTERED.md", "bench.py", "prompts/seeds-tune.txt", "prompts/seeds-heldout.txt", "scenarios-tune.json", "scenarios-heldout.json",
             "frozen/growth-analytics.v0.md", "frozen/growth-analytics.v1.md"]
    return [HERE / x for x in names if (HERE / x).is_file()] + [ROOT / "scripts/rival_eval.py", BRIEF, RIVAL]


def sha_file(name):
    lines = [f"{R.sha(p.read_bytes())}  {p.relative_to(ROOT)}" for p in freeze_list()]
    (HERE / f"SHA256-{name}.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def event(file, **kw):
    t = time.time()
    with (HERE / file).open("a") as f:
        f.write(json.dumps({"ts": int(t), "iso": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **kw}) + "\n")


def prereg():
    if (HERE / "ledger.jsonl").exists():
        raise SystemExit("ledger.jsonl exists; the preregistered event comes first, once")
    event("ledger.jsonl", event="preregistered", sha256_of="SHA256-frozen.txt", sha256=R.sha((HERE / "SHA256-frozen.txt").read_bytes()))


def paired_boot(d, n=10000, seed=1):
    rng, m = random.Random(seed), len(d)
    bs = sorted(sum(d[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return bs[int(0.025 * n)], bs[int(0.975 * n) - 1]


def evaluate(scs, texts, out, judges):
    """Generate every arm once per scenario (cached under out), judge each skill arm against the rival in both orders, per judge."""
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
    skill_arms = [k for k in texts if k != "rival"]
    for model in judges:
        sc_scores, raw = {}, {}
        for arm in skill_arms:
            o = {"PERUN": outs[arm], "RIVAL": outs["rival"]}
            d = out / "judge" / arm

            def both(sc):
                return sc["id"], [R.judge_one(model, sc, a, b, d, o) for a, b in (R.ARMS, R.ARMS[::-1])]
            with cf.ThreadPoolExecutor(6) as ex:
                vs = dict(ex.map(both, ok))
            raw[arm] = vs
            sc_scores[arm] = {i: R.scenario_score([R.order_score(x, a) for x, a in zip(p, R.ARMS)]) for i, p in vs.items() if None not in p}
        rate = R.slot1_rate([x for arm in raw.values() for p in arm.values() for x in p])
        ids = sorted(set.intersection(*[set(v) for v in sc_scores.values()]))
        r = dict(slot1=None if rate is None else round(rate, 3), healthy=rate is not None and R.SLOT1_OK[0] <= rate <= R.SLOT1_OK[1], n_scored=len(ids))
        if ids:
            vals = {a: [sc_scores[a][i] for i in ids] for a in skill_arms}
            for a in skill_arms:
                r[f"win_{a}"], r[f"ci_{a}"] = round(sum(vals[a]) / len(ids), 3), [round(x, 3) for x in R.boot(vals[a])]
                r[f"strict_{a}"] = {"win": vals[a].count(1.0), "tie_or_split": vals[a].count(0.5), "loss": vals[a].count(0.0)}
            diff = [b - a for a, b in zip(vals["v0"], vals["v1"])]
            r.update(paired_diff=round(sum(diff) / len(diff), 3), ci_diff=[round(x, 3) for x in paired_boot(diff)])
        res["judges"][model] = r
    return res


def tune(cand):
    scs = [x for t in ("tune",) if (HERE / SPLITS[t][2]).exists() for x in json.loads((HERE / SPLITS[t][2]).read_text())]
    texts = {"v0": V0.read_text(), "v1": Path(cand).read_text(), "rival": RIVAL.read_text()}
    out = Path(os.environ.get("TMPDIR", "/tmp")) / "growth-r3-tune"
    res = evaluate(scs, texts, out, (R.JUDGE_MODEL,))
    event("ledger-tune.jsonl", event="tune_run", cand_sha256=R.sha(texts["v1"]), bytes=len(texts["v1"].encode()), result=res["judges"][R.JUDGE_MODEL], errors=res["errors"])
    print(json.dumps(res["judges"][R.JUDGE_MODEL], indent=1))


def run(out):
    scs = json.loads((HERE / SPLITS["heldout"][2]).read_text())
    texts = {"v0": V0.read_text(), "v1": V1.read_text(), "rival": RIVAL.read_text()}
    event("ledger.jsonl", event="run_start", note="no held-out answer or judge call existed before this event")
    res = evaluate(scs, texts, Path(out), R.JUDGES)
    for model in R.JUDGES:
        r = res["judges"][model]
        if r["healthy"]:
            res["used"] = model
            res["keep"] = bool(r["n_scored"] >= 135 and r["ci_diff"][0] > 0)
            res["superior"] = bool(r["n_scored"] >= 135 and r["ci_v1"][0] > 0.5)
            break
    (Path(out) / "verdict.json").write_text(json.dumps(res, indent=1) + "\n")
    event("ledger.jsonl", event="results", sha256=R.sha((Path(out) / "verdict.json").read_bytes()), used=res.get("used"), keep=res.get("keep"), superior=res.get("superior"))
    print(json.dumps({k: v for k, v in res.items() if k != "sha256"}, indent=1))


def fold(out):
    import shutil
    out, dest = Path(out), HERE / "results"
    shutil.copytree(out / "outputs", dest / "outputs")
    shutil.copy(out / "verdict.json", dest / "verdict.json")
    (dest / "judge-verdicts.json").write_text(json.dumps({str(p.relative_to(out / "judge")): json.loads(p.read_text())["verdict"]
                                                         for p in sorted((out / "judge").rglob("*.json"))}, indent=1) + "\n")


if __name__ == "__main__":
    a = sys.argv
    {"seeds": lambda: seeds(a[2]), "scenarios": lambda: scenarios(a[2]), "sha": lambda: sha_file(a[2]), "prereg": prereg,
     "tune": lambda: tune(a[2]), "run": lambda: run(a[2]), "fold": lambda: fold(a[2])}[a[1]]()
