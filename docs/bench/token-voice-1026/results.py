#!/usr/bin/env python3
"""Regenerate results.json from runs.jsonl (byte-identical on rerun). Stdlib only, offline, no model call.

Per task: mean completion tokens and pass fraction over the samples. Per arm: median of those over the 60 tasks.
Paired A-B: per-task difference; CI = 10,000-resample percentile bootstrap over tasks, seed 1 (median for tokens, mean for pass rate).
Keep rule (frozen): Perun wins vs an arm iff the tokens CI upper bound is < 0 AND the pass-rate CI lower bound is > -0.05."""
import json, random, statistics as st
from pathlib import Path

D = Path(__file__).resolve().parent
ARMS = ("none", "caveman", "ponytail", "perun")
PAIRS = (("perun", "none"), ("perun", "caveman"), ("perun", "ponytail"), ("caveman", "none"), ("ponytail", "none"))


def boot(v, f, n=10000, seed=1):
    rng, m = random.Random(seed), len(v)
    b = sorted(f([v[rng.randrange(m)] for _ in range(m)]) for _ in range(n))
    return round(b[int(0.025 * n)], 6), round(b[int(0.975 * n) - 1], 6)


def build():
    cells = {}
    for r in map(json.loads, (D / "runs.jsonl").read_text().splitlines()):
        cells.setdefault((r["arm"], r["id"]), []).append(r)
    ids = sorted({i for _, i in cells})
    ks = {len(v) for v in cells.values()}
    if len(ks) != 1 or any((a, i) not in cells for a in ARMS for i in ids):
        raise ValueError("incomplete grid")
    tok = {a: [st.mean(x["completion_tokens"] for x in cells[(a, i)]) for i in ids] for a in ARMS}
    ps = {a: [st.mean(x["pass"] for x in cells[(a, i)]) for i in ids] for a in ARMS}
    res = {"n_tasks": len(ids), "samples_per_task": ks.pop(), "bootstrap": "10000 resamples, seed 1, percentile, over tasks", "arms": {}, "paired": []}
    for a in ARMS:
        rs = [x for i in ids for x in cells[(a, i)]]
        res["arms"][a] = {"median_completion_tokens": round(st.median(tok[a]), 3), "mean_completion_tokens": round(st.mean(tok[a]), 3),
                          "pass_rate": round(st.mean(ps[a]), 6), "pass_ci95": boot(ps[a], st.mean),
                          "truncated": sum(x["finish"] == "length" for x in rs), "no_code": sum(x["why"] == "no-code" for x in rs),
                          "prompt_tokens_per_call": round(st.mean(x["prompt_tokens"] for x in rs), 1)}
    for a, b in PAIRS:
        dt = [x - y for x, y in zip(tok[a], tok[b])]
        dp = [x - y for x, y in zip(ps[a], ps[b])]
        tlo, thi = boot(dt, st.median)
        plo, phi = boot(dp, st.mean)
        res["paired"].append({"a": a, "b": b, "median_token_diff": round(st.median(dt), 3), "token_ci95": [tlo, thi],
                              "median_token_ratio": round(st.median([x / y for x, y in zip(tok[a], tok[b])]), 4),
                              "pass_diff": round(st.mean(dp), 6), "pass_ci95": [plo, phi],
                              "fewer_tokens": thi < 0, "non_inferior": plo > -0.05, "a_wins_keep_rule": thi < 0 and plo > -0.05})
    return res


if __name__ == "__main__":
    (D / "results.json").write_text(json.dumps(build(), indent=1) + "\n")
