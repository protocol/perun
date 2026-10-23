#!/usr/bin/env python3
"""Tests for product-discovery/scripts/discovery_check.py: one FAIL case per rule, SKIP/INCONCLUSIVE, bad input,
quote-is-verbatim guard. Every expected value is hardcoded; fictional data, offline, every subprocess has a timeout."""
import contextlib
import copy
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / ".claude/skills/product-discovery"
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import discovery_check as D  # noqa: E402

# One input that satisfies every rule; each FAIL case below breaks exactly one thing in it.
GOOD = {
    "tests": [
        {"assumption": "Buyers pay for X", "test": "fake door", "metric": "signups", "kill_threshold": 5,
         "sample_size": 50, "deadline": "2026-12-01", "behavioral": True, "thresholds_fixed_before_run": True,
         "proposed": True, "basis": "10% of 50 visitors", "decision_rule": "go at 10, narrow at 5, drop below 5"},
        {"assumption": "Users can onboard", "test": "concierge", "metric": "completions", "kill_threshold": 3,
         "sample_size": 10, "deadline": "2026-12-15", "behavioral": True, "thresholds_fixed_before_run": True,
         "proposed": False},
    ],
    "gate": {"assumptions": [{"name": "Buyers pay for X", "impact": 9, "uncertainty": 8},
                             {"name": "Users can onboard", "impact": 5, "uncertainty": 4}],
             "riskiest": "Buyers pay for X", "build_proceeds": False, "riskiest_test_run": False},
    "ice": [{"impact": 8, "confidence": 5, "ease": 2, "score": 80, "user_supplied": True},
            {"impact": 3, "confidence": 3, "ease": 3, "score": 27, "user_supplied": True},
            {"impact": None, "confidence": None, "ease": None, "score": None, "user_supplied": True}],
    "pmf": {"declared": True, "survey_share": 0.45, "survey_min_share": 0.4, "retention_flattening": True},
    "claims": [{"text": "Interviewee 3 said they export weekly", "user_supplied": True}],
    "unknowns": [{"text": "market size", "routed": True, "concluded": False}],
    "non_goals": [{"reason": "demand untested", "stage": "prototype", "user_chosen": True}],
    "requests": [{"touches_non_goal": True, "flagged": True}],
    "reference": {"core_loop_is_acceptance": True, "judged_as_non_pilot_user": True, "first_pilot_is_team_workflow": True},
}


def run(d):
    with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
        json.dump(d, f)
        f.flush()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = D.main([f.name])
    return rc, out.getvalue()


def mutated(fn):
    d = copy.deepcopy(GOOD)
    fn(d)
    return d


def status(out, name):
    m = re.search(rf"^(PASS|FAIL|SKIP) {name}:", out, re.M)
    return m.group(1) if m else None


class Baseline(unittest.TestCase):
    def test_good_passes_all_24_rules(self):
        rc, out = run(GOOD)
        self.assertEqual(rc, 0, out)
        self.assertEqual(len(out.splitlines()), 24)
        self.assertEqual(len(re.findall(r"^PASS ", out, re.M)), 24)

    def test_quotes_are_verbatim_skill_text(self):
        skill = re.sub(r"\s+", " ", (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))
        _, out = run(GOOD)
        quotes = re.findall(r' \| mechanizes: "(.*)"$', out, re.M)
        self.assertEqual(len(quotes), 24)
        for q in quotes:
            self.assertIn(q, skill)

    def test_cli_stdin_subprocess(self):
        p = subprocess.run([sys.executable, "-B", str(SKILL_DIR / "scripts/discovery_check.py")],
                           input=json.dumps(GOOD), capture_output=True, text=True, timeout=60)
        self.assertEqual((p.returncode, p.stdout.count("PASS "), p.stderr), (0, 24, ""))

    def test_reads_stdin_without_path(self):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(json.dumps(GOOD))), contextlib.redirect_stdout(out):
            self.assertEqual(D.main([]), 0)


def _set(path, value):
    def f(d):
        cur = d
        for k in path[:-1]:
            cur = cur[k]
        cur[path[-1]] = value
    return f


def _del(path):
    def f(d):
        cur = d
        for k in path[:-1]:
            cur = cur[k]
        del cur[path[-1]]
    return f


def _all(*fns):
    def f(d):
        for fn in fns:
            fn(d)
    return f


def _swap_ice(d):
    d["ice"][0], d["ice"][1] = d["ice"][1], d["ice"][0]


