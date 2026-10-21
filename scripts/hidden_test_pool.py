#!/usr/bin/env python3
"""Exploratory pool of every hard-split sample across the hidden-test r2 runs (pilot, ablation, confirm).

Reads the committed runs.jsonl files, maps arm `perun-no-delivery+testing` onto `perun-core` (identical text), averages each ticket's
samples per arm, and prints pass counts plus paired differences with a 10,000-resample percentile bootstrap over tickets (seed 1,
`rival_eval.boot`). Runs are mixed (different dates, seeds, sample counts), so this is descriptive, not a preregistered test.
Offline; writes nothing.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rival_eval import boot  # noqa: E402

D = Path(__file__).resolve().parent.parent / "docs/bench/hidden-test-r2-1021"
FILES = ("pilot/runs.jsonl", "pilot/ablation/runs.jsonl", "confirm/runs.jsonl")
PAIRS = (("perun", "none"), ("perun-core", "none"), ("perun-core", "perun"))


def pool(d=D):
    """-> (counts {arm: (passed, total)}, diffs {(a, b): (mean, lo, hi)}) over hard (`h_*`) tickets."""
    recs = [json.loads(line) for f in FILES for line in (d / f).read_text().splitlines()]
    recs = [r for r in recs if r["id"].startswith("h_")]
    for r in recs:
        if r["arm"] == "perun-no-delivery+testing":
            r["arm"] = "perun-core"
    ids = sorted({r["id"] for r in recs})

    def per(arm):
        return [sum(r["pass"] for r in x) / len(x) for x in ([r for r in recs if r["arm"] == arm and r["id"] == i] for i in ids)]

    counts = {a: (sum(r["pass"] for r in recs if r["arm"] == a), sum(r["arm"] == a for r in recs)) for a in ("none", "perun", "perun-core")}
    diffs = {}
    for a, b in PAIRS:
        diff = [x - y for x, y in zip(per(a), per(b))]
        lo, hi = boot(diff)
        diffs[(a, b)] = (sum(diff) / len(diff), lo, hi)
    return counts, diffs


def main():
    counts, diffs = pool()
    for a, (p, n) in counts.items():
        print(f"{a}: {p}/{n} = {p / n:.3f}")
    for (a, b), (m, lo, hi) in diffs.items():
        print(f"{a} minus {b}: {m:+.3f} [{lo:+.3f}, {hi:+.3f}]")


if __name__ == "__main__":
    main()
