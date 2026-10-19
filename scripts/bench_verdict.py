#!/usr/bin/env python3
"""Outcome-first verdict for a Perun-vs-rival comparison, plus the doc gate that enforces it.

verdict(spec) takes preference scores (per-item in [0, 1], or wins/ties/losses with a tie = 0.5), optional
cost per item for each arm, and an optional user-felt outcome metric. It returns one label:

  WIN                                          preference CI lower bound > 0.5 (or a parity tie) AND cost measured
                                               with Perun <= rival (a tie needs strictly lower) AND outcome measured
                                               and not worse
  PREFERENCE-ONLY WIN (cost/outcome unmeasured)  lower bound > 0.5 but cost or outcome missing
  WIN ON PROXY, OUTCOME WORSE                  lower bound > 0.5, outcome measured and worse
  WIN ON PROXY, COST HIGHER                    lower bound > 0.5, outcome fine, Perun costs more
  LOSS                                         CI upper bound < 0.5
  PARITY                                       everything else

The CI is rival_eval.boot (percentile bootstrap of the mean, seed 1), reused so every bench shares one rule.
Edge cases: no items raises ValueError; cost_per_item/outcome need both arms or count as unmeasured.

`bench_verdict.py spec.json` prints the verdict JSON. `bench_verdict.py --check-doc docs/perun-vs-rivals.md`
exits 1 if a row's cell under a "Verdict" table header calls a Win without the honest preference-only label or a `$` cost
figure plus an `outcome ... <number>` metric. Reads files only.
"""
import functools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rival_eval import boot  # noqa: E402

_boot = functools.lru_cache(maxsize=None)(lambda vals: boot(list(vals)))  # 10,000 resamples; benches repeat inputs

PREF_ONLY = "PREFERENCE-ONLY WIN (cost/outcome unmeasured)"


def _scores(spec):
    if "items" in spec:
        vals = [float(x) for x in spec["items"]]
    else:
        vals = [1.0] * spec["wins"] + [0.5] * spec["ties"] + [0.0] * spec["losses"]
    if not vals or any(not 0 <= v <= 1 for v in vals):
        raise ValueError("need at least one score, each in [0, 1]")
    return vals


def verdict(spec):
    """Return {verdict, mean, lo, hi, n} for one comparison spec (see module docstring)."""
    vals = _scores(spec)
    lo, hi = _boot(tuple(vals))
    cost, out = spec.get("cost_per_item"), spec.get("outcome")
    have_cost = bool(cost) and "perun" in cost and "rival" in cost
    have_out = bool(out) and "perun" in out and "rival" in out
    if hi < 0.5:
        label = "LOSS"
    elif lo <= 0.5 and not (have_cost and have_out and cost["perun"] < cost["rival"]):
        label = "PARITY"
    elif not (have_cost and have_out):
        label = PREF_ONLY if lo > 0.5 else "PARITY"
    else:
        sign = 1 if out.get("higher_is_better", True) else -1
        if sign * (out["perun"] - out["rival"]) < 0:
            label = "WIN ON PROXY, OUTCOME WORSE" if lo > 0.5 else "PARITY"
        elif cost["perun"] > cost["rival"]:
            label = "WIN ON PROXY, COST HIGHER"
        else:
            label = "WIN"
    return {"verdict": label, "mean": sum(vals) / len(vals), "lo": lo, "hi": hi, "n": len(vals)}


def check_doc(text):
    """Return the table rows (as text) whose verdict cell says Win with no cost figure and outcome metric."""
    bad, col = [], None
    for line in text.splitlines():
        if not line.startswith("|"):
            col = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if "Verdict" in cells:  # table header: remember which column holds the verdict
            col = cells.index("Verdict")
            continue
        if col is None or "---" in line or col >= len(cells):
            continue
        cell = cells[col]
        head = re.sub(r"(?i)\b(not a|no|not)\s+win\b|\bwin\s+not\b", "", cell[:60])
        if not re.search(r"(?i)\bwin\b", head):
            continue
        pref_only = re.search(r"(?i)preference-only win", cell) and re.search(r"(?i)unmeasured", cell)
        measured = re.search(r"\$\d", cell) and re.search(r"(?i)outcome[^|.]*\d", cell)
        if not (pref_only or measured):
            bad.append(line[:80])
    return bad


def main(argv):
    if argv[:1] == ["--check-doc"]:
        bad = check_doc(Path(argv[1]).read_text())
        for row in bad:
            print("Win without cost figure and outcome metric:", row)
        return 1 if bad else 0
    print(json.dumps(verdict(json.loads(Path(argv[0]).read_text())), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