def _add_assumption(d):
    d["gate"]["assumptions"].append({"name": "Nobody tested this", "impact": 1, "uncertainty": 1})


# (rule name, mutation that breaks only that rule, expected failing id text)
FAIL_CASES = [
    ("test_row_slots_named", _del(["tests", 0, "metric"]), "tests[0]"),
    ("test_is_behavioral", _set(["tests", 1, "behavioral"], False), "tests[1]"),
    ("test_has_kill_threshold", _set(["tests", 0, "kill_threshold"], None), "tests[0]"),
    ("test_has_sample_and_deadline", _del(["tests", 1, "sample_size"]), "tests[1]"),
    ("test_has_sample_and_deadline", _set(["tests", 0, "deadline"], None), "tests[0]"),
    ("test_fixed_before_run", _set(["tests", 0, "thresholds_fixed_before_run"], False), "tests[0]"),
    ("proposal_shows_basis_and_rule", _del(["tests", 0, "decision_rule"]), "tests[0]"),
    ("proposal_shows_basis_and_rule", _del(["tests", 0, "basis"]), "tests[0]"),
    ("gate_every_assumption_tested", _add_assumption, "Nobody tested this"),
    ("gate_riskiest_is_top_ranked", _set(["gate", "riskiest"], "Users can onboard"), "riskiest Users can onboard"),
    ("gate_riskiest_is_top_ranked", _set(["gate", "riskiest"], "Not in the list"), "riskiest Not in the list"),
    ("gate_no_build_before_test", _set(["gate", "build_proceeds"], True), "gate"),
    ("ice_inputs_user_supplied", _set(["ice", 0, "user_supplied"], False), "ice[0]"),
    ("ice_blank_inputs_unscored", _set(["ice", 2, "score"], 5), "ice[2]"),
    ("ice_score_is_product", _set(["ice", 0, "score"], 81), "ice[0]"),
    ("ice_ordered", _swap_ice, "ice order"),
    ("pmf_declared_needs_data", _all(_set(["pmf", "survey_share"], None), _del(["pmf", "survey_min_share"])), "pmf"),
    ("pmf_declared_needs_data", _set(["pmf", "retention_flattening"], False), "pmf"),
    ("pmf_meets_stated_survey_limit", _set(["pmf", "survey_share"], 0.39), "pmf"),
    ("test_is_behavioral", _del(["tests", 1, "behavioral"]), "tests[1]"),
    ("test_fixed_before_run", _del(["tests", 1, "thresholds_fixed_before_run"]), "tests[1]"),
    ("proposal_shows_basis_and_rule", _del(["tests", 1, "proposed"]), "tests[1]"),
    ("test_has_sample_and_deadline", _all(_set(["tests", 1, "no_figure_given"], True), _del(["tests", 1, "deadline"])),
     "tests[1]"),
    ("gate_riskiest_is_top_ranked", _del(["gate", "riskiest"]), "gate"),
    ("gate_no_build_before_test", _all(_set(["gate", "build_proceeds"], True), _del(["gate", "riskiest_test_run"])), "gate"),
    ("ice_inputs_user_supplied", _del(["ice", 0, "user_supplied"]), "ice[0]"),
    ("ice_score_is_product", _set(["ice", 0, "score"], None), "ice[0]"),
    ("ice_score_is_product", _del(["ice", 1, "score"]), "ice[1]"),
    ("unknown_is_routed", _del(["unknowns", 0, "routed"]), "unknowns[0]"),
    ("unknown_not_concluded", _del(["unknowns", 0, "concluded"]), "unknowns[0]"),
    ("non_goal_user_chosen", _del(["non_goals", 0, "user_chosen"]), "non_goals[0]"),
    ("non_goal_collision_flagged", _del(["requests", 0, "touches_non_goal"]), "requests[0]"),
    ("non_goal_collision_flagged", _del(["requests", 0, "flagged"]), "requests[0]"),
    ("reference_core_loop_is_acceptance", _del(["reference", "core_loop_is_acceptance"]), "reference[0]"),
    ("reference_judged_as_non_pilot_user", _del(["reference", "judged_as_non_pilot_user"]), "reference[0]"),
    ("first_pilot_is_team_workflow", _del(["reference", "first_pilot_is_team_workflow"]), "reference[0]"),
    ("claims_user_supplied", _set(["claims", 0, "user_supplied"], False), "claims[0]"),
    ("claims_user_supplied", _del(["claims", 0, "user_supplied"]), "claims[0]"),
    ("unknown_is_routed", _set(["unknowns", 0, "routed"], False), "unknowns[0]"),
    ("unknown_not_concluded", _set(["unknowns", 0, "concluded"], True), "unknowns[0]"),
    ("non_goal_recorded_with_reason_and_stage", _del(["non_goals", 0, "reason"]), "non_goals[0]"),
    ("non_goal_recorded_with_reason_and_stage", _del(["non_goals", 0, "stage"]), "non_goals[0]"),
    ("non_goal_user_chosen", _set(["non_goals", 0, "user_chosen"], False), "non_goals[0]"),
    ("non_goal_collision_flagged", _set(["requests", 0, "flagged"], False), "requests[0]"),
    ("reference_core_loop_is_acceptance", _set(["reference", "core_loop_is_acceptance"], False), "reference[0]"),
    ("reference_judged_as_non_pilot_user", _set(["reference", "judged_as_non_pilot_user"], False), "reference[0]"),
    ("first_pilot_is_team_workflow", _set(["reference", "first_pilot_is_team_workflow"], False), "reference[0]"),
]


