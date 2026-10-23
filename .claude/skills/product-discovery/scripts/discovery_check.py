#!/usr/bin/env python3
"""Deterministic checks of a product-discovery plan or readout against rules SKILL.md states verbatim.

Usage: discovery_check.py [input.json]   (stdin when no path)

Input is one JSON object; every value is bound by key name. A section is an object
or a list of objects. An absent section is SKIPped; once a section is present, a key
a rule needs and a row omits (or sets null) is a FAIL, never a SKIP or a sibling's PASS:
  tests[]:    assumption, test, metric (text); behavioral, thresholds_fixed_before_run,
              no_figure_given, proposed (bool); kill_threshold, sample_size (number);
              deadline, basis, decision_rule (text). A blank figure (kill_threshold, sample_size)
              is a FAIL unless the row sets no_figure_given true; a deadline is never exempt.
              A row needs basis and decision_rule unless it sets proposed false.
  gate:       assumptions[{name, impact, uncertainty}], riskiest (a name),
              build_proceeds, riskiest_test_run (bool).
  ice[]:      impact, confidence, ease, score (number, or null = blank); user_supplied (bool).
              Rows are expected highest score first.
  pmf:        declared (bool); survey_share, survey_min_share (0..1); retention_flattening (bool).
              The only survey limit is the survey_min_share the input states.
  claims[]:   text, user_supplied (bool; absent counts as not supplied).
  unknowns[]: routed, concluded (bool).
  non_goals[]: reason, stage (text), user_chosen (bool).
  requests[]: touches_non_goal, flagged (bool).
  reference:  core_loop_is_acceptance, judged_as_non_pilot_user, first_pilot_is_team_workflow (bool).
No limit is built in. Free text is never parsed; only the explicit booleans, numbers and
non-empty strings above decide a result. Arithmetic is exact (Fraction).

Exit 0 every checked rule holds, 1 any FAIL, 2 bad input ("ERROR <reason>": wrong type,
empty object, empty string, empty list, non-object list item), 3 every check SKIPped
(prints INCONCLUSIVE). Each line quotes the SKILL.md text it mechanizes.
Side effects: none beyond reading the input and printing.
"""
import json
import math
import sys
from fractions import Fraction

I3 = ("impact", "confidence", "ease")


def val(r, k, kind):
    """Value of key k as text, flag or num; None when absent or null; ValueError on a wrong type."""
    v = r.get(k)
    if v is None:
        return None
    if kind == "text" and not (isinstance(v, str) and v.strip()):
        raise ValueError(f"{k} must be a non-empty string")
    if kind == "flag" and not isinstance(v, bool):
        raise ValueError(f"{k} must be true or false")
    if kind == "num":
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
            raise ValueError(f"{k} must be a finite number")
        return Fraction(str(v))
    return v


def has(r, k, kind):
    return val(r, k, kind) is not None


def req(r, k, kind):
    v = val(r, k, kind)
    if v is None:
        raise ValueError(f"missing key {k}")
    return v


def rows(d, sect):
    """Rows of a section: an object or a non-empty list of non-empty objects; [] when absent."""
    v = d.get(sect)
    if v is None:
        return []
    v = [v] if isinstance(v, dict) else v
    if not isinstance(v, list) or not v or not all(isinstance(r, dict) and r for r in v):
        raise ValueError(f"{sect} must be a non-empty object or a non-empty list of non-empty objects")
    return v


def one(d, sect):
    r = rows(d, sect)
    if len(r) > 1:
        raise ValueError(f"{sect} must be one object")
    return r[0] if r else {}


def per_row(sect, test):
    """Check running test(row) per row: True ok, False bad, None not applicable."""
    def fn(d):
        seen, bad = 0, []
        for i, r in enumerate(rows(d, sect)):
            ok = test(r)
            if ok is not None:
                seen += 1
                bad += [] if ok else [f"{sect}[{i}]"]
        return seen, bad
    return fn


def want(sect, key, expected):
    """Row check: the bool `key` must equal expected; an absent value fails (fail closed)."""
    return per_row(sect, lambda r: val(r, key, "flag") is expected)


