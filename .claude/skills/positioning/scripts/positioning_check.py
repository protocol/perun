#!/usr/bin/env python3
"""Deterministic checks of a positioning draft against rules positioning already states.

Usage: positioning_check.py [input.json]   (stdin when no path)

Input is one JSON object; every value is bound by key name. A check runs only
when all its keys are present and non-blank, otherwise it prints SKIP; this
script invents no threshold and no market fact. Keys:
  statement_text            str   the drafted positioning statement
  segment, alternative      str   the statement's segment and alternative
  statement + supplied      object of element -> text, and the list of element names the user supplied
  differentiators           list of {claim, proof}
  core_messages             list of str (message house)
  pillars                   list of {pillar, proof}
  market_facts              list of {kind, value, user_supplied (bool)}
  name_cleared_by_professional  bool  true when a trademark professional cleared the name; false FAILs
  name_clearance            str   what the draft says about the name; any non-blank text FAILs unless the bool is true (no wording match); non-string is ERROR
  stage + artifacts         str, and list of str; pre-PMF fails an artifact naming a brand system or messaging bible
  (statement_text must start with "Hypothesis", case-insensitive)
  buyer_reactions           list of {reaction, gathered_from}
Every output line quotes the SKILL.md / references/full-map.md text the check enforces.

Exit 0 no FAIL, 1 any FAIL, 2 bad input ("ERROR <reason>"), 3 every check
SKIPped (prints INCONCLUSIVE). Side effects: none beyond reading input and printing.
"""
import json
import re
import sys

MARK = "UNVERIFIED — needs proof"


def blank(v):
    return v is None or v == [] or (isinstance(v, str) and not v.strip())


def text(v, what):
    if not isinstance(v, str):
        raise ValueError(f"{what} must be a string")
    return v.strip()


def rows(d, key, fields):
    """Rows of list `key` as tuples of stripped strings, in `fields` order."""
    if not isinstance(d[key], list):
        raise ValueError(f"{key} must be a list")
    out = []
    for r in d[key]:
        if not isinstance(r, dict):
            raise ValueError(f"{key} items must be objects")
        row = tuple(text(r.get(f, ""), f"{key}.{f}") for f in fields)
        if not row[0]:
            raise ValueError(f"{key} items need a non-blank {fields[0]}")
        out.append(row)
    return out


def generic(d, key, bad):
    v = text(d[key], key).lower().rstrip(". ").removeprefix("unlike ").strip()
    return [f'{key} "{d[key].strip()}" is generic'] if v in bad else []


def unproven(d, key, name, fields):
    return [f"{name} {c!r} has no proof and no {MARK}" for c, p in rows(d, key, fields) if c and not p and MARK not in c]


def elements(d):
    """Statement elements the user did not supply, as (name, text)."""
    return [(k, text(v, f"statement.{k}")) for k, v in d["statement"].items() if k not in d["supplied"]]


def assumed(d):
    return [f"{k} not supplied by the user and not tagged [ASSUMED]" for k, v in elements(d) if "[ASSUMED]" not in v]


def invented(d):
    return [f"{k} not supplied but contains a number or quote" for k, v in elements(d) if re.search(r'[0-9"“”]', v)]


def facts(d):
    out = []
    for r in d["market_facts"] if isinstance(d["market_facts"], list) else [None]:
        if not isinstance(r, dict) or not isinstance(r.get("user_supplied"), bool):
            raise ValueError("market_facts items must be objects with a boolean user_supplied")
        if text(r.get("value", ""), "value") and not r["user_supplied"]:
            out.append(f"{text(r.get('kind', ''), 'kind') or 'market fact'} filled in but not supplied by the user")
    return out


def pro(d):
    """The explicit boolean name_cleared_by_professional, or None when absent."""
    v = d.get("name_cleared_by_professional")
    if v is not None and not isinstance(v, bool):
        raise ValueError("name_cleared_by_professional must be true or false")
    return v


def cleared_by_pro(d):
    return [] if pro(d) else ["name_cleared_by_professional is false"]


def clearance_claim(d):
    # no wording heuristic: any non-blank name_clearance text is a claim and needs the professional's confirmation
    text(d["name_clearance"], "name_clearance")
    return ["name_clearance text present without name_cleared_by_professional true"] if pro(d) is not True else []


def hypothesis(d):
    return [] if re.match(r"hypothesis\b(?!-)", text(d["statement_text"], "statement_text").lower()) else ["statement_text does not start with Hypothesis"]


