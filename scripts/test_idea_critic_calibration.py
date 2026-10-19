#!/usr/bin/env python3
"""Offline tests for the idea-critic calibration bench (docs/bench/idea-critic-calibration-1019): held-out corpus integrity,
frozen-file hashes, preregistration ledger order, and that committed results recompute from the committed outputs."""
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

N = Path(__file__).resolve().parent.parent / "docs/bench/idea-critic-calibration-1019"
sys.path.insert(0, str(N.parents[1] / "idea-critic-outcome-1019"))
import bench_outcome as bo  # noqa: E402

CASES = json.loads((N / "corpus.json").read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


class Corpus(unittest.TestCase):
    def test_size_and_balance(self):
        keys = [c["key"] for c in CASES]
        self.assertEqual((len(CASES), keys.count("good"), keys.count("bad")), (24, 12, 12))

    def test_fields_and_unique_ids(self):
        self.assertEqual(len({c["id"] for c in CASES}), len(CASES))
        for c in CASES:
            self.assertTrue(all(u.startswith("https://en.wikipedia.org/wiki/") for u in c["source_urls"]), c["id"])
            self.assertTrue(c["evidence_quote"].strip(), c["id"])
            self.assertEqual(c["fetched"], "2026-10-19")

    def test_disjoint_from_tune_set(self):
        tune = {c["id"] for c in json.loads((N.parents[1] / "idea-critic-outcome-1019/corpus.json").read_text())}
        self.assertFalse(tune & {c["id"] for c in CASES})

    def test_no_name_or_hindsight_leak(self):
        for c in CASES:
            p = c["prompt"].lower()
            for n in c["names"]:
                self.assertIsNone(re.search(r"\b%s\b" % re.escape(n.lower()), p), f"{c['id']}: {n}")
            for w in ("write-down", "writedown", "bankrupt", "shut down", "failure", "reintroduc", "discontinued"):
                self.assertNotIn(w, p, c["id"])


class Preregistration(unittest.TestCase):
    def test_frozen_hashes_match(self):
        lines = (N / "SHA256-frozen.txt").read_text().splitlines()
        self.assertEqual(len(lines), 7)  # lines 6-7 re-hash the two drivers after the outcome bench moved (see PREREG.md)
        current = dict((rel, h) for h, rel in (l.split("  ", 1) for l in lines if not l.endswith("bench_outcome.py") or "../../" in l))  # a later line for the same name wins; line 5 holds the pre-move path
        self.assertEqual(len(current), 5, current)
        for rel, h in current.items():
            self.assertEqual(sha(N / rel), h, rel)
        for l in lines[:3]:  # corpus and both skill texts never changed
            self.assertEqual(sha(N / l.split("  ", 1)[1]), l.split("  ", 1)[0])

    def test_ledger_first_line_is_prereg_of_frozen_file(self):
        first = json.loads((N / "ledger.jsonl").read_text().splitlines()[0])
        self.assertEqual(first["event"], "preregistered")
        head = "".join(l + "\n" for l in (N / "SHA256-frozen.txt").read_text().splitlines()[:5])
        self.assertEqual(first["sha256"], hashlib.sha256(head.encode()).hexdigest())

    def test_arms_differ_and_v1_has_the_fix(self):
        v0, v1 = (N / "prompts/skill_v0.txt").read_text(), (N / "prompts/skill_v1.txt").read_text()
        self.assertNotEqual(v0, v1)
        self.assertIn("No fatal flaw means GO", " ".join(v1.split()))
        self.assertNotIn("No fatal flaw means GO", " ".join(v0.split()))


class Results(unittest.TestCase):
    def test_committed_results_recompute(self):
        files = list(N.glob("results-*.json"))
        self.assertTrue(files)
        bo.H = N
        for f in files:
            res = json.loads(f.read_text())
            model = res["model"]
            self.assertEqual(set(res["arms"]), {"V0", "V1", "BASE", "RIVAL"})
            for a in res["arms"]:
                acc = sum(bo.right(c, bo.parse(bo.path(model, a, c["id"], r).read_text())) for c in CASES for r in range(bo.REPS)) / (len(CASES) * bo.REPS)
                self.assertAlmostEqual(acc, res["arms"][a]["accuracy"]["mean"], places=3, msg=f"{model} {a}")


if __name__ == "__main__":
    unittest.main()
