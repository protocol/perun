#!/usr/bin/env python3
"""product-output-safety round 2 (2026-10-18): tune up to three candidate edits of the shipped skill (prompts/v0.md) on a fresh tune set, freeze one,
then one held-out n=300 run of V0 and EDIT against the promptfoo redteam-setup rival (prompts/rival.txt). Judge protocol v2 of
scripts/rival_eval.py, unchanged. Generator Qwen3.5-397B-A17B, judge GLM-5.1 (fallbacks per rival_eval), both orders, bootstrap 10,000, seed 1.

usage: bench.py seeds SPLIT | scenarios SPLIT | sha NAME | prereg | late | run SPLIT [--jobs N]
  SPLIT      tune (n=100, ids sc4t001.., ledger-tune.jsonl, arms V0 E1 E2 E3 RIVAL) or held (n=300, ids sc4h001.., ledger.jsonl, arms V0 EDIT RIVAL)
  seeds      fresh seeds, none close to any earlier bench seed (nor the tune seeds, for held)
  scenarios  write them in batches of 10 from the skill's own writer brief; reject any scenario whose 6-word shingles overlap docs/bench (other
             dirs, and the tune scenarios for held) or each other by more than 10%
  sha NAME   write SHA256-NAME.txt over the freeze list
  prereg     first line of ledger.jsonl: event "preregistered" + sha256 of SHA256-frozen.txt; refuses if ledger.jsonl exists
  late       append held seeds and scenarios hashes to SHA256-frozen.txt and log event fixtures_frozen, before any held arm answer
  run SPLIT  generate every arm once per scenario, judge each non-rival arm against RIVAL, write <split>/results.json; refuses to overwrite
Needs PCSS_KEY (environment or repo .env; never printed).
"""
import argparse, concurrent.futures as cf, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import rival_eval as R  # noqa: E402

P = HERE / "prompts"
SPLITS = {  # n, id prefix, seeds file, scenarios file, ledger, arms
    "tune": dict(n=100, pre="sc4t", seeds="seeds-tune.txt", sc="scenarios-tune.json", ledger="ledger-tune.jsonl", arms=("V0", "E1", "E2", "E3", "RIVAL")),
    "held": dict(n=300, pre="sc4h", seeds="seeds.txt", sc="scenarios-heldout.json", ledger="ledger.jsonl", arms=("V0", "EDIT", "RIVAL")),
}
ARM_FILE = {"V0": "v0.md", "E1": "e1.md", "E2": "e2.md", "E3": "e3.md", "EDIT": "edit.md", "RIVAL": "rival.txt"}
MAX_OVERLAP, BATCH = 0.10, 10
TOPIC = "a product team making a feature safe before launch, where the feature's own AI outputs or automated decisions reach end users and could harm them"
FREEZE = ["PREREGISTERED.md", "bench.py", "prompts/v0.md", "prompts/edit.md", "prompts/rival.txt", "prompts/writer_brief.txt"]
LATE = ["seeds.txt", "scenarios-heldout.json"]  # written after the preregistered ledger line; hashed in a later ledger event
DIR = "docs/bench/safety-r2-1018"


def words(t):
    return set(re.findall(r"[a-z]{3,}", t.lower()))


def near(seed, others, thr=0.5):
    a = words(seed)
    return any(len(a & words(o)) / max(1, min(len(a), len(words(o)))) > thr for o in others)


def corpus(split):
    """6-word shingles of every text file under docs/bench (other dirs; raw outputs and judge records excluded), the rival fixtures, and for held the tune scenarios."""
    ps = [p for p in (ROOT / "docs/bench").rglob("*") if p.is_file() and p.suffix in (".json", ".txt", ".md", ".py", ".jsonl")
          and not {"outputs", "judge", "run"} & set(p.parts) and HERE not in p.parents and p.stat().st_size < 4_000_000]
    ps += list((ROOT / "scripts/eval-fixtures/rival").rglob("*.json")) + list((ROOT / "scripts/eval-fixtures/rival").rglob("*.txt"))
    if split == "held":
        ps.append(HERE / SPLITS["tune"]["sc"])
    out = set()
    for p in ps:
        out |= R.shingles(p.read_text(errors="ignore").replace("\\n", " "))
    return out


def overlap(prompt, sh):
    s = R.shingles(prompt)
    return len(s & sh) / max(1, len(s))


