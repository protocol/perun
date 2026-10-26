#!/usr/bin/env python3
"""Regenerate results-held.json: score arms RIVAL/v0/c9c of idea-critic-r9-1018 held outputs against keys.json.

  results.py          write results-held.json next to this file (byte-identical on rerun)
Pairs: exact two-sided McNemar on discordant pass/fail (wins = first arm passes, second fails). Fail counts:
one per failure code per scenario. Stdlib only, no model call, no network."""
import importlib.util, json
from math import comb
from pathlib import Path

D = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("keys_score", D / "keys_score.py")
ks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ks)
OUT = D.parent / "idea-critic-r9-1018/outputs/held"
ARMS = ("RIVAL", "v0", "c9c")
PAIRS = (("v0", "RIVAL"), ("c9c", "RIVAL"), ("c9c", "v0"))


def mcnemar(w, l):
    """Exact two-sided McNemar p on w wins and l losses."""
    n = w + l
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(w, l) + 1)) / 2 ** n)


def build():
    keys = json.loads((D / "keys.json").read_text())
    res = {a: ks.score(keys, OUT / a)["scenarios"] for a in ARMS}
    fails = {}
    for a in ARMS:
        c = {}
        for r in res[a].values():
            for w in r["why"]:
                c[w] = c.get(w, 0) + 1
        fails[a] = dict(sorted(c.items(), key=lambda kv: -kv[1]))
    pairs = {}
    for x, y in PAIRS:
        w = sum(res[x][i]["pass"] and not res[y][i]["pass"] for i in keys)
        l = sum(res[y][i]["pass"] and not res[x][i]["pass"] for i in keys)
        pairs[f"{x}_vs_{y}"] = {"wins": w, "losses": l, "p_two_sided": round(mcnemar(w, l), 4)}
    return {"split": "held", "n": len(keys), "outputs": "../idea-critic-r9-1018/outputs/held/<arm>/",
            "pass": {a: sum(r["pass"] for r in res[a].values()) for a in ARMS},
            "paired_mcnemar_exact": pairs, "fails": fails}


if __name__ == "__main__":
    (D / "results-held.json").write_text(json.dumps(build(), indent=1) + "\n")
