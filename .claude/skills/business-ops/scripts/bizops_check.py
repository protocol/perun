#!/usr/bin/env python3
"""Deterministic arithmetic checks business-ops already states, run on the user's own numbers.

Usage: bizops_check.py [input.json]   (stdin when no path)

Input is one flat JSON object; every value is bound by key name. Figures are
monthly and positive: cash, net_burn, price, cac, churn (fraction per month),
margin (fraction) or unit_cost (per price unit; margin = (price - unit_cost) / price).
A check runs only when its limit key is present, otherwise it prints SKIP; this
script invents no threshold. Limits: min_runway_months, min_ltv_cac,
max_payback_months, min_margin. A limit that is met exactly passes.

Exit 0 all stated limits met, 1 any FAIL, 2 bad input ("ERROR <reason>"),
3 every check SKIPped (prints INCONCLUSIVE). Arithmetic is exact (Fraction).
Side effects: none beyond reading the input and printing.
"""
import json
import math
import sys
from fractions import Fraction


def num(d, key):
    if key not in d:
        raise ValueError(f"missing key {key}")
    v = d[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{key} must be a number")
    if not math.isfinite(float(v)):
        raise ValueError(f"{key} must be finite")
    return Fraction(str(v))


def pos(d, key):
    v = num(d, key)
    if v <= 0:
        raise ValueError(f"{key} must be > 0")
    return v


def margin(d):
    """Margin fraction in [0, 1] from `margin`, or (price - unit_cost) / price; both given must agree."""
    m = num(d, "margin") if "margin" in d else None
    if "unit_cost" in d:
        if num(d, "unit_cost") < 0:
            raise ValueError("unit_cost must be >= 0")
        derived = (pos(d, "price") - num(d, "unit_cost")) / pos(d, "price")
        if m is not None and m != derived:
            raise ValueError("margin conflicts with price and unit_cost")
        m = derived
    if m is None:
        raise ValueError("missing key margin (or price and unit_cost)")
    if not 0 <= m <= 1:
        raise ValueError("margin must be between 0 and 1")
    return m


def runway(d):
    return pos(d, "cash") / pos(d, "net_burn")


def ltv_cac(d):
    return pos(d, "price") * margin(d) / pos(d, "churn") / pos(d, "cac")


def payback(d):
    pm = pos(d, "price") * margin(d)
    if pm <= 0:
        raise ValueError("price x margin must be > 0")
    return pos(d, "cac") / pm


# name, limit key, True when value must be >= limit, formula, SKILL.md sentence mechanized (verbatim), fn
CHECKS = [
    ("runway", "min_runway_months", True, "cash / net_burn", "runway = cash / net burn", runway),
    ("ltv_cac", "min_ltv_cac", True, "price x margin / churn / cac", "LTV = price x margin / churn", ltv_cac),
    ("payback", "max_payback_months", False, "cac / (price x margin)", "payback = CAC / (price x margin)", payback),
    # the quoted sentence's arithmetic: margin = (price - unit_cost) / price, e.g. ($40 - $12) / $40 = 70%
    ("margin", "min_margin", True, "margin or (price - unit_cost) / price",
     "show $28 per seat, 70% from the user's inputs", margin),
]


def run(d):
    """Return (output lines, exit code) for one parsed input object; raise ValueError on bad input."""
    if not isinstance(d, dict):
        raise ValueError("input must be a JSON object")
    lines, fail, ran = [], False, 0
    for name, lim, ge, formula, quote, fn in CHECKS:
        if lim not in d:
            lines.append(f'SKIP {name}: no {lim} in input | mechanizes: "{quote}"')
            continue
        ran += 1
        v, limit = fn(d), num(d, lim)
        ok = v >= limit if ge else v <= limit
        fail |= not ok
        lines.append(f'{"PASS" if ok else "FAIL"} {name}: {formula} = {float(v):.6g} '
                     f'{">=" if ge else "<="} {lim} {float(limit):.6g} | mechanizes: "{quote}"')
    if not ran:
        lines.append("INCONCLUSIVE no limit stated; add min_runway_months, min_ltv_cac, max_payback_months or min_margin")
    return lines, 3 if not ran else 1 if fail else 0


def main(argv):
    try:
        with (open(argv[0]) if argv else sys.stdin) as f:
            lines, rc = run(json.load(f))
    except (ValueError, KeyError, OverflowError, TypeError, OSError, RecursionError) as e:
        print(f"ERROR {e}")
        return 2
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