def seed_lines(p):
    return [re.sub(r"^\d+\s+", "", l) for l in p.read_text().splitlines() if re.match(r"\d\d\d? ", l)]


def old_seeds(split):
    out = []
    for p in list((ROOT / "docs/bench").rglob("seeds*.txt")) + list((ROOT / "scripts/eval-fixtures/rival").rglob("seeds.txt")):
        if HERE not in p.parents:
            out += seed_lines(p)
    if split == "held" and (HERE / SPLITS["tune"]["seeds"]).exists():
        out += seed_lines(HERE / SPLITS["tune"]["seeds"])
    return out


def seed_chat():
    mine = seed_lines(ROOT / "docs/bench/pos-1016/prompts/seeds_A.txt")
    txt = R.chat(R.GEN_MODEL, "You write evaluation scenario seeds.", (
        f"Write 80 one-line seeds, one per line, no numbering, no commentary. Each seed is a distinct work situation about {TOPIC}. "
        "Vary industry, company size, stage, team size, constraint and country; fictional only. Each is 8 to 20 words, plain text. "
        "Do not repeat any of these:\n" + "\n".join(mine[:30])), max_tokens=6000, temperature=0.9)
    return [re.sub(r"^[\s\-*\d.)]+", "", l).strip() for l in txt.splitlines()]


def seeds(split):
    c = SPLITS[split]
    old, keep = old_seeds(split), []
    for _ in range(80):
        for l in seed_chat():
            if 5 <= len(l.split()) <= 30 and not near(l, old + keep):
                keep.append(l)
        if len(keep) >= c["n"]:
            break
    assert len(keep) >= c["n"], f"only {len(keep)} seeds"
    (HERE / c["seeds"]).write_text("\n".join(f"{i:02d} {l}" for i, l in enumerate(keep[:c["n"]], 1)) + "\n")


def as_list(txt):
    try:  # the writer sometimes emits one JSON object per line instead of an array
        rows = [json.loads(l) for l in txt.strip().splitlines() if l.strip()]
        if len(rows) > 1 and all(isinstance(x, dict) and "prompt" in x for x in rows):
            return rows
    except ValueError:
        pass
    arr = R.jparse(txt)
    if isinstance(arr, dict):
        arr = next(iter(arr.values())) if len(arr) == 1 and isinstance(next(iter(arr.values())), list) else [arr]
    if not isinstance(arr, list):  # "NN" header lines plus prose
        bits = re.split(r"(?m)^(\d\d)[ \t]*$", txt)
        arr = [{"id": i, "prompt": b.strip()} for i, b in zip(bits[1::2], bits[2::2]) if b.strip()]
    if not arr:  # "NN: text" lines
        bits = re.split(r"(?m)^\s*(\d\d)[:.)]\s*", txt)
        arr = [{"id": i, "prompt": b.strip()} for i, b in zip(bits[1::2], bits[2::2]) if b.strip()]
    return arr


def write_batch(brief, batch, sh):
    """Per position, keep the first draw that passes the length and overlap checks; redraw the whole batch (so the brief's per-position
    pressure rule still holds) until every position is filled."""
    got = [None] * len(batch)
    for _ in range(25):
        arr = as_list(R.chat(R.GEN_MODEL, "You write evaluation scenarios.", brief.replace("{N}", str(len(batch))) + "\n" + "\n".join(batch) + "\n",
                             max_tokens=12000, temperature=0.7))
        if not (isinstance(arr, list) and len(arr) == len(batch) and all(isinstance(x, dict) and isinstance(x.get("prompt"), str) for x in arr)):
            print("unusable writer output", flush=True)
            continue
        for i, x in enumerate(arr):
            if got[i] is None and 70 <= len(x["prompt"].split()) <= 260 and overlap(x["prompt"], sh) <= MAX_OVERLAP:
                got[i] = x["prompt"]
        if None not in got:
            return got
    print(f"batch starting {batch[0][:2]}: {got.count(None)} position(s) stuck after 25 tries", flush=True)
    return got


def replace_seed(split, j, p, lines, avoid):
    """A seed whose scenarios always overlap the corpus is replaced by a fresh seed."""
    brief = (P / "writer_brief.txt").read_text()
    for _ in range(30):
        if p is not None:
            return p
        used = [re.sub(r"^\d+\s+", "", l) for l in lines]
        new = next((s for s in seed_chat() if 5 <= len(s.split()) <= 30 and not near(s, old_seeds(split) + used)), None)
        if new:
            lines[j] = f"{lines[j].split()[0]} {new}"
            p = write_batch(brief, lines[j:j + 1], avoid)[0]
    raise SystemExit(f"seed {j + 1} could not be replaced")


