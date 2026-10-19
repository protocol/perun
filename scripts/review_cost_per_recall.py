#!/usr/bin/env python3
"""Review cost per real bug caught, and false alarms per case, from committed bench artifacts only.

  review_cost_per_recall.py            print the markdown tables (docs/bench/review-cost-per-recall/README.md embeds them)

Set S1 is recomputed from per-case raw outputs (docs/bench/review-real-skill-1016): crediting is that bench's
`driver.tally` (which calls `score_review.score` for the strict match), the CI for per-case means is
`rival_eval.boot`. Every other set is read from `reported.tsv`, rows transcribed from a cited file whose aggregate
numbers are the only data committed (per-case data was kept private on purpose), so they get no CI.

Definitions: recall = caught / bugs (one bug per case on every corpus here); false alarm = a finding the verifier
did not credit as real or as the reference bug, so `unverifiable` counts as false; $ per caught bug = review $ per
case / recall. A field the source does not publish prints `unmeasured`; nothing is estimated.
"""
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BENCH = REPO / "docs/bench"
OUT = BENCH / "review-cost-per-recall"
RAW = BENCH / "review-real-skill-1016"
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(RAW))
import driver  # noqa: E402  review-real-skill-1016 driver: loadt/tally credit one case
import rival_eval  # noqa: E402  boot(): percentile bootstrap CI of a mean

U = "unmeasured"


def boot_ratio(num, den, n=10000, seed=1):
    """Percentile bootstrap 95% CI of sum(num)/sum(den) over cases; resamples with a zero denominator are skipped."""
    rng, m, xs = random.Random(seed), len(num), []
    for _ in range(n):
        ix = [rng.randrange(m) for _ in range(m)]
        d = sum(den[i] for i in ix)
        if d:
            xs.append(sum(num[i] for i in ix) / d)
    xs.sort()
    return xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]


def raw_arm(arm):
    """Per-case rows (cred, bugs, findings, good, review $ = mean of the case's non-error review calls) for one arm."""
    led = [json.loads(x) for x in (RAW / "ledger.jsonl").read_text().splitlines()]
    cost = defaultdict(list)
    for x in led:
        if x["tag"].startswith(f"review/{arm}/") and not x["err"]:
            cost[x["tag"].split("/")[2]].append(x["cost"])
    rows = [dict(driver.loadt(arm, c), usd=sum(cost[c]) / len(cost[c])) for c in driver.IDS if driver.loadt(arm, c)]
    verify = sum(x["cost"] for x in led if x["tag"].startswith(f"verify/{arm}/"))
    return rows, verify


def raw_row(arm):
    rows, verify = raw_arm(arm)
    n, caught = len(rows), sum(r["cred"] for r in rows)
    cred, bugs, usd = ([r[k] for r in rows] for k in ("cred", "bugs", "usd"))
    fa = [r["n"] - r["good"] for r in rows]
    rec, perbug = caught / sum(bugs), sum(usd) / caught
    ci = lambda lo_hi, f="{:.3f}": f"[{f.format(lo_hi[0])}, {f.format(lo_hi[1])}]"  # noqa: E731
    return dict(arm=arm, n=n, recall=f"{rec:.3f} {ci(boot_ratio(cred, bugs))}", fa=f"{sum(fa) / n:.2f} {ci(rival_eval.boot(fa), '{:.2f}')}",
                usd=f"${sum(usd) / n:.4f} {ci(rival_eval.boot(usd), '${:.4f}')}", perbug=f"${perbug:.3f} {ci(boot_ratio(usd, cred), '${:.3f}')}",
                verify=f"${verify / n:.4f}")


def reported(path=OUT / "reported.tsv"):
    """Rows of reported.tsv with the derived columns; blank source fields stay `unmeasured`."""
    out = []
    for r in csv.DictReader(path.open(), delimiter="\t"):
        n, rec, usd = int(r["n"]), float(r["recall"]), float(r["usd_case"])
        caught = round(rec * n)
        fa = f"{(int(r['findings']) - int(r['good'])) / n:.2f}" if r["findings"] and r["good"] else U
        out.append(dict(r, caught=caught, fa=fa, perbug=f"${usd * n / caught:.3f}" if caught else "no bug caught", usd=f"${usd:.3f}"))
    return out


def tables():
    """Markdown for set S1 (recomputed, with CI) and the reported sets."""
    s1 = ["| Arm | n | Recall [95% CI] | False alarms per case [95% CI] | Review $ per case [95% CI] | Review $ per caught bug [95% CI] | Verifier $ per case |", "|---|---|---|---|---|---|---|"]
    for arm, name in (("REAL", "Perun (real skill)"), ("TK", "Anthropic toolkit code-reviewer")):
        r = raw_row(arm)
        s1.append(f"| {name} | {r['n']} | {r['recall']} | {r['fa']} | {r['usd']} | {r['perbug']} | {r['verify']} |")
    rest, last = ["| Set | Arm | n | Recall | Caught | False alarms per case | Review $ per case | $ per caught bug | $ basis |", "|---|---|---|---|---|---|---|---|---|"], None
    for r in reported():
        rest.append(f"| {r['set'] if r['set'] != last else ''} | {r['arm']} | {r['n']} | {float(r['recall']):.3f} | {r['caught']} | {r['fa']} | {r['usd']} | {r['perbug']} | {r['basis']} |")
        last = r["set"]
    return "\n".join(s1), "\n".join(rest)


if __name__ == "__main__":
    print("\n\n".join(tables()))
