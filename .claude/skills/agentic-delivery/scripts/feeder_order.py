#!/usr/bin/env python3
"""feeder_order.py — order the work queue so a fix for a recurring failure class runs before features.

  feeder_order.py --ledger FILE [--min N] [--max-run M] < items.json

items.json is a list of {"id", "kind" ("fix"/"bugfix", any case; anything else is a feature), "class" (optional)}. FILE is
a JSON object {class: occurrences}, e.g. built from the flake or escaped-defect ledger. Output: the ids, one per line.
Rank 0: a fix whose non-empty class has >= N ledger occurrences (default 2, recurring); rank 1: any other fix (a missing
class never ranks 0); rank 2: the rest. Input order is kept inside a rank. After M consecutive fixes (default 3) a waiting
feature is promoted, so fixes cannot starve features. Side effects: none. Edge: a missing or unreadable file or a bad
shape (ledger not {str: int >= 0}, items not a list of objects with an id) exits 2 (fail closed).
"""
import argparse
import json
import sys


def _fix(i):
    return str(i.get("kind", "")).strip().lower() in ("fix", "bugfix")


def check(items, ledger):
    """Raise ValueError on a bad shape."""
    if not isinstance(ledger, dict) or not all(isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v >= 0
                                               for k, v in ledger.items()):
        raise ValueError("ledger must be an object {class: count >= 0}")
    if not isinstance(items, list) or not all(isinstance(i, dict) and "id" in i for i in items):
        raise ValueError("items must be a list of objects with an id")


def order(items, ledger, n=2, max_run=3):
    """Items sorted by rank (stable): recurring-class fix, other fix, rest; a feature is promoted after max_run fixes in a row."""
    def rank(i):
        c = i.get("class")
        return 2 if not _fix(i) else 0 if isinstance(c, str) and c and ledger.get(c, 0) >= n else 1
    s = sorted(items, key=rank)
    fixes, feats, out, run = [i for i in s if _fix(i)], [i for i in s if not _fix(i)], [], 0
    while fixes or feats:
        if fixes and (run < max_run or not feats):
            out.append(fixes.pop(0))
            run += 1
        else:
            out.append(feats.pop(0))
            run = 0
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--min", type=int, default=2)
    ap.add_argument("--max-run", type=int, default=3)
    a = ap.parse_args(argv)
    try:
        with open(a.ledger) as f:
            ledger = json.load(f)
        items = json.load(sys.stdin)
        check(items, ledger)
    except (OSError, ValueError) as e:
        print(f"feeder_order: {e}", file=sys.stderr)
        return 2
    print("\n".join(str(i["id"]) for i in order(items, ledger, a.min, max(1, a.max_run))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