def scenarios(split):
    """SC_CACHE (a directory outside the repo) keeps finished batches so a crashed run resumes."""
    c = SPLITS[split]
    sh = corpus(split)
    brief = (P / "writer_brief.txt").read_text()
    lines = (HERE / c["seeds"]).read_text().splitlines()
    cache = Path(os.environ["SC_CACHE"]) if os.environ.get("SC_CACHE") else None

    def do(i):
        f = cache / f"{split}-b{i}.json" if cache else None
        if f and f.exists():
            return json.loads(f.read_text())
        sl = lines[i:i + BATCH]
        got = write_batch(brief, sl, sh)
        d = {"lines": sl, "prompts": [replace_seed(split, k, q, sl, sh) for k, q in enumerate(got)]}
        if f:
            f.write_text(json.dumps(d))
        return d

    with cf.ThreadPoolExecutor(3) as ex:
        ds = list(ex.map(do, range(0, c["n"], BATCH)))
    lines = [l for d in ds for l in d["lines"]]
    prompts = [q for d in ds for q in d["prompts"]]
    assert len(prompts) == c["n"] and len(lines) == c["n"] and len({R.norm(q) for q in prompts}) == c["n"]
    seen = set()
    for i, q in enumerate(prompts):  # a scenario may not echo an earlier new one: rewrite the offender alone
        if overlap(q, seen) > MAX_OVERLAP:
            prompts[i] = replace_seed(split, i, write_batch(brief, lines[i:i + 1], sh | seen)[0], lines, sh | seen)
        seen |= R.shingles(prompts[i])
    (HERE / c["seeds"]).write_text("\n".join(lines) + "\n")
    (HERE / c["sc"]).write_text(json.dumps([{"id": f"{c['pre']}{i:03d}", "prompt": q} for i, q in enumerate(prompts, 1)], indent=1) + "\n")


def sha_file(name):
    lines = [f"{R.sha((HERE / f).read_bytes())}  {DIR}/{f}" for f in FREEZE if (HERE / f).is_file()]
    lines.append(f"{R.sha((ROOT / 'scripts/rival_eval.py').read_bytes())}  scripts/rival_eval.py")
    (HERE / f"SHA256-{name}.txt").write_text("\n".join(lines) + "\n")


def late():
    """Append held seeds.txt and scenarios-heldout.json to SHA256-frozen.txt and log their hashes, before any held arm answer."""
    lines = [f"{R.sha((HERE / f).read_bytes())}  {DIR}/{f}" for f in LATE]
    with (HERE / "SHA256-frozen.txt").open("a") as f:
        f.write("\n".join(lines) + "\n")
    event("ledger.jsonl", event="fixtures_frozen", seeds_sha256=lines[0].split()[0], scenarios_sha256=lines[1].split()[0])


def event(ledger, **kw):
    t = time.time()
    with (HERE / ledger).open("a") as f:
        f.write(json.dumps({"ts": int(t), "iso": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **kw}) + "\n")


def prereg():
    if (HERE / "ledger.jsonl").exists() or (HERE / "held").exists():
        raise SystemExit("ledger.jsonl or a held run exists; the preregistered event is the first line, once")
    event("ledger.jsonl", event="preregistered", sha256_of="SHA256-frozen.txt", sha256=R.sha((HERE / "SHA256-frozen.txt").read_bytes()))


def frozen_edit_sha():
    return next(l.split()[0] for l in (HERE / "SHA256-frozen.txt").read_text().splitlines() if l.endswith("prompts/edit.md"))


