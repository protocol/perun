#!/usr/bin/env python3
"""Offline tests for the idea-critic V2 bench (docs/bench/idea-critic-v2-1019): fresh held-out corpus integrity and
disjointness from both earlier idea-critic benches, frozen-file hashes, preregistration ledger order, that committed
results recompute from the committed outputs, and that the shipped SKILL.md matches the verdict (V2 text only on a WIN)."""
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N = ROOT / "docs/bench/idea-critic-v2-1019"
sys.path.insert(0, str(ROOT / "docs/idea-critic-outcome-1019"))
import bench_outcome as bo  # noqa: E402

CASES = json.loads((N / "corpus.json").read_text())
EARLIER = [ROOT / "docs/idea-critic-outcome-1019/corpus.json", ROOT / "docs/idea-critic-calibration-1019/corpus.json"]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
flat = lambda p: " ".join(p.read_text().split())


class Corpus(unittest.TestCase):
    def test_size_and_balance(self):
        keys = [c["key"] for c in CASES]
        self.assertEqual((len(CASES), keys.count("good"), keys.count("bad")), (28, 14, 14))

    def test_fields_and_unique_ids(self):
        self.assertEqual(len({c["id"] for c in CASES}), len(CASES))
        for c in CASES:
            self.assertTrue(all(u.startswith("https://en.wikipedia.org/wiki/") for u in c["source_urls"]), c["id"])
            self.assertTrue(c["evidence_quote"].strip(), c["id"])
            self.assertEqual(c["fetched"], "2026-10-19")

    def test_fresh_cases_disjoint_from_earlier_benches(self):
        for f in EARLIER:
            old = json.loads(f.read_text())
            self.assertFalse({c["id"] for c in old} & {c["id"] for c in CASES}, f)
            shared = {u for c in old for u in c["source_urls"]} & {u for c in CASES for u in c["source_urls"]}
            # One held-out case (teen-social-phones-2010) shares its source page with a training case; this was found
            # after the run and is disclosed in README.md with a sensitivity result. Any further overlap fails.
            self.assertLessEqual(shared, {"https://en.wikipedia.org/wiki/Microsoft_Kin"}, f)

    def test_no_name_or_hindsight_leak(self):
        for c in CASES:
            p = c["prompt"].lower()
            for n in c["names"]:
                self.assertIsNone(re.search(r"\b%s\b" % re.escape(n.lower()), p), f"{c['id']}: {n}")
            for w in ("write-down", "writedown", "bankrupt", "shut down", "failure", "reintroduc", "discontinued", "flop", "success"):
                self.assertNotIn(w, p, c["id"])


class Preregistration(unittest.TestCase):
    def test_frozen_hashes_match(self):
        lines = (N / "SHA256-frozen.txt").read_text().splitlines()
        self.assertEqual(len(lines), 6)
        for h, rel in (l.split("  ", 1) for l in lines):
            self.assertEqual(sha(N / rel), h, rel)

    def test_ledger_first_line_is_prereg_of_frozen_file(self):
        first = json.loads((N / "ledger.jsonl").read_text().splitlines()[0])
        self.assertEqual(first["event"], "preregistered")
        self.assertEqual(first["sha256"], sha(N / "SHA256-frozen.txt"))

    def test_v0_is_the_pre_change_skill_and_v2_has_the_blocker_test(self):
        v0, v2 = flat(N / "prompts/skill_v0.txt"), flat(N / "prompts/skill_v2.txt")
        self.assertIn("It must beat all three", v0)
        self.assertNotIn("blocker test", v0)
        self.assertIn("blocker test", v2)
        self.assertIn("Risks never decide the call", v2)


class Results(unittest.TestCase):
    def test_committed_results_recompute(self):
        files = list(N.glob("results-*.json"))
        self.assertTrue(files)
        bo.H = N
        for f in files:
            res = json.loads(f.read_text())
            self.assertEqual(set(res["arms"]), {"V0", "V2", "BASE"})
            for a in res["arms"]:
                acc = sum(bo.right(c, bo.parse(bo.path(res["model"], a, c["id"], r).read_text())) for c in CASES for r in range(bo.REPS)) / (len(CASES) * bo.REPS)
                self.assertAlmostEqual(acc, res["arms"][a]["accuracy"]["mean"], places=3, msg=f"{res['model']} {a}")

    def test_shipped_skill_matches_verdict(self):
        res = json.loads((N / "results-Qwen3.5-397B-A17B.json").read_text())
        skill = flat(ROOT / ".claude/skills/idea-critic/SKILL.md")
        self.assertEqual("blocker test" in skill, res["verdict"] == "WIN", res["verdict"])


if __name__ == "__main__":
    unittest.main()