def stage(d):
    if not isinstance(d["artifacts"], list):
        raise ValueError("artifacts must be a list")
    pre = re.sub(r"[\s_-]", "", text(d["stage"], "stage").lower()) == "prepmf"
    arts = [(a, re.sub(r"[\s_-]+", " ", text(a, "artifact").lower())) for a in d["artifacts"]]  # types checked at every stage
    return [f"pre-PMF draft proposes {a!r}" for a, n in arts if pre and ("brand system" in n or "messaging bible" in n)]


def one_core(d):
    if not isinstance(d["core_messages"], list):
        raise ValueError("core_messages must be a list")
    for m in d["core_messages"]:
        if not text(m, "core_messages item"):
            raise ValueError("core_messages items must be non-blank strings")
    n = len(d["core_messages"])
    return [] if n == 1 else [f"{n} core messages"]


def reactions(d):
    return [f"reaction {r!r} has no gathered_from" for r, g in rows(d, "buyer_reactions", ("reaction", "gathered_from")) if r and not g]


# name, required keys, verbatim rule text (SKILL.md or references/full-map.md), fn(d) -> list of problems
CHECKS = [
    ("hypothesis", ("statement_text",), "Label it a hypothesis.", hypothesis),
    ("segment", ("segment",), 'a nameable buyer in a situation, not a demographic or "teams"', lambda d: generic(d, "segment", ("teams",))),
    ("alternative", ("alternative",), '"Unlike the competition" is a blank', lambda d: generic(d, "alternative", ("the competition",))),
    ("assumed_tags", ("statement", "supplied"), "tag every element the user did not supply `[ASSUMED]`", assumed),
    ("no_invented_specifics", ("statement", "supplied"), "Never a named vendor, number or quote", invented),
    ("differentiator_proof", ("differentiators",),
     "Differentiator: one user-supplied proof point plus what leaving the alternative costs; none is `UNVERIFIED — needs proof`",
     lambda d: unproven(d, "differentiators", "differentiator", ("claim", "proof"))),
    ("one_core_message", ("core_messages",), "One core message", one_core),
    ("pillar_proof", ("pillars",), "no proof is `UNVERIFIED — needs proof`", lambda d: unproven(d, "pillars", "pillar", ("pillar", "proof"))),
    ("market_facts", ("market_facts",), "No TAM, competitor claim, customer quote, or outcome number the user did not supply", facts),
    ("clearance_by_professional", ("name_cleared_by_professional",),
     "Trademark / domain clearance is routed to a professional, never asserted.", cleared_by_pro),
    ("clearance_claim", ("name_clearance",), "trademark / domain availability or clearance", clearance_claim),
    ("stage", ("stage", "artifacts"), "a brand system or messaging bible earlier is premature scaling", stage),
    ("buyer_reactions", ("buyer_reactions",), "never report a reaction that was not gathered", reactions),
]


def run(d):
    """Return (output lines, exit code) for one parsed input object; raise ValueError on bad input."""
    if not isinstance(d, dict):
        raise ValueError("input must be a JSON object")
    # type-check before any SKIP: an empty or mistyped statement/supplied is bad input, not an absent one
    if d.get("statement") is not None and not (isinstance(d["statement"], dict) and d["statement"]):
        raise ValueError("statement must be a non-empty object")
    if d.get("supplied") is not None and not isinstance(d["supplied"], list):
        raise ValueError("supplied must be a list")
    lines, fail, ran = [], False, 0
    for name, keys, quote, fn in CHECKS:
        # an empty `supplied` list is an answer (the user supplied nothing), not an absent input
        miss = [k for k in keys if blank(d.get(k)) and not (k == "supplied" and d.get(k) == [])]
        if miss:
            lines.append(f'SKIP {name}: no {", ".join(miss)} in input | rule: "{quote}"')
            continue
        ran += 1
        bad = fn(d)
        fail |= bool(bad)
        lines.append(f'{"FAIL" if bad else "PASS"} {name}: {"; ".join(bad) or "ok"} | rule: "{quote}"')
    if not ran:
        lines.append("INCONCLUSIVE no checkable key in input; see the header of positioning_check.py")
    return lines, 3 if not ran else 1 if fail else 0


def main(argv):
    try:
        with (open(argv[0]) if argv else sys.stdin) as f:
            lines, rc = run(json.load(f))
    except (ValueError, KeyError, RecursionError, OSError) as e:
        print(f"ERROR {e}")
        return 2
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
