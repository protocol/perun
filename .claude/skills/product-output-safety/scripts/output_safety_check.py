#!/usr/bin/env python3
"""Deterministic checks of a product's LLM-output handling against rules product-output-safety already states.

Usage: output_safety_check.py [input.json]   (stdin when no path)

Input is one JSON object; every value is bound by key name. A check runs only when its
key is present and non-vacuous, otherwise it prints SKIP; this script invents no
threshold, rate or list of "typical" values. It never certifies anything: PASS means
only that the stated rule's mechanical part holds for the input you gave.

Keys (rows are non-empty objects bound by field name; strings must be non-blank):
  harm_inventory   [{harm, affected, worst_case, owner}]   an empty list FAILs the inventory
  rereview_on      ["feature", "model", "data"]            names what triggers re-review
  actions          [{action, high_stakes: bool, human_gate: bool}]
  metrics          [{name, measured: bool, value?}]        a stated value needs measured: true
  test_rows        [{harm, positive_control, negative_control, sliced_by, metric,
                     threshold, threshold_owner, stop_condition, gated_irreversible?}]
  sweeps           {prompt_injection, data_leakage, excess_agency: bool}
  claims_about_system  [str]     scanned for certification words; any hit FAILs, even a
                                 disclaimer (fail closed, reword the line)
  confidence_displays  [str]     text shown to users, scanned for a bare percentage
  confidence_tiers     {tier: definition}
  override_offered     bool
  card             null (no card) or {intended_use, out_of_scope_uses, subgroup_performance,
                     limits, known_gaps, owner, model_version, data_composition, provenance, consent}
  disclosure_recommended  bool
  legal_questions  [{question, routed_to}]
  regimes_named    [str]         must name the three regimes (a negated entry does not count)
                                 and carry no year or version

An empty list for actions, metrics, test_rows (no inventory given), legal_questions,
claims_about_system or confidence_displays is vacuous: SKIP, never PASS. An empty row or a
blank string inside a list is bad input.

Exit 0 all run checks PASS, 1 any FAIL, 2 bad input ("ERROR <reason>"),
3 every check SKIPped (prints INCONCLUSIVE). Side effects: none beyond reading input and printing.
"""
import json
import math
import re
import sys

NEG = re.compile(r"\b(not|never|no|cannot|without)\b|n't", re.I)
# Fail closed: any certification word FAILs, negated or not. A false FAIL on a disclaimer
# ("we do not call it safe") is the intended safe direction; no negation heuristic can be
# trusted ("no doubt it is safe" certifies), so the author rewords the line.
CERT = re.compile(r"\b(safe|unbiased|fair|compliant)\b", re.I)
PCT = re.compile(r"\d+(\.\d+)?\s*%")
DATE = re.compile(r"\b(19|20)\d\d\b|\bversion\b|\bv\d|\b\d+(\.\d+)+\b", re.I)
REGIMES = ("EU AI Act", "ISO/IEC 42001", "NIST AI RMF")
CARD = ("intended_use", "out_of_scope_uses", "subgroup_performance", "limits", "known_gaps",
        "owner", "model_version", "data_composition", "provenance", "consent")
ROW = ("harm", "positive_control", "negative_control", "sliced_by", "metric", "threshold_owner", "stop_condition")
SWEEPS = ("prompt_injection", "data_leakage", "excess_agency")


def rows(v, key):
    if not isinstance(v, list) or not all(isinstance(r, dict) and r for r in v):
        raise ValueError(f"{key} must be a list of non-empty objects")
    return v


def strs(v, key):
    if not isinstance(v, list) or not all(isinstance(s, str) and s.strip() for s in v):
        raise ValueError(f"{key} must be a list of non-blank strings")
    return v


def flag(r, key):
    if not isinstance(r.get(key), bool):
        raise ValueError(f"{key} must be true or false")
    return r[key]


def blank(r, key):
    v = r.get(key)
    if v is not None and not isinstance(v, str):
        raise ValueError(f"{key} must be a string")
    return not (v or "").strip()


def inventory(v, d):
    rs = rows(v, "harm_inventory")
    p = [] if rs else ["empty inventory"]
    return p + [f"{r.get('harm') or '?'}: no {k}" for r in rs for k in ("harm", "affected", "worst_case") if blank(r, k)]


def owners(v, d):
    rs = rows(v, "harm_inventory")
    return [f"{r.get('harm') or '?'}: no owner" for r in rs if blank(r, "owner")] if rs else None


def rereview(v, d):
    got = [s.lower() for s in strs(v, "rereview_on")]
    return [f"no {w}" for w in ("feature", "model", "data") if w not in got]


def gates(v, d):
    rs = rows(v, "actions")
    return [f"{r.get('action') or '?'}: high stakes, no human_gate" for r in rs
            if flag(r, "high_stakes") and not flag(r, "human_gate")] if rs else None


def metrics(v, d):
    rs = rows(v, "metrics")
    if any(blank(r, "name") for r in rs):
        raise ValueError("metrics rows need a name")
    if any(r.get("measured") is not None and not isinstance(r["measured"], bool) for r in rs):
        raise ValueError("measured must be true or false")
    return [f"{r['name']}: value stated, not measured" for r in rs
            if r.get("measured") is not True and r.get("value") is not None] if rs else None