class Rules(unittest.TestCase):
    def test_each_rule_fails_alone(self):
        for name, fn, ident in FAIL_CASES:
            with self.subTest(rule=name, ident=ident):
                rc, out = run(mutated(fn))
                self.assertEqual(rc, 1, out)
                self.assertRegex(out, rf"(?m)^FAIL {name}: .*{re.escape(ident)}")
                self.assertEqual(len(re.findall(r"^FAIL ", out, re.M)), 1, out)

    def test_boundaries_pass(self):
        d = mutated(_set(["pmf", "survey_share"], 0.4))  # equal to the stated minimum
        tie = {"impact": 8, "confidence": 5, "ease": 2, "score": 80, "user_supplied": True}
        d["ice"] = [tie, dict(tie), {"impact": 0.1, "confidence": 3, "ease": 1, "score": 0.3, "user_supplied": True}]
        d["gate"]["assumptions"][1] = {"name": "Users can onboard", "impact": 12, "uncertainty": 6}  # ties 72 with 9 x 8
        d["gate"]["riskiest"] = "Users can onboard"
        rc, out = run(d)
        self.assertEqual(rc, 0, out)
        self.assertEqual(status(out, "ice_ordered"), "PASS")
        self.assertEqual(status(out, "gate_riskiest_is_top_ranked"), "PASS")

    def test_float_arithmetic_is_exact(self):
        rc, out = run({"ice": [{"impact": 0.1, "confidence": 3, "ease": 1, "score": 0.3, "user_supplied": True}]})
        self.assertEqual((rc, status(out, "ice_score_is_product")), (0, "PASS"))
        rc, out = run({"ice": [{"impact": 0.1, "confidence": 3, "ease": 1, "score": 0.30000000000000004, "user_supplied": True}]})
        self.assertEqual((rc, status(out, "ice_score_is_product")), (1, "FAIL"))

    def test_no_limit_is_invented(self):
        rc, out = run({"pmf": {"declared": True, "survey_share": 0.01, "retention_flattening": True}})
        self.assertEqual((rc, status(out, "pmf_declared_needs_data"), status(out, "pmf_meets_stated_survey_limit")),
                         (0, "PASS", "SKIP"))
        rc, out = run({"tests": [{"assumption": "A", "test": "t", "metric": "m", "kill_threshold": 0,
                                  "sample_size": 1, "deadline": "d"}]})
        self.assertEqual((status(out, "test_has_kill_threshold"), status(out, "test_has_sample_and_deadline")),
                         ("PASS", "PASS"))

    def test_undeclared_pmf_is_skipped_not_passed(self):
        rc, out = run({"pmf": {"declared": False, "survey_share": 0.1}})
        self.assertEqual((rc, status(out, "pmf_declared_needs_data")), (3, "SKIP"))

    def test_gate_build_allowed_after_test_run(self):
        d = mutated(_set(["gate", "build_proceeds"], True))
        d["gate"]["riskiest_test_run"] = True
        self.assertEqual(status(run(d)[1], "gate_no_build_before_test"), "PASS")

    def test_blank_figures_allowed_only_with_no_figure_given(self):
        row = {"assumption": "A", "test": "t", "metric": "m", "deadline": "2026-12-01"}
        names = ("test_has_kill_threshold", "test_has_sample_and_deadline")
        _, out = run({"tests": [row]})
        self.assertEqual([status(out, n) for n in names], ["FAIL", "FAIL"])
        _, out = run({"tests": [{**row, "no_figure_given": True}]})
        self.assertEqual([status(out, n) for n in names] + [status(out, "test_row_slots_named")],
                         ["SKIP", "SKIP", "PASS"])

    def test_no_figure_given_never_exempts_the_deadline(self):
        row = {"assumption": "A", "test": "t", "metric": "m", "no_figure_given": True}
        _, out = run({"tests": [row]})
        self.assertEqual((status(out, "test_has_kill_threshold"), status(out, "test_has_sample_and_deadline")),
                         ("SKIP", "FAIL"))
        _, out = run({"tests": [{**row, "kill_threshold": 3, "sample_size": 9}]})
        self.assertEqual(status(out, "test_has_sample_and_deadline"), "FAIL")

    def test_ranked_assumptions_without_any_named_test_row_fail(self):
        d = mutated(_all(_del(["tests", 0, "assumption"]), _del(["tests", 1, "assumption"])))
        rc, out = run(d)
        self.assertEqual((rc, status(out, "gate_every_assumption_tested")), (1, "FAIL"))
        self.assertIn("Buyers pay for X", out)
        d = mutated(_del(["tests"]))
        rc, out = run(d)
        self.assertEqual((rc, status(out, "gate_every_assumption_tested")), (1, "FAIL"))

    def test_riskiest_without_a_ranking_fails(self):
        rc, out = run({"gate": {"riskiest": "A"}})
        self.assertEqual((rc, status(out, "gate_riskiest_is_top_ranked")), (1, "FAIL"))

    def test_survey_limit_stated_but_share_missing_fails(self):
        d = mutated(_all(_set(["pmf", "survey_share"], None)))
        rc, out = run(d)
        self.assertEqual((rc, status(out, "pmf_declared_needs_data"), status(out, "pmf_meets_stated_survey_limit")),
                         (1, "FAIL", "FAIL"))

    def test_absent_ice_flag_with_numbers_fails_but_a_blank_row_passes(self):
        rc, out = run({"ice": [{"impact": 1, "confidence": 2, "ease": 3}]})
        self.assertEqual((rc, status(out, "ice_inputs_user_supplied")), (1, "FAIL"))
        rc, out = run({"ice": [{"impact": None, "confidence": None, "ease": None}]})
        self.assertEqual((rc, status(out, "ice_inputs_user_supplied")), (0, "PASS"))

    def test_missing_flag_is_not_rescued_by_a_passing_sibling(self):
        d = mutated(lambda d: d["unknowns"].append({"text": "competitor claims", "concluded": False}))
        rc, out = run(d)
        self.assertEqual((rc, status(out, "unknown_is_routed")), (1, "FAIL"))
        self.assertRegex(out, r"FAIL unknown_is_routed: unknowns\[1\]")

    def test_survey_of_intent_and_missing_flags_fail_not_skip(self):
        rc, out = run({"tests": [{"assumption": "A", "test": "t", "metric": "m", "no_figure_given": True}]})
        self.assertEqual((rc, status(out, "test_is_behavioral"), status(out, "test_fixed_before_run")),
                         (1, "FAIL", "FAIL"))


