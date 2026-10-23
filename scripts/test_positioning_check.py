#!/usr/bin/env python3
"""Tests for positioning/scripts/positioning_check.py: one test per branch of every check, SKIP/INCONCLUSIVE, bad input, rule-quote drift guard. Expected values are hardcoded. Fictional data, offline, 10 s alarm per test."""
import contextlib
import io
import json
import signal
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude/skills/positioning"
sys.path.insert(0, str(SKILL / "scripts"))
import positioning_check as P  # noqa: E402

MARK = "UNVERIFIED — needs proof"
GOOD = {
    "statement_text": "Hypothesis: for solo bookkeepers who dread month-end, Acme Ledger is a close tool that cuts rework.",
    "segment": "solo bookkeeper at month-end close",
    "alternative": "a shared spreadsheet",
    "statement": {"segment": "solo bookkeeper", "alternative": "[ASSUMED] a shared spreadsheet", "benefit": "[ASSUMED] less rework"},
    "supplied": ["segment"],
    "differentiators": [{"claim": "auto-matching", "proof": "pilot notes from the user"}],
    "core_messages": ["Close the books without rework"],
    "pillars": [{"pillar": "speed", "proof": "shipped import"}, {"pillar": f"trust {MARK}", "proof": ""}],
    "market_facts": [{"kind": "TAM", "value": "", "user_supplied": False}, {"kind": "quote", "value": "works well", "user_supplied": True}],
    "name_cleared_by_professional": True,
    "name_clearance": "A trademark professional confirmed the name.",
    "stage": "pre-PMF",
    "artifacts": ["one-line value prop"],
    "buyer_reactions": [{"reaction": "liked it", "gathered_from": "3 calls the user ran"}],
}
NAMES = ["hypothesis", "segment", "alternative", "assumed_tags", "no_invented_specifics", "differentiator_proof", "one_core_message",
         "pillar_proof", "market_facts", "clearance_by_professional", "clearance_claim", "stage", "buyer_reactions"]
QUOTES = [
    "Label it a hypothesis.",
    'a nameable buyer in a situation, not a demographic or "teams"',
    '"Unlike the competition" is a blank',
    "tag every element the user did not supply `[ASSUMED]`",
    "Never a named vendor, number or quote",
    "Differentiator: one user-supplied proof point plus what leaving the alternative costs; none is `UNVERIFIED — needs proof`",
    "One core message",
    "no proof is `UNVERIFIED — needs proof`",
    "No TAM, competitor claim, customer quote, or outcome number the user did not supply",
    "Trademark / domain clearance is routed to a professional, never asserted.",
    "trademark / domain availability or clearance",
    "a brand system or messaging bible earlier is premature scaling",
    "never report a reaction that was not gathered",
]


def run_text(raw, via_file=False):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        if via_file:
            with tempfile.NamedTemporaryFile("w", suffix=".json") as f:
                f.write(raw)
                f.flush()
                rc = P.main([f.name])
        else:
            sys.stdin, old = io.StringIO(raw), sys.stdin  # stdin is always swapped: a test can never block on the terminal
            try:
                rc = P.main([])
            finally:
                sys.stdin = old
    return rc, out.getvalue()


def only(**kw):
    """Run GOOD with `kw` overriding."""
    return run_text(json.dumps({**GOOD, **kw}))


class Base(unittest.TestCase):
    def setUp(self):  # no test may block: fail after 10 s
        signal.signal(signal.SIGALRM, lambda *a: self.fail("test exceeded 10 s"))
        signal.alarm(10)

    def tearDown(self):
        signal.alarm(0)

    def fail_only(self, name, **kw):
        rc, out = only(**kw)
        self.assertEqual(rc, 1, out)
        self.assertIn(f"FAIL {name}:", out)
        self.assertNotIn("FAIL", out.replace(f"FAIL {name}:", ""))

    def ok(self, **kw):
        rc, out = only(**kw)
        self.assertEqual(rc, 0, out)

    def error(self, raw):
        rc, out = run_text(raw)
        self.assertEqual(rc, 2, (raw[:60], out))
        self.assertTrue(out.startswith("ERROR "), out)
        self.assertNotIn("Traceback", out)


