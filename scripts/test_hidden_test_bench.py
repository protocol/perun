#!/usr/bin/env python3
"""Tests for scripts/hidden_test_bench.py: code extraction, hidden-test scorer, corpus health, paired report. Offline; no model is called."""
import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hidden_test_bench as H  # noqa: E402

TESTS = "from mod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
FENCE = "```"
# The scorer runs hidden tests under pytest; CI runners without it skip the tests that need a real pytest run.
NEEDS_PYTEST = unittest.skipUnless(importlib.util.find_spec("pytest"), "pytest not installed")


class Extract(unittest.TestCase):
    def test_last_non_test_python_block_wins(self):
        reply = f"first\n{FENCE}python\nx = 1\n{FENCE}\nthen\n{FENCE}python\ny = 2\n{FENCE}\n"
        self.assertEqual(H.extract_code(reply), "y = 2\n")

    def test_test_blocks_are_skipped(self):
        reply = f"{FENCE}python\ndef add(a, b):\n    return a + b\n{FENCE}\n{FENCE}python\nimport pytest\ndef test_x():\n    pass\n{FENCE}\n"
        self.assertEqual(H.extract_code(reply), "def add(a, b):\n    return a + b\n")

    def test_no_block(self):
        self.assertIsNone(H.extract_code("no code here"))
        self.assertIsNone(H.extract_code(None))
        self.assertIsNone(H.extract_code(f"{FENCE}bash\nls\n{FENCE}"))


class Scorer(unittest.TestCase):
    @NEEDS_PYTEST
    def test_pass_and_fail(self):
        self.assertEqual(H.run_hidden("def add(a, b):\n    return a + b\n", TESTS), (True, "pass"))
        self.assertEqual(H.run_hidden("def add(a, b):\n    return a - b\n", TESTS), (False, "tests-fail"))

    @NEEDS_PYTEST
    def test_missing_function_fails(self):
        self.assertEqual(H.run_hidden("x = 1\n", TESTS), (False, "tests-fail"))

    def test_no_code(self):
        self.assertEqual(H.run_hidden(None, TESTS), (False, "no-code"))

    def test_unsafe_constructs_fail_before_running(self):
        for code in ("import os\ndef add(a, b):\n    return a + b\n", "from subprocess import run\n", "def add(a, b):\n    return eval('a+b')\n",
                     "def add(a, b):\n    open('x', 'w')\n    return a + b\n", "__import__('os')\n"):
            self.assertEqual(H.run_hidden(code, TESTS), (False, "unsafe"), code)

    @NEEDS_PYTEST
    def test_timeout(self):
        self.assertEqual(H.run_hidden("def add(a, b):\n    while True:\n        pass\n", TESTS, timeout=2), (False, "timeout"))

    @NEEDS_PYTEST
    def test_collection_error_fails(self):
        self.assertEqual(H.run_hidden("def add(:\n", TESTS), (False, "tests-fail"))


class Corpus(unittest.TestCase):
    def test_shape(self):
        ts = H.load_tickets()
        self.assertEqual(len(ts), 63)
        self.assertEqual(len({t["id"] for t in ts}), 63)
        self.assertEqual(sum(t["split"] == "easy" for t in ts), 40)
        self.assertEqual(sum(t["split"] == "hard" for t in ts), 23)
        self.assertTrue(all(t["id"].startswith("h_") == (t["split"] == "hard") for t in ts))
        for t in ts:
            self.assertIn("from mod import", t["test"], t["id"])
            self.assertNotEqual(t["src"], t["fix"], t["id"])

    @NEEDS_PYTEST
    def test_buggy_fails_and_reference_fix_passes(self):
        self.assertEqual(H.validate(H.load_tickets()), [])

    @NEEDS_PYTEST
    def test_validate_flags_a_ticket_whose_bug_passes(self):
        t = {"id": "t", "ticket": "", "src": "def add(a, b):\n    return a + b\n", "fix": "def add(a, b):\n    return a + b\n", "test": TESTS}
        self.assertEqual(H.validate([t]), ["t: buggy src passes the hidden tests"])

    def test_no_fabricated_person_or_company_names(self):
        blob = "".join(p.read_text() for p in (H.D / "tickets").glob("*.txt")).lower()
        for banned in ("@gmail", "@company", "http://", "https://"):
            self.assertNotIn(banned, blob)

    def test_bad_section_layout_rejected(self):
        d = Path(__import__("tempfile").mkdtemp())
        (d / "a.txt").write_text("### x\n--- ticket\nt\n--- src\ns\n")
        with self.assertRaises(ValueError):
            H.load_tickets(d)