def run(split, jobs):
    c = SPLITS[split]
    arms = {a: P / ARM_FILE[a] for a in c["arms"]}
    mine = [a for a in arms if a not in ("V0", "RIVAL")]
    if split == "held":
        assert R.sha(arms["EDIT"].read_bytes()) == frozen_edit_sha(), "prompts/edit.md is not the frozen edit"
    assert arms["V0"].read_bytes() == (ROOT / ".claude/skills/product-output-safety/SKILL.md").read_bytes(), "prompts/v0.md != SKILL.md"
    ledger, d = c["ledger"], HERE / split
    if (d / "results.json").exists():
        raise SystemExit("results.json exists; never overwrite")
    event(ledger, event="run_start", split=split, arms={a: R.sha(p.read_bytes())[:16] for a, p in arms.items()})
    scs = json.loads((HERE / c["sc"]).read_text())
    sysm = {a: p.read_text() for a, p in arms.items()}
    outs, errs = {a: {} for a in arms}, []

    def gen(a, sc):
        p = d / "outputs" / a / f"{sc['id']}.txt"
        if not p.exists():
            try:
                R.save(p, R.chat(R.GEN_MODEL, sysm[a], R.GEN_TASK + sc["prompt"], temperature=0.3))
            except RuntimeError as e:
                return errs.append(f"gen {a}/{sc['id']}: {e}")
        outs[a][sc["id"]] = p.read_text()

    with cf.ThreadPoolExecutor(jobs) as ex:
        list(ex.map(lambda t: gen(*t), [(a, s) for a in arms for s in scs]))
    ok = [s for s in scs if all(s["id"] in outs[a] for a in arms)]
    res, health, used = {}, {}, None
    for model in R.JUDGES:
        vs = {}
        for x in ["V0"] + mine:
            o = {"PERUN": outs[x], "RIVAL": outs["RIVAL"]}  # reuse rival_eval's judge with the arm under test as "PERUN"
            for sc, pair in zip(ok, cf.ThreadPoolExecutor(jobs).map(lambda sc: [R.judge_one(model, sc, a, b, d / x, o) for a, b in (("PERUN", "RIVAL"), ("RIVAL", "PERUN"))], ok)):
                vs[x, sc["id"]] = pair
        rate = R.slot1_rate([v for p in vs.values() for v in p])
        health[model] = None if rate is None else round(rate, 3)
        if rate is not None and R.SLOT1_OK[0] <= rate <= R.SLOT1_OK[1]:
            used = model
            for k, pair in vs.items():
                if None in pair:
                    errs.append(f"judge {k}: no verdict")
                else:
                    res[k] = R.scenario_score([R.order_score(v, f) for v, f in zip(pair, ("PERUN", "RIVAL"))])
            break
    out = dict(split=split, judge=used, slot1_rate=health, n_scenarios=len(scs), errors=errs, boot="10000 resamples, seed 1, percentile, over scenarios",
               arm_sha256={a: R.sha(t.encode())[:16] for a, t in sysm.items()})
    ids = [s["id"] for s in ok if all((x, s["id"]) in res for x in ["V0"] + mine)]
    if ids:
        v0 = [res["V0", i] for i in ids]
        out["n"] = len(ids)
        for name, v in [("v0", v0)] + [(x.lower(), [res[x, i] for i in ids]) for x in mine]:
            lo, hi = R.boot(v)
            out[name] = dict(mean=round(sum(v) / len(v), 3), ci95=[round(lo, 3), round(hi, 3)], wld=[sum(y == 1 for y in v), sum(y == .5 for y in v), sum(y == 0 for y in v)])
        for x in mine:
            dif = [res[x, i] - res["V0", i] for i in ids]
            lo, hi = R.boot(dif)
            out[f"paired_{x.lower()}_minus_v0"] = dict(mean=round(sum(dif) / len(dif), 3), ci95=[round(lo, 3), round(hi, 3)], up_down=[sum(y > 0 for y in dif), sum(y < 0 for y in dif)])
        out["per_scenario"] = {i: {x: res[x, i] for x in ["V0"] + mine} for i in ids}
        if split == "held":
            out["keep_rule_paired_lo_gt_0"] = out["paired_edit_minus_v0"]["ci95"][0] > 0
            out["win_lo_gt_0.5"] = out["edit"]["ci95"][0] > 0.5
    (d / "results.json").write_text(json.dumps(out, indent=1) + "\n")
    event(ledger, event="run_done", split=split, results_sha256=R.sha((d / "results.json").read_bytes()))
    print(json.dumps({k: v for k, v in out.items() if k != "per_scenario"}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("seeds", "scenarios", "sha", "prereg", "late", "run"))
    ap.add_argument("name", nargs="?")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    {"seeds": lambda: seeds(a.name), "scenarios": lambda: scenarios(a.name), "sha": lambda: sha_file(a.name), "prereg": prereg, "late": late,
     "run": lambda: run(a.name, a.jobs)}[a.cmd]()
