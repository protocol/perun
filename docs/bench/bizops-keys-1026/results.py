#!/usr/bin/env python3
"""Regenerate results-held.json: score arms RIVAL/SHIPPED/EDIT of bizops-r4-1018 held outputs against keys.json.

  results.py          write results-held.json next to this file (byte-identical on rerun)
All 150 held ids (r4-001 to r4-150) are scored. Pairs: exact two-sided McNemar on discordant
pass/fail (wins = first arm passes, second fails). Fail counts: one per failure code per scenario, "leak:<name>"
folded to "leak". exploratory_excluding_lead repeats pass counts and pairs with no-lead-number ignored (post-hoc). Stdlib only, no model call, no network."""
import importlib.util, json
from math import comb
from pathlib import Path

D = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("keys_score", D / "keys_score.py")
ks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ks)
OUT = D.parent / "bizops-r4-1018/outputs"
ARMS = ("RIVAL", "SHIPPED", "EDIT")
PAIRS = (("SHIPPED", "RIVAL"), ("EDIT", "RIVAL"), ("EDIT", "SHIPPED"))


def mcnemar(w, l):
    """Exact two-sided McNemar p on w wins and l losses."""
    n = w + l
    return 1.0 if n == 0 else min(1.0, 2 * sum(comb(n, i) for i in range(min(w, l) + 1)) / 2 ** n)


def build():
    keys = {k: v for k, v in json.loads((D / "keys.json").read_text()).items() if k.startswith("r4-")}
    res = {a: ks.score(keys, OUT / a)["scenarios"] for a in ARMS}
    fails = {}
    for a in ARMS:
        c = {}
        for r in res[a].values():
            for w in r["why"]:
                w = w.split(":")[0]
                c[w] = c.get(w, 0) + 1
        fails[a] = dict(sorted(c.items(), key=lambda kv: -kv[1]))
    def pairs_for(ok):
        out = {}
        for x, y in PAIRS:
            w = sum(ok(x, i) and not ok(y, i) for i in keys)
            l = sum(ok(y, i) and not ok(x, i) for i in keys)
            out[f"{x}_vs_{y}"] = {"wins": w, "losses": l, "p_two_sided": round(mcnemar(w, l), 4)}
        return out

    # post-hoc: lead_number restates the skill's own lead-with-a-number doctrine, so ignore that code
    nolead = lambda a, i: not [c for c in res[a][i]["why"] if c != "no-lead-number"]
    return {"split": "held", "n": len(keys), "outputs": "../bizops-r4-1018/outputs/<arm>/",
            "pass": {a: sum(r["pass"] for r in res[a].values()) for a in ARMS},
            "paired_mcnemar_exact": pairs_for(lambda a, i: res[a][i]["pass"]), "fails": fails,
            "exploratory_excluding_lead": {"note": "post-hoc, not preregistered: no-lead-number ignored",
                                           "pass": {a: sum(nolead(a, i) for i in keys) for a in ARMS},
                                           "paired_mcnemar_exact": pairs_for(nolead)}}


if __name__ == "__main__":
    (D / "results-held.json").write_text(json.dumps(build(), indent=1) + "\n")