class Skip(unittest.TestCase):
    def test_absent_sections_skip_only_those(self):
        rc, out = run({"claims": GOOD["claims"]})
        self.assertEqual(rc, 0)
        self.assertEqual(len(re.findall(r"^SKIP ", out, re.M)), 23)
        self.assertEqual(status(out, "claims_user_supplied"), "PASS")

    def test_all_skip_is_inconclusive(self):
        rc, out = run({"unrelated": 1})
        self.assertEqual(rc, 3)
        self.assertIn("INCONCLUSIVE", out)
        self.assertNotIn("PASS", out)

    def test_null_section_and_key_are_absent(self):
        rc, out = run({"tests": None, "gate": None, "claims": [{"text": "x", "user_supplied": None}]})
        self.assertEqual((rc, status(out, "claims_user_supplied")), (1, "FAIL"))

    def test_binds_by_key_not_order(self):
        rc, _ = run(dict(reversed(list(GOOD.items()))))
        self.assertEqual(rc, 0)


class BadInput(unittest.TestCase):
    def err(self, d):
        rc, out = run(d)
        self.assertEqual(rc, 2, out)
        self.assertTrue(out.startswith("ERROR "), out)
        self.assertNotIn("Traceback", out)
        self.assertNotIn("PASS", out)

    def test_top_level_not_a_nonempty_object(self):
        for d in ([1, 2], {}, "x", 5, None, []):
            with self.subTest(d=d):
                self.err(d)

    def test_empty_or_wrong_section_shapes(self):
        for sect in ("tests", "gate", "ice", "pmf", "claims", "unknowns", "non_goals", "requests", "reference"):
            for bad in ({}, [], [{}], ["x"], [5], [[]], [None], "x", 7, [{"a": 1}, {}]):
                with self.subTest(sect=sect, bad=bad):
                    self.err({sect: bad})

    def test_two_objects_for_a_single_object_section(self):
        for sect in ("gate", "pmf"):
            self.err({sect: [{"declared": True}, {"declared": True}]})

    def test_empty_or_non_string_text(self):
        for key, bad in (("assumption", ""), ("assumption", "  "), ("test", 5), ("metric", ["x"]), ("deadline", ""),
                         ("basis", 1), ("decision_rule", True)):
            with self.subTest(key=key):
                self.err({"tests": [{key: bad, "proposed": True}]})
        self.err({"claims": [{"text": ""}]})
        self.err({"non_goals": [{"reason": "", "stage": "mvp"}]})
        self.err({"gate": {"assumptions": [{"name": "", "impact": 1, "uncertainty": 1}]}})

    def test_bad_numbers(self):
        for bad in ("5", True, [1], {"a": 1}, float("nan"), float("inf"), 10**400):
            with self.subTest(bad=repr(bad)[:20]):
                self.err({"tests": [{"kill_threshold": bad}]})
        self.err({"ice": [{"impact": "8", "confidence": 5, "ease": 2}]})
        self.err({"gate": {"assumptions": [{"name": "A", "impact": True, "uncertainty": 1}]}})

    def test_bad_flags(self):
        for bad in ("yes", 1, 0, [], {"a": 1}):
            with self.subTest(bad=bad):
                self.err({"tests": [{"behavioral": bad}]})
                self.err({"pmf": {"declared": bad}})

    def test_share_outside_unit_range(self):
        for k in ("survey_share", "survey_min_share"):
            for bad in (1.5, -0.1):
                self.err({"pmf": {"declared": True, k: bad}})

    def test_assumption_rows_incomplete_or_duplicated(self):
        self.err({"gate": {"assumptions": [{"name": "A", "impact": 1}]}})
        self.err({"gate": {"assumptions": [{"impact": 1, "uncertainty": 1}]}})
        self.err({"gate": {"assumptions": [{"name": "A", "impact": 1, "uncertainty": 1}] * 2}})
        self.err({"gate": {"assumptions": []}})

    def test_deeply_nested_json(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            f.write("[" * 200000)
            f.flush()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(D.main([f.name]), 2)
            self.assertTrue(out.getvalue().startswith("ERROR "))

    def test_bad_json_and_missing_file(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(D.main(["/nonexistent/in.json"]), 2)
        with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
            f.write("{nope")
            f.flush()
            with contextlib.redirect_stdout(out):
                self.assertEqual(D.main([f.name]), 2)
        self.assertEqual(out.getvalue().count("ERROR "), 2)

    def test_lone_surrogate_is_an_error_not_a_crash(self):
        for d in ({"gate": {"assumptions": [{"name": "A", "impact": 1, "uncertainty": 1}], "riskiest": "\ud800"}},
                  {"gate": {"assumptions": [{"name": "\ud800", "impact": 1, "uncertainty": 1},
                                            {"name": "\ud800", "impact": 1, "uncertainty": 1}]}},
                  {"claims": [{"text": "x\udfff", "user_supplied": True}]},
                  {"\ud800": 1}, {"unrelated": ["ok", ["\ud800"]]}):
            with self.subTest(d=repr(d)[:40]):
                self.err(d)

    def test_lone_surrogate_cli_has_no_traceback(self):
        doc = json.dumps({"gate": {"assumptions": [{"name": "A", "impact": 1, "uncertainty": 1}],
                                   "riskiest": "\ud800"}})
        p = subprocess.run([sys.executable, "-B", str(SKILL_DIR / "scripts/discovery_check.py")],
                           input=doc, capture_output=True, text=True, timeout=60)
        self.assertEqual((p.returncode, p.stdout.startswith("ERROR "), p.stderr), (2, True, ""))

    def test_cli_error_has_no_traceback(self):
        p = subprocess.run([sys.executable, "-B", str(SKILL_DIR / "scripts/discovery_check.py")],
                           input="{bad", capture_output=True, text=True, timeout=60)
        self.assertEqual((p.returncode, p.stdout.startswith("ERROR "), p.stderr), (2, True, ""))


if __name__ == "__main__":
    unittest.main()