def slots(nums, texts=()):
    """Test-row check: every text slot filled; a blank numeric figure is skipped only when no_figure_given is true."""
    def t(r):
        blank_ok = val(r, "no_figure_given", "flag")
        figs = [has(r, k, "num") for k in nums]
        if not all([has(r, k, "text") for k in texts]):
            return False
        return True if all(figs) else None if blank_ok else False
    return per_row("tests", t)


def share(p, k):
    v = val(p, k, "num")
    if v is not None and not 0 <= v <= 1:
        raise ValueError(f"{k} must be between 0 and 1")
    return v


def assumptions(d):
    g, out = one(d, "gate"), {}
    for a in rows(g, "assumptions"):
        n = req(a, "name", "text")
        if n in out:
            raise ValueError(f"duplicate assumption {n}")
        out[n] = req(a, "impact", "num") * req(a, "uncertainty", "num")
    return g, out


def every_assumption_tested(d):
    _, a = assumptions(d)
    tested = {val(r, "assumption", "text") for r in rows(d, "tests")} - {None}
    return (len(a), [n for n in a if n not in tested]) if a else (0, [])


def riskiest_is_top(d):
    g, a = assumptions(d)
    r = val(g, "riskiest", "text")
    if not a and r is None:
        return 0, []
    if not a or r is None:  # a ranking without a named riskiest, or a riskiest with no ranking
        return 1, ["gate"]
    return 1, [] if r in a and a[r] == max(a.values()) else [f"riskiest {r}"]


def no_build_before_test(d):
    g = one(d, "gate")
    b, t = val(g, "build_proceeds", "flag"), val(g, "riskiest_test_run", "flag")
    return (0, []) if b is None else (1, ["gate"] if b and t is not True else [])


def ice_ordered(d):
    s = [x for x in (val(r, "score", "num") for r in rows(d, "ice")) if x is not None]
    if len(s) < 2:
        return 0, []
    return len(s), [] if all(a >= b for a, b in zip(s, s[1:])) else ["ice order"]


def pmf_needs_data(d):
    p = one(d, "pmf")
    if not val(p, "declared", "flag"):
        return 0, []
    ok = share(p, "survey_share") is not None and val(p, "retention_flattening", "flag") is True
    return 1, [] if ok else ["pmf"]


def pmf_meets_survey_limit(d):
    p = one(d, "pmf")
    s, m = share(p, "survey_share"), share(p, "survey_min_share")
    if not val(p, "declared", "flag") or m is None:
        return 0, []
    return 1, [] if s is not None and s >= m else ["pmf"]


def ice_user_supplied(r):
    """A number needs an explicit user_supplied true; an absent flag next to a number fails."""
    return val(r, "user_supplied", "flag") is True or not any([has(r, k, "num") for k in I3])


def collision_flagged(r):
    t, f = val(r, "touches_non_goal", "flag"), val(r, "flagged", "flag")
    return t is not None and (not t or f is True)


def ice_product(r):
    if not all([has(r, k, "num") for k in I3]):
        return None
    s = val(r, "score", "num")  # all three inputs given: a missing score is a failure, not a pass
    return s is not None and s == val(r, "impact", "num") * val(r, "confidence", "num") * val(r, "ease", "num")