class Arms(unittest.TestCase):
    def test_section_stops_at_next_heading(self):
        md = "# T\n## One\nbody1\n## Two\nbody2\n"
        self.assertEqual(H.section(md, "One"), "## One\nbody1\n")
        with self.assertRaises(ValueError):
            H.section(md, "Three")

    def test_perun_lean_is_small_and_extracted_from_repo_files(self):
        lean, full = H.perun_lean_text(), H.perun_text()
        self.assertLess(len(lean), 12000)  # ~3k tokens
        self.assertLess(len(lean), len(full) // 4)
        for needle in ("G4", "G5", "UNVERIFIED", "change approach"):
            self.assertIn(needle, lean)
        for line in lean.splitlines():  # nothing re-authored: every non-blank line exists verbatim in the full Perun text
            if line.strip() and not line.startswith("#"):
                self.assertIn(line, full)

    def test_perun_text_has_the_three_sources(self):
        t = H.perun_text()
        for needle in ("## Gates (G0", "## Operating principles (non-negotiable)", "## Definition of done", "# Testing & evaluation review"):
            self.assertIn(needle, t)

    def test_prompt_never_contains_hidden_tests(self):
        t = H.load_tickets()[0]
        p = H.user_prompt(t)
        self.assertIn(t["src"], p)
        self.assertNotIn("def test_", p)


def recs(passes, toks=100):
    """passes: {arm: pass fraction pattern per ticket} -> 2 samples per ticket for 4 tickets."""
    out = []
    for arm, pat in passes.items():
        for i, ok in enumerate(pat):
            for k in range(2):
                out.append({"arm": arm, "id": f"t{i}", "sample": k, "pass": ok, "why": "pass" if ok else "tests-fail",
                            "completion_tokens": toks, "prompt_tokens": 10, "finish": "stop"})
    return out


ARM4 = ("none", "perun", "superpowers", "agent-skills")


class Report(unittest.TestCase):
    ids = [f"t{i}" for i in range(4)]

    def test_clear_win_and_tie(self):
        r = H.report(recs({"none": [0, 0, 0, 0], "perun": [1, 1, 1, 1], "superpowers": [0, 1, 0, 1], "agent-skills": [0, 1, 0, 1]}), self.ids, ARM4)
        self.assertEqual(r["arms"]["perun"]["pass_rate"], 1.0)
        p = {(x["a"], x["b"]): x for x in r["paired"]}
        self.assertEqual(p[("perun", "none")]["verdict"], "a better")
        self.assertEqual(p[("perun", "none")]["ci95"], [1.0, 1.0])
        self.assertEqual(p[("perun", "superpowers")]["diff"], 0.5)
        self.assertEqual(p[("superpowers", "none")]["verdict"], "tie (CI includes 0)")

    def test_lower_bound_of_zero_is_a_tie_not_a_win(self):
        # 3 of 20 tickets better, none worse: the bootstrap lower bound is 0 (float noise like 1e-18 must not read as a win)
        a = [1] * 3 + [0] * 17
        r = H.report(recs({"none": [0] * 20, "perun": a, "superpowers": a, "agent-skills": a}), [f"t{i}" for i in range(20)], ARM4)
        v = {(x["a"], x["b"]): x for x in r["paired"]}[("perun", "none")]
        self.assertEqual(v["ci95"][0], 0.0)
        self.assertEqual(v["verdict"], "tie (CI includes 0)")

    def test_loss_is_reported_as_a_loss(self):
        r = H.report(recs({"none": [1, 1, 1, 1], "perun": [0, 0, 0, 0], "superpowers": [1, 1, 1, 1], "agent-skills": [1, 1, 1, 1]}), self.ids, ARM4)
        self.assertEqual({(x["a"], x["b"]): x for x in r["paired"]}[("perun", "none")]["verdict"], "b better")

    def test_per_ticket_score_is_mean_over_samples(self):
        rs = recs({a: [1, 1, 1, 1] for a in H.ARMS})
        rs[0]["pass"] = False  # one of two samples of none/t0 fails
        self.assertAlmostEqual(H.report(rs, self.ids)["arms"]["none"]["pass_rate"], 0.875)

    def test_tokens_and_failure_reasons(self):
        rs = recs({a: [1, 0, 1, 1] for a in H.ARMS}, toks=250)
        rs[2]["why"], rs[2]["finish"] = "no-code", "length"
        a = H.report(rs, self.ids)["arms"]["none"]
        self.assertEqual((a["completion_tokens_per_ticket"], a["no_code"], a["truncated"]), (250, 1, 1))

    def test_incomplete_grid_raises(self):
        with self.assertRaises(ValueError):
            H.report(recs({"none": [1, 1, 1, 1], "perun": [1, 1, 1, 1], "superpowers": [1, 1, 1, 1]}), self.ids, ARM4)
        rs = recs({a: [1, 1, 1, 1] for a in H.ARMS})
        with self.assertRaises(ValueError):
            H.report(rs[:-1], self.ids)

    def test_lean_pairs_and_split_keys(self):
        r = H.report(recs({a: [1, 0, 1, 0] for a in H.ARMS}), self.ids)
        keys = {(x["a"], x["b"]) for x in r["paired"]}
        self.assertIn(("perun-lean", "none"), keys)
        self.assertIn(("perun-lean", "perun"), keys)
        self.assertIn(("perun-lean", "superpowers"), keys)
        self.assertEqual(len(r["paired"]), 4 + 4 + 1)

    def test_table_has_every_arm_and_pair(self):
        t = H.table(H.report(recs({a: [1, 0, 1, 0] for a in H.ARMS}), self.ids))
        for needle in H.ARMS + ("perun - none", "perun - superpowers", "perun - agent-skills", "superpowers - none"):
            self.assertIn(needle, t)


if __name__ == "__main__":
    unittest.main()
