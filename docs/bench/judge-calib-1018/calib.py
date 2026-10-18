#!/usr/bin/env python3
"""Judge position-bias calibration on SPENT growth r4/r5 held-out outputs (PCSS only, $0, no claude -p).
Calibration only: nothing here feeds a skill, a rival row or a past verdict.

Uses the frozen judge of growth-r5-1018 unchanged: scripts/rival_eval.py (JUDGE_SYSTEM, labels, parse_verdict, chat), both orders.
Controls, per judge, per item (n = 60: 30 r4 + 30 r5 held-out outputs, arms rotating v0/v1/rival, seed 1018):
  a  identical pair A vs A            slot-1 rate is pure position bias (no content difference exists)
  b  A vs A cut to its first 30%      big gap; the full answer is the correct pick
  c  A vs A minus its last section    small gap; the full answer is the correct pick
The only change from the frozen call: the label seed is salted with control and order, so the two orders of an identical pair do not
reduce to one byte-identical prompt.

  calib.py run      judge every pair (resumable; appends to raw/verdicts.jsonl)
  calib.py report   print the per-judge, per-control table as markdown
"""
import concurrent.futures as cf, json, math, random, re, sys, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import rival_eval as R  # noqa: E402

RAW = HERE / "raw" / "verdicts.jsonl"
SRC = {"r4": ROOT / "docs/bench/growth-r4-1018", "r5": ROOT / "docs/bench/growth-r5-1018"}
ARMS3 = ("v0", "v1", "rival")
N_PER_ROUND = 30


def items():
    """60 item dicts (id, round, arm, prompt, text), deterministic."""
    out, rnd = [], random.Random(1018)
    for r, d in SRC.items():
        scs = rnd.sample(json.loads((d / "scenarios-heldout.json").read_text()), N_PER_ROUND)
        for i, sc in enumerate(sorted(scs, key=lambda s: s["id"])):
            arm = ARMS3[i % 3]
            f = next((d / "results/outputs" / arm).glob(sc["id"] + "-*.txt"))
            out.append(dict(id=sc["id"], round=r, arm=arm, prompt=sc["prompt"], text=f.read_text()))
    return out


def drop_last_section(t):
    """Text without its last section: from the last markdown heading when it starts in the back half, else the last blank-line block.
    None when that would leave under 30% of the text."""
    heads = [m.start() for m in re.finditer(r"^#{1,6} ", t, re.M)]
    cut = heads[-1] if heads and heads[-1] > len(t) / 2 else t.rstrip().rfind("\n\n")
    return t[:cut].rstrip() if cut > len(t) * 0.3 else None


def pair(ctl, t):
    """(A, B) where A is the full answer; B is None when the control does not apply."""
    if ctl == "a":
        return t, t
    if ctl == "b":
        return t, t[: int(len(t) * 0.3)].rstrip()
    return t, drop_last_section(t)


def judge(model, it, ctl, order, a, b):
    """Frozen judge call. order 1: A in slot 1; order 2: A in slot 2. Returns "1", "2", "tie" or None (unusable)."""
    first, second = (a, b) if order == 1 else (b, a)
    sc = {"id": f"{it['id']}-{ctl}-{order}", "prompt": it["prompt"]}  # salted label seed
    x, y = R.labels(sc, first, second)
    system = R.JUDGE_SYSTEM.format(a=x, b=y)
    user = f"REQUEST:\n{it['prompt']}\n\n=== Response {x} ===\n{first}\n\n=== Response {y} ===\n{second}\n"
    for _ in range(2):
        try:
            v = R.parse_verdict(R.chat(model, system, user, max_tokens=3000), x, y)
        except RuntimeError:
            continue
        if v:
            return v
    return None