class Checks(Base):
    def test_good_draft_passes_every_check(self):
        rc, out = run_text(json.dumps(GOOD))
        self.assertEqual(rc, 0, out)
        self.assertEqual([ln.split(":")[0] for ln in out.splitlines()], [f"PASS {n}" for n in NAMES])

    def test_hypothesis_must_start_the_statement_case_insensitively(self):
        self.ok(statement_text="  HYPOTHESIS for solo bookkeepers, Acme Ledger is a close tool.")
        self.fail_only("hypothesis", statement_text="For bookkeepers, Acme Ledger is a close tool.")
        self.fail_only("hypothesis", statement_text="No hypothesis here: Acme Ledger is a close tool.")
        self.fail_only("hypothesis", statement_text="Hypothesis-free claim: Acme Ledger is a close tool.")
        self.fail_only("hypothesis", statement_text="Hypothesisx for bookkeepers: Acme Ledger.")

    def test_generic_segment(self):
        self.fail_only("segment", segment="Teams.")

    def test_generic_alternative(self):
        self.fail_only("alternative", alternative="Unlike the competition")
        self.fail_only("alternative", alternative="the competition")

    def test_unsupplied_element_needs_assumed_tag(self):
        self.fail_only("assumed_tags", statement={**GOOD["statement"], "benefit": "less rework"})

    def test_supplied_element_needs_no_tag_and_may_hold_numbers(self):
        self.ok(statement={"segment": "bookkeeper with 5 clients", "benefit": "[ASSUMED] less rework"})

    def test_empty_supplied_list_means_nothing_supplied(self):
        self.fail_only("assumed_tags", statement={"segment": "solo bookkeeper"}, supplied=[])

    def test_unsupplied_digit_fails(self):
        self.fail_only("no_invented_specifics", statement={"benefit": "[ASSUMED] 3x faster"})

    def test_unsupplied_straight_quote_fails(self):
        self.fail_only("no_invented_specifics", statement={"benefit": '[ASSUMED] "loved it"'})

    def test_unsupplied_curly_quotes_fail(self):
        self.fail_only("no_invented_specifics", statement={"benefit": "[ASSUMED] “loved it"})
        self.fail_only("no_invented_specifics", statement={"benefit": "[ASSUMED] loved it”"})

    def test_differentiator_without_proof_fails(self):
        self.fail_only("differentiator_proof", differentiators=[{"claim": "faster", "proof": ""}])

    def test_differentiator_marked_unverified_passes(self):
        self.ok(differentiators=[{"claim": f"faster {MARK}"}])

    def test_pillar_with_blank_proof_fails(self):
        self.fail_only("pillar_proof", pillars=[{"pillar": "speed", "proof": "  "}])

    def test_two_core_messages_fail(self):
        self.fail_only("one_core_message", core_messages=["a", "b"])

    def test_market_fact_filled_but_not_supplied_fails(self):
        self.fail_only("market_facts", market_facts=[{"kind": "TAM", "value": "big", "user_supplied": False}])

    def test_market_fact_slot_left_empty_passes(self):
        self.ok(market_facts=[{"kind": "TAM", "value": " ", "user_supplied": False}])

    def test_market_fact_user_supplied_must_be_a_bool(self):
        self.error('{"market_facts": [{"value": "x", "user_supplied": "yes"}]}')
        self.error('{"market_facts": [{"value": "x"}]}')

    def test_market_facts_must_be_a_list_of_objects(self):
        self.error('{"market_facts": "x"}')
        self.error('{"market_facts": [1]}')

    def test_professional_false_fails(self):
        self.fail_only("clearance_by_professional", name_cleared_by_professional=False, name_clearance="")

    def test_professional_must_be_a_bool(self):
        self.error('{"name_cleared_by_professional": "yes"}')
        self.error('{"name_cleared_by_professional": 1}')

    def test_clearance_claim_without_professional_fails(self):
        rc, out = run_text(json.dumps({"name_clearance": "The name is cleared for use."}))
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL clearance_claim:", out)
        self.assertIn("SKIP clearance_by_professional:", out)

    def test_clearance_claim_with_professional_false_fails(self):
        rc, out = only(name_clearance="Clear to use.", name_cleared_by_professional=False)
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL clearance_claim:", out)
        self.assertIn("FAIL clearance_by_professional:", out)

    def test_clearance_claim_with_professional_true_passes(self):
        self.ok(name_clearance="The name is cleared for use.", name_cleared_by_professional=True)

    def test_any_clearance_text_fails_without_professional_true(self):
        for claim in ("The domain is available, free to use", "safe to use", "free-to-use", "free  to  use", "no conflicts found",
                      "good to go", "usable", "Not cleared: route to a professional."):
            rc, out = run_text(json.dumps({"name_clearance": claim}))
            self.assertEqual(rc, 1, claim)
            self.assertIn("FAIL clearance_claim:", out)

    def test_any_clearance_text_passes_with_professional_true(self):
        self.ok(name_clearance="safe to use", name_cleared_by_professional=True)

    def test_blank_clearance_text_skips(self):
        rc, out = run_text('{"name_clearance": "  "}')
        self.assertEqual(rc, 3, out)

    def test_non_string_clearance_text_is_error(self):
        self.error('{"name_clearance": 5}')
        self.error('{"name_clearance": true}')

    def test_pre_pmf_artifact_naming_brand_system_or_bible_fails(self):
        self.fail_only("stage", artifacts=["Brand System v2"])
        self.fail_only("stage", artifacts=["full brand system"])
        self.fail_only("stage", artifacts=["MESSAGING-BIBLE"], stage="Pre PMF")
        self.fail_only("stage", artifacts=["messaging_bible"], stage="PRE-pmf")

    def test_other_stage_or_artifact_passes(self):
        self.ok(stage="growth", artifacts=["brand system"])
        self.ok(artifacts=["one-line value prop", "name"])

    def test_artifacts_must_be_a_list_of_strings(self):
        self.error('{"stage": "pre-PMF", "artifacts": "x"}')
        self.error('{"stage": "pre-PMF", "artifacts": [1]}')
        self.error('{"stage": "growth", "artifacts": [1]}')

    def test_reaction_without_source_fails(self):
        self.fail_only("buyer_reactions", buyer_reactions=[{"reaction": "loved it", "gathered_from": ""}])