# name, SKILL.md text mechanized (verbatim), fn(d) -> (rows checked, failing ids)
CHECKS = [
    ("test_row_slots_named",
     "the assumption, its cheapest behavioral test",
     per_row("tests", lambda r: all([has(r, "assumption", "text"), has(r, "test", "text"), has(r, "metric", "text")]))),
    ("test_is_behavioral", "not a survey of intent", want("tests", "behavioral", True)),
    ("test_has_kill_threshold", "A test with no kill threshold cannot fail, so it is not a test",
     slots(("kill_threshold",))),
    ("test_has_sample_and_deadline", "a sample size and a deadline", slots(("sample_size",), ("deadline",))),
    ("test_fixed_before_run", "all fixed before the test runs", want("tests", "thresholds_fixed_before_run", True)),
    ("proposal_shows_basis_and_rule", "show the basis, add the go / narrow / drop rule",
     per_row("tests", lambda r: all([has(r, "basis", "text"), has(r, "decision_rule", "text")])
             if val(r, "proposed", "flag") is not False else None)),
    ("gate_every_assumption_tested", "Every ranked assumption gets a test row", every_assumption_tested),
    ("gate_riskiest_is_top_ranked", "rank by impact × uncertainty", riskiest_is_top),
    ("gate_no_build_before_test", "If that test has not been run, refuse to build yet", no_build_before_test),
    ("ice_inputs_user_supplied", "Never print a reach/impact/confidence number the user did not supply",
     per_row("ice", ice_user_supplied)),
    ("ice_blank_inputs_unscored", "A scoring table has blanks, not guesses",
     per_row("ice", lambda r: all([has(r, k, "num") for k in I3]) if has(r, "score", "num") else None)),
    ("ice_score_is_product", "ICE (Impact × Confidence × Ease)", per_row("ice", ice_product)),
    ("ice_ordered", "the skill does the arithmetic and orders the list", ice_ordered),
    ("pmf_declared_needs_data", "PMF is never declared from a conversation, demo or vibes", pmf_needs_data),
    ("pmf_meets_stated_survey_limit", 'the "very-disappointed" survey (verify the exact figure before asserting it)',
     pmf_meets_survey_limit),
    ("claims_user_supplied",
     "interview findings, customer quotes, personas, market size / TAM, competitor facts, adoption numbers or a PMF verdict",
     per_row("claims", lambda r: has(r, "text", "text") and val(r, "user_supplied", "flag") is True)),
    ("unknown_is_routed",
     "go to real research, the owner or a licensed professional as a routed open question",
     want("unknowns", "routed", True)),
    ("unknown_not_concluded", "never conclude it", want("unknowns", "concluded", False)),
    ("non_goal_recorded_with_reason_and_stage", '("not X yet, because [reason]")',
     per_row("non_goals", lambda r: all([has(r, "reason", "text"), has(r, "stage", "text")]))),
    ("non_goal_user_chosen", "set a non-goal the user did not choose", want("non_goals", "user_chosen", True)),
    ("non_goal_collision_flagged", "A request touching one gets one line",
     per_row("requests", collision_flagged)),
    ("reference_core_loop_is_acceptance", "names the reference's core loop as acceptance",
     want("reference", "core_loop_is_acceptance", True)),
    ("reference_judged_as_non_pilot_user", "judge the result against the reference as a non-pilot user",
     want("reference", "judged_as_non_pilot_user", True)),
    ("first_pilot_is_team_workflow", "The first pilot is a workflow the team itself runs",
     want("reference", "first_pilot_is_team_workflow", True)),
]


def utf8(x):
    """Reject any string or key that cannot be encoded as UTF-8 (a lone surrogate), so printing never crashes."""
    if isinstance(x, str):
        try:
            x.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("input has a string that is not valid UTF-8 text") from None
    elif isinstance(x, list):
        [utf8(i) for i in x]
    elif isinstance(x, dict):
        [(utf8(k), utf8(v)) for k, v in x.items()]


def run(d):
    """Return (output lines, exit code) for one parsed input object; raise ValueError on bad input."""
    if not isinstance(d, dict) or not d:
        raise ValueError("input must be a non-empty JSON object")
    utf8(d)
    lines, fail, ran = [], False, 0
    for name, quote, fn in CHECKS:
        seen, bad = fn(d)
        ran += bool(seen)
        fail |= bool(bad)
        status = "FAIL" if bad else "PASS" if seen else "SKIP"
        detail = ", ".join(bad) if bad else f"{seen} checked" if seen else "no input for this rule"
        lines.append(f'{status} {name}: {detail} | mechanizes: "{quote}"')
    if not ran:
        lines.append("INCONCLUSIVE no checkable section; see the script header for the keys")
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