def run():
    its = items()
    RAW.parent.mkdir(exist_ok=True)
    done = {(r["judge"], r["id"], r["ctl"], r["order"]) for r in map(json.loads, RAW.read_text().splitlines())} if RAW.exists() else set()
    lock, jobs = threading.Lock(), []
    for model in R.JUDGES:
        for it in its:
            for ctl in "abc":
                a, b = pair(ctl, it["text"])
                if b is None:
                    continue
                for order in (1, 2):
                    if (model, it["id"], ctl, order) not in done:
                        jobs.append((model, it, ctl, order, a, b))

    def work(j):
        model, it, ctl, order, a, b = j
        v = judge(model, it, ctl, order, a, b)
        with lock, RAW.open("a") as f:
            f.write(json.dumps(dict(judge=model, id=it["id"], round=it["round"], arm=it["arm"], ctl=ctl, order=order, verdict=v, b_frac=round(len(b) / len(a), 3))) + "\n")

    with cf.ThreadPoolExecutor(8) as ex:
        list(ex.map(work, jobs))
    print("judged", len(jobs))


def wilson(k, n, z=1.96):
    """95% Wilson interval for k of n."""
    if not n:
        return float("nan"), float("nan")
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def report():
    rows = [json.loads(x) for x in RAW.read_text().splitlines()]
    print("| Judge | Control | Pairs | Slot-1 [95% CI] | Ties | Unusable | Correct pick (full answer) | Picked slot 1 when full is in slot 1 / in slot 2 |\n|---|---|---|---|---|---|---|---|")
    for m in R.JUDGES:
        for ctl, name in (("a", "a identical"), ("b", "b truncated to 30%"), ("c", "c last section dropped")):
            r = [x for x in rows if x["judge"] == m and x["ctl"] == ctl]
            if not r:
                continue
            dec = [x for x in r if x["verdict"] in ("1", "2")]
            s1 = sum(x["verdict"] == "1" for x in dec)
            lo, hi = wilson(s1, len(dec))
            cp = cp2 = "n/a"
            if ctl != "a":
                ok = sum((x["verdict"] == "1") == (x["order"] == 1) for x in dec)  # picked the full answer
                f1, f2 = [x for x in dec if x["order"] == 1], [x for x in dec if x["order"] == 2]
                cp = f"{ok}/{len(dec)} = {ok / max(len(dec), 1):.3f}"
                c1, c2 = sum(x["verdict"] == "1" for x in f1), sum(x["verdict"] == "1" for x in f2)
                cp2 = f"{c1}/{len(f1)} = {c1 / max(len(f1), 1):.3f} / {c2}/{len(f2)} = {c2 / max(len(f2), 1):.3f}"
            print(f"| {m} | {name} | {len(r) // 2} | {f'{s1}/{len(dec)} = {s1 / len(dec):.3f} [{lo:.3f}, {hi:.3f}]' if dec else 'n/a (no decisive verdict)'} | {sum(x['verdict'] == 'tie' for x in r)} | {sum(x['verdict'] is None for x in r)} | {cp} | {cp2} |")


def real():
    """Re-read the spent r5 verdicts: per judge, how the two orders of each scenario/arm pair relate.
    content = one order picked slot 1 and the other slot 2 (same answer both times); pos1/pos2 = both orders picked slot 1 / slot 2."""
    d = json.loads((SRC["r5"] / "results/judge-verdicts.json").read_text())
    print("| Judge | Pairs | Both orders decisive | content-consistent | both slot 1 | both slot 2 | any tie | Slot-1 overall |\n|---|---|---|---|---|---|---|---|")
    for m in R.JUDGES:
        pr = {}
        for k, v in d.items():
            arm, _, model, order, f = k.split("/")
            if model == m:
                pr.setdefault((arm, f.split("-")[0]), {})[order.split("__")[0]] = v
        vs = [list(p.values()) for p in pr.values()]
        both = [p for p in vs if all(x in ("1", "2") for x in p)]
        c, p1, p2 = (sum(sorted(p) == e for p in both) for e in (["1", "2"], ["1", "1"], ["2", "2"]))
        flat = [x for p in vs for x in p if x in ("1", "2")]
        print(f"| {m} | {len(vs)} | {len(both)} | {c} | {p1} | {p2} | {sum('tie' in p for p in vs)} | {flat.count('1') / len(flat):.3f} |")


if __name__ == "__main__":
    {"run": run, "report": report, "real": real}[sys.argv[1]]()
