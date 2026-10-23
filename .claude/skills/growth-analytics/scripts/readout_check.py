#!/usr/bin/env python3
"""readout_check.py: deterministic pass/fail checks on a finished two-arm A/B readout. Stdlib only.

Usage: readout_check.py READOUT.json

Checks only what the input pre-registers; it holds no thresholds of its own. A rule whose
pre-registered input is absent prints SKIP (never a default). Keys:
  required: "arms": {"control": {"n": int, "conversions": int}, "variant": {...}}, "run_days": number
  srm:      "srm_alpha" and "expected_split": {"control": f, "variant": f} (sums to 1)
  holm:     "alpha" and "primary_p_values": [p, ...]; optional "guardrail_p_values": {name: p}
            (reported unadjusted, never Holm-adjusted)
  sample_size: "planned_sample_size" (total, both arms; checks only observed n >= plan)
  run-length: "planned_days"

Prints one `PASS|FAIL|SKIP <rule>: <detail>` line per rule in a fixed order; no clock, no network.
SRM and Holm are standard checks the skill does not name: mechanized conventions, not skill doctrine.
Exit: 0 no FAIL and at least one PASS, 1 any FAIL, 2 bad input (`ERROR <reason>`, no traceback),
3 every rule SKIPped (`INCONCLUSIVE: nothing pre-registered`).
"""
from __future__ import annotations

import json
import math
import sys

ARMS = ("control", "variant")


def _num(r: dict, k: str, lo: float, hi: float | None = None, *, integer: bool = False) -> float:
    v = r[k]
    if isinstance(v, bool) or not isinstance(v, int if integer else (int, float)) or not v >= lo or (hi is not None and not v <= hi):
        raise ValueError(f"{k} must be {'an integer' if integer else 'a number'} in [{lo}, {hi if hi is not None else 'inf'}]")
    return v


def _arms(r: dict) -> dict:
    a = r["arms"]
    if not isinstance(a, dict) or set(a) != set(ARMS):
        raise ValueError("arms must have exactly the keys control and variant")
    for name in ARMS:
        n = _num(a[name], "n", 1, integer=True)
        _num(a[name], "conversions", 0, n, integer=True)
    return a


def _p(v: object, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
        raise ValueError(f"{what} must be a p-value in [0, 1]")
    return v


def srm(r: dict) -> tuple[str, str]:
    # SKILL.md "Recompute lift, rates and significance from the stated counts ... and lead with the
    # figure that does not reconcile": an arm split that departs from the stated split does not
    # reconcile. The skill names no SRM threshold, so srm_alpha must come from the input.
    if "srm_alpha" not in r:
        return "SKIP", "no pre-registered srm_alpha"
    alpha = _num(r, "srm_alpha", 0, 1)
    if "expected_split" not in r:
        return "SKIP", "no pre-registered expected_split"
    sp = r["expected_split"]
    if not isinstance(sp, dict) or set(sp) != set(ARMS):
        raise ValueError("expected_split must have exactly the keys control and variant")
    for name in ARMS:
        _num(sp, name, 0)
    if abs(sum(sp.values()) - 1) > 1e-9 or not all(sp.values()):
        raise ValueError("expected_split must be positive and sum to 1")
    a = _arms(r)
    total = sum(a[k]["n"] for k in ARMS)
    x2 = sum((a[k]["n"] - total * sp[k]) ** 2 / (total * sp[k]) for k in ARMS)
    p = math.erfc(math.sqrt(x2 / 2))  # chi-square survival function, 1 df
    return ("PASS" if p >= alpha else "FAIL"), (
        f"arms {a['control']['n']}/{a['variant']['n']}, chi2={x2:.3f}, p={p:.4g}, srm_alpha={alpha}")


def holm(r: dict) -> tuple[str, str]:
    # SKILL.md "Pre-declare a primary and a guardrail metric so a secondary win is not
    # cherry-picked": Holm runs over the primary p-values only. Guardrails are listed beside it,
    # unadjusted, never folded into the family.
    if "primary_p_values" not in r:
        return "SKIP", "no primary_p_values"
    if "alpha" not in r:
        return "SKIP", "no pre-registered alpha"
    alpha = _num(r, "alpha", 0, 1)
    ps = r["primary_p_values"]
    if not isinstance(ps, list) or not ps:
        raise ValueError("primary_p_values must be a non-empty list")
    s = sorted(_p(p, "primary_p_values entry") for p in ps)
    m = len(s)
    adj, run = [], 0.0
    for i, p in enumerate(s):
        run = max(run, min(1.0, (m - i) * p))
        adj.append(run)
    lost = sum(1 for p, a in zip(s, adj) if p < alpha <= a)
    g = r.get("guardrail_p_values", {})
    if not isinstance(g, dict):
        raise ValueError("guardrail_p_values must be an object of name: p")
    gtxt = "; guardrails (unadjusted): " + ", ".join(f"{k} p={_p(v, 'guardrail p'):.4g}" for k, v in g.items()) if g else ""
    return ("FAIL" if lost else "PASS"), (
        f"{m} primary p-value(s), smallest raw {s[0]:.4g}, Holm-adjusted {adj[0]:.4g}, alpha={alpha}"
        + (f"; {lost} raw-significant result(s) fail Holm" if lost else "") + gtxt)


def sample_size(r: dict) -> tuple[str, str]:
    # SKILL.md "Require a fixed N or duration read once at the end" / "extend to the pre-committed N":
    # observed n below the pre-committed N is not that read.
    if "planned_sample_size" not in r:
        return "SKIP", "no pre-registered planned_sample_size"
    plan = _num(r, "planned_sample_size", 1)
    a = _arms(r)
    n = sum(a[k]["n"] for k in ARMS)
    return ("PASS" if n >= plan else "FAIL"), f"observed n={n}, planned {plan}"


def days(r: dict) -> tuple[str, str]:
    # SKILL.md "A day-2 p = 0.03 on a 14-day test ... is peeking": a read before the
    # pre-committed duration is a peek.
    if "planned_days" not in r:
        return "SKIP", "no pre-registered planned_days"
    plan = _num(r, "planned_days", 0)
    ran = _num(r, "run_days", 0)
    return ("PASS" if ran >= plan else "FAIL"), f"ran {ran} days, planned {plan}"


RULES = (("srm", srm), ("holm", holm), ("sample_size", sample_size), ("run-length", days))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("ERROR usage: readout_check.py READOUT.json")
        return 2
    try:
        with open(argv[1], encoding="utf-8") as f:
            r = json.load(f)
        if not isinstance(r, dict):
            raise ValueError("readout must be a JSON object")
        _arms(r)
        _num(r, "run_days", 0)
        results = [(name, *fn(r)) for name, fn in RULES]
    except KeyError as e:
        print(f"ERROR missing key {e.args[0]}")
        return 2
    except (OSError, ValueError, TypeError, OverflowError) as e:
        print(f"ERROR {e}")
        return 2
    for name, status, detail in results:
        print(f"{status} {name}: {detail}")
    if any(s == "FAIL" for _, s, _ in results):
        return 1
    if all(s == "SKIP" for _, s, _ in results):
        print("INCONCLUSIVE: nothing pre-registered")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