def test_rows(v, d):
    rs, p = rows(v, "test_rows"), []
    if not rs and "harm_inventory" not in d:
        return None
    for r in rs:
        h = r.get("harm") or "?"
        p += [f"{h}: no {k}" for k in ROW if blank(r, k)]
        t = r.get("threshold")
        if isinstance(t, bool) or not isinstance(t, (int, float)):
            p.append(f"{h}: threshold must be a number")
        elif not math.isfinite(t):
            raise ValueError("threshold must be finite")
        elif t == 0 and r.get("gated_irreversible") is not True:
            p.append(f"{h}: zero tolerance but not gated_irreversible")
    if "harm_inventory" in d:
        have = {r.get("harm") for r in rs}
        p += [f"{r.get('harm') or '?'}: no test row" for r in rows(d["harm_inventory"], "harm_inventory")
              if r.get("harm") not in have]
    return p


def sweeps(v, d):
    if not isinstance(v, dict):
        raise ValueError("sweeps must be an object")
    return [f"{k} not swept" for k in SWEEPS if v.get(k) is not True]


def claims(v, d):
    ss = strs(v, "claims_about_system")
    return [f"certifies: {s}" for s in ss if CERT.search(s)] if ss else None


def pct(v, d):
    ss = strs(v, "confidence_displays")
    return [f"bare percentage: {s}" for s in ss if PCT.search(s)] if ss else None


def tiers(v, d):
    if not isinstance(v, dict) or not all(isinstance(x, str) for x in v.values()):
        raise ValueError("confidence_tiers must map tier to a definition string")
    return (["no tiers"] if not v else []) + [f"{k}: no definition" for k, x in v.items() if not x.strip()]


def override(v, d):
    if not isinstance(v, bool):
        raise ValueError("override_offered must be true or false")
    return [] if v else ["no override"]


def card(v, d):
    if v is None:
        return ["no card"]
    if not isinstance(v, dict):
        raise ValueError("card must be an object or null")
    return [f"card: no {k}" for k in CARD if blank(v, k)]


def disclosure(v, d):
    if not isinstance(v, bool):
        raise ValueError("disclosure_recommended must be true or false")
    return [] if v else ["disclosure not recommended"]


def legal(v, d):
    rs = rows(v, "legal_questions")
    if any(blank(r, "question") for r in rs):
        raise ValueError("legal_questions rows need a question")
    return [f"{r['question']}: not routed" for r in rs if blank(r, "routed_to")] if rs else None


def regimes(v, d):
    s = strs(v, "regimes_named")
    # an entry that negates the regime ("not the EU AI Act") does not name it
    return [f"missing {n}" for n in REGIMES if not any(n.lower() in x.lower() and not NEG.search(x) for x in s)]


def no_date(v, d):
    return [f"date or version: {x}" for x in strs(v, "regimes_named") if DATE.search(x)]


# name, input key, SKILL.md / full-map.md sentence mechanized (verbatim), fn
CHECKS = [
    ("inventory", "harm_inventory", "For each, record who is affected and the worst realistic case. An empty inventory is not a pass.", inventory),
    ("owners", "harm_inventory", "Name an owner for each shipped output-harm", owners),
    ("rereview", "rereview_on", "re-review when the feature, model or data changes", rereview),
    ("human_gate", "actions", "full autonomous execution of it is the failure", gates),
    ("unmeasured_metric", "metrics", "A bias, accuracy or hallucination rate that was not measured is `UNVERIFIED`", metrics),
    ("test_rows", "test_rows", "One test row per harm.", test_rows),
    ("sweeps", "sweeps", "Also sweep prompt injection, leakage of other users' data and excess agency.", sweeps),
    ("never_certify", "claims_about_system", 'Do not declare a system "safe", "unbiased", "fair" or "compliant"', claims),
    ("bare_percentage", "confidence_displays", 'never a bare "87%" from the model', pct),
    ("tiers_defined", "confidence_tiers", "each tier defined and shown as text plus a cue", tiers),
    ("override", "override_offered", "offer an override", override),
    ("card", "card", "No card is a transparency finding", card),
    ("disclosure", "disclosure_recommended", "Recommend disclosure as a control", disclosure),
    ("legal_routed", "legal_questions", "goes to counsel", legal),
    ("regimes", "regimes_named", "Name the EU AI Act, ISO/IEC 42001 and NIST AI RMF", regimes),
    ("no_date", "regimes_named", "never encode a date or version", no_date),
]


def run(d):
    """Return (output lines, exit code) for one parsed input object; raise ValueError on bad input."""
    if not isinstance(d, dict):
        raise ValueError("input must be a JSON object")
    lines, fail, ran = [], False, 0
    for name, key, quote, fn in CHECKS:
        p = fn(d[key], d) if key in d else None
        if p is None:
            why = f"empty {key}" if key in d else f"no {key}"
            lines.append(f'SKIP {name}: {why} in input | rule: "{quote}"')
            continue
        ran += 1
        fail |= bool(p)
        lines.append(f'{"FAIL" if p else "PASS"} {name}{": " + "; ".join(p) if p else ""} | rule: "{quote}"')
    if not ran:
        lines.append("INCONCLUSIVE no checkable key in input; see the key list in the script docstring")
    return lines, 3 if not ran else 1 if fail else 0


def main(argv):
    try:
        with (open(argv[0], encoding="utf-8") if argv else sys.stdin) as f:
            lines, rc = run(json.load(f))
    except (ValueError, KeyError, OverflowError, TypeError, OSError, RecursionError) as e:
        print(f"ERROR {e}")
        return 2
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
