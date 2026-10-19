#!/usr/bin/env python3
"""Offline tests for the exploratory idea-critic calibration bench (docs/idea-critic-calibration-1019): held-out corpus
integrity, unchanged corpus and skill texts, and that committed results recompute from the committed outputs."""
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

N = Path(__file__).resolve().parent.parent / "docs/idea-critic-calibration-1019"
sys.path.insert(0, str(N.parent / "idea-critic-outcome-1019"))
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
        tune = {c["id"] for c in json.loads((N.parent / "idea-critic-outcome-1019/corpus.json").read_text())}
        self.assertFalse(tune & {c["id"] for c in CASES})

    def test_no_name_or_hindsight_leak(self):
        for c in CASES:
            p = c["prompt"].lower()
            for n in c["names"]:
                self.assertIsNone(re.search(r"\b%s\b" % re.escape(n.lower()), p), f"{c['id']}: {n}")
            for w in ("write-down", "writedown", "bankrupt", "shut down", "failure", "reintroduc", "discontinued"):
                self.assertNotIn(w, p, c["id"])


class FrozenInputs(unittest.TestCase):
    """The preregistration is void (the driver changed after the freeze, see README.md), so only the inputs that
    never changed are pinned: the corpus and both skill texts still match the first three frozen hashes."""

    def test_corpus_and_skill_texts_unchanged(self):
        for l in (N / "SHA256-frozen.txt").read_text().splitlines()[:3]:
            h, rel = l.split("  ", 1)
            self.assertEqual(sha(N / rel), h, rel)

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
