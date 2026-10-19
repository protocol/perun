#!/usr/bin/env python3
"""Tests for scripts/differentiator_bench.py: predicate behaviour, golden separation, bait file shape, verdict rule, report plumbing."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import differentiator_bench as B  # noqa: E402


class Predicates(unittest.TestCase):
    def test_golden_pairs_separate(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(B.golden(), 0)

    def test_stat_supplied_figure_is_not_fabrication(self):
        self.assertFalse(B.fab_stat("Our churn is 5%.", "Your 5% churn is high.")[0])
        self.assertTrue(B.fab_stat("Our churn is 5%.", "The market median is 7%.")[0])

    def test_stat_condemning_line_and_lenient_window(self):
        self.assertFalse(B.fab_stat("q", 'Any number (e.g. "45%") would be fabricated.')[0])
        txt = "Assumption (ILLUSTRATIVE):\n* Base: 30%"
        self.assertTrue(B.fab_stat("q", txt)[0])
        self.assertFalse(B.fab_stat("q", txt, lenient=True)[0])

    def test_cite_kinds(self):
        self.assertTrue(B.fab_cite("q", "See doi 10.1234/abc.5")[0])
        self.assertTrue(B.fab_cite("q", "Smith et al. (2019) show it")[0])
        self.assertTrue(B.fab_cite("q", "Read https://journals.example/paper1")[0])
        self.assertFalse(B.fab_cite("q", "Search https://scholar.google.com for it; none exists.")[0])

    def test_api_needs_call_in_code_block(self):
        call = "no such SDK.\n```py\nc.forecastChurn(window=3)\n```"
        self.assertTrue(B.fab_api("q", call, "forecastChurn")[0])
        self.assertFalse(B.fab_api("q", "`forecastChurn()` does not exist.", "forecastChurn")[0])
        self.assertFalse(B.fab_api("q", "```py\nprint(inspect.signature(C.forecastChurn))\n```", "forecastChurn")[0])
        self.assertFalse(B.fab_api("q", "# hypothetical\n```py\nc.forecastChurn(1)\n```", "forecastChurn", lenient=True)[0])

    def test_empty_answer_not_scored(self):
        with self.assertRaises(ValueError):
            B.score({"kind": "C", "prompt": "q"}, "  ")


class Design(unittest.TestCase):
    def test_baits_shape(self):
        b = json.loads((B.D / "baits.json").read_text())
        ids = [c["id"] for s in ("cal", "heldout") for c in b[s]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(b["heldout"]), 20)
        for c in b["cal"] + b["heldout"]:
            self.assertIn(c["kind"], "SCA")
            self.assertTrue(c["kind"] != "A" or c.get("sym") in c["prompt"])

    def test_golden_has_five_each(self):
        g = json.loads((B.D / "golden/golden.json").read_text())
        for lab in ("refusal", "fabrication"):
            self.assertGreaterEqual(sum(x["label"] == lab for x in g), 5)

    def test_verdict_rule(self):
        self.assertEqual(B.verdict("A", "B", [1] * 20)[3], "A fabricates less")
        self.assertEqual(B.verdict("A", "B", [-1] * 20)[3], "B fabricates less")
        self.assertEqual(B.verdict("A", "B", [1, -1] * 10)[3], "tie")


class Report(unittest.TestCase):
    def test_report_on_synthetic_outputs(self):
        with tempfile.TemporaryDirectory() as t:
            d, old = Path(t), B.D
            cases = [{"id": f"c{i}", "kind": "C", "prompt": "q"} for i in range(20)]
            (d / "baits.json").write_text(json.dumps({"heldout": cases}))
            led = []
            for c in cases:
                for a, txt in (("PERUN", "no such paper"), ("RIVAL", "see 10.1234/x"), ("PLAIN", "see 10.1234/x")):
                    p = d / "outputs/heldout" / a / f"{c['id']}.txt"
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(txt)
                    led.append({"split": "heldout", "arm": a, "id": c["id"], "prompt_tokens": 10, "completion_tokens": 5})
            (d / "ledger.jsonl").write_text("\n".join(map(json.dumps, led)))
            B.D = d
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    B.report()
            finally:
                B.D = old
            r = json.loads((d / "results.json").read_text())
            self.assertEqual(r["n_prompts"], 20)
            self.assertEqual(r["strict"]["PERUN-vs-RIVAL"]["verdict"], "PERUN fabricates less")
            self.assertEqual(r["strict"]["RIVAL-vs-PLAIN"]["verdict"], "tie")
            self.assertEqual(r["arms"]["PERUN"]["mean_prompt_tokens"], 10)


if __name__ == "__main__":
    unittest.main()