class Contract(Base):
    def test_absent_key_skips_only_that_check(self):
        rc, out = run_text(json.dumps({k: v for k, v in GOOD.items() if k != "segment"}))
        self.assertEqual(rc, 0, out)
        self.assertIn("SKIP segment: no segment", out)
        self.assertIn("PASS alternative:", out)

    def test_blank_values_skip(self):
        rc, out = run_text('{"segment": "  ", "pillars": [], "statement_text": ""}')
        self.assertEqual(rc, 3, out)

    def test_all_skip_is_inconclusive(self):
        rc, out = run_text('{"unrelated": 1}')
        self.assertEqual(rc, 3)
        self.assertIn("INCONCLUSIVE", out)
        self.assertNotIn("PASS", out)

    def test_statement_without_supplied_skips_both_tag_checks(self):
        rc, out = run_text('{"statement": {"segment": "x"}}')
        self.assertEqual(rc, 3, out)

    def test_empty_statement_is_error_not_skip(self):
        self.error('{"statement": {}}')
        self.error('{"statement": {}, "supplied": []}')

    def test_non_list_supplied_is_error_not_skip(self):
        for raw in ('{"supplied": "x"}', '{"supplied": {}}', '{"supplied": 0}', '{"statement": {"a": "x"}, "supplied": "a"}'):
            self.error(raw)

    def test_non_object_input_is_error(self):
        self.error("[]")

    def test_invalid_json_is_error(self):
        self.error("not json")
        self.error("")

    def test_wrong_types_are_errors(self):
        for raw in ('{"pillars": "x"}', '{"pillars": [1]}', '{"segment": 3}', '{"segment": {}}','{"core_messages": "x"}',
                    '{"statement": [1], "supplied": []}', '{"statement": {"a": 1}, "supplied": []}'):
            self.error(raw)

    def test_empty_items_never_pass_vacuously(self):
        for raw in ('{"pillars": [{}]}', '{"differentiators": [{"proof": "x"}]}', '{"buyer_reactions": [{}]}',
                    '{"core_messages": [""]}', '{"core_messages": [1]}', '{"core_messages": [" "]}'):
            self.error(raw)

    def test_deeply_nested_array_is_error_not_traceback(self):
        rc, out = run_text("[" * 20000 + "]" * 20000)
        self.assertEqual(rc, 2, out)
        self.assertTrue(out.startswith("ERROR "), out)

    def test_listed_exceptions_print_error_and_exit_2(self):
        for exc in (KeyError("k"), RecursionError("r"), OSError("os"), ValueError("v")):
            def boom(d, exc=exc):
                raise exc
            old, P.CHECKS = P.CHECKS, [("boom", ("segment",), "q", boom)]
            try:
                rc, out = run_text('{"segment": "x"}')
            finally:
                P.CHECKS = old
            self.assertEqual(rc, 2, exc)
            self.assertTrue(out.startswith("ERROR "), out)

    def test_missing_file_is_error(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(P.main(["/nonexistent/positioning.json"]), 2)
        self.assertTrue(out.getvalue().startswith("ERROR "))

    def test_file_input_matches_stdin(self):
        raw = json.dumps(GOOD)
        self.assertEqual(run_text(raw, via_file=True), run_text(raw))

    def test_every_check_cites_rule_text_present_in_the_skill(self):
        corpus = " ".join((SKILL / "SKILL.md").read_text().split() + (SKILL / "references/full-map.md").read_text().split())
        out = run_text(json.dumps(GOOD))[1]
        for quote in QUOTES:
            self.assertIn(quote, corpus, "rule text drifted from SKILL.md / full-map.md")
            self.assertIn(f'| rule: "{quote}"', out)


if __name__ == "__main__":
    unittest.main()
