#!/usr/bin/env python3
"""Offline tests for the idea-critic V4 bench (docs/bench/idea-critic-v4-1019): fresh held-out corpus integrity and
disjointness from every earlier idea-critic set (V3's recorded in prior-v3-ids.json) and every Wikipedia page cited in
other tracked files, frozen-file hashes, preregistration ledger order, that the dev texts rebuild from V0 and V4 is the
frozen dev wording, that committed results and the verdict recompute from the committed outputs, and that the shipped
SKILL.md matches the verdict (V4 text only on a WIN)."""
import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N = ROOT / "docs/bench/idea-critic-v4-1019"
sys.path.insert(0, str(ROOT / "docs/idea-critic-outcome-1019"))
sys.path.insert(0, str(N / "dev"))
import bench_outcome as bo  # noqa: E402
import mk_variants  # noqa: E402

CASES = json.loads((N / "corpus.json").read_text())
EARLIER = [ROOT / "docs/idea-critic-outcome-1019/corpus.json", ROOT / "docs/idea-critic-calibration-1019/corpus.json",
           ROOT / "docs/bench/idea-critic-v2-1019/corpus.json"]
V3 = json.loads((N / "prior-v3-ids.json").read_text())
WIKI = re.compile(r"https://en\.wikipedia\.org/wiki/[^\s\"'<>\]|`,]+")
trim = lambda u: u[:-1] if u.endswith(")") and u.count(")") > u.count("(") else u  # markdown link closer
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
flat = lambda p: " ".join(p.read_text().split())
urls = {u for c in CASES for u in c["source_urls"]}
RESULTS = N / "results-Qwen3.5-397B-A17B.json"


class Corpus(unittest.TestCase):
    def test_size_and_balance(self):
        keys = [c["key"] for c in CASES]
        self.assertEqual((len(CASES), keys.count("good"), keys.count("bad")), (30, 15, 15))

    def test_fields_and_unique_ids(self):
        self.assertEqual(len({c["id"] for c in CASES}), len(CASES))
        self.assertEqual(len(urls), len(CASES))
        for c in CASES:
            self.assertTrue(c["source_urls"] and all(u.startswith("https://en.wikipedia.org/wiki/") for u in c["source_urls"]), c["id"])
            self.assertTrue(c["evidence_quote"].strip(), c["id"])
            self.assertEqual(c["fetched"], "2026-10-19")

    def test_disjoint_from_earlier_idea_critic_sets(self):
        for f in EARLIER:
            old = json.loads(f.read_text())
            self.assertFalse({c["id"] for c in old} & {c["id"] for c in CASES}, f)
            self.assertFalse({u for c in old for u in c["source_urls"]} & urls, f)
        self.assertEqual(len(V3["ids"]), 30)
        self.assertFalse(set(V3["ids"]) & {c["id"] for c in CASES})
        self.assertFalse(set(V3["source_urls"]) & urls)

    def test_no_source_page_cited_elsewhere_in_repo(self):
        out = subprocess.run(["git", "grep", "-hIF", "https://en.wikipedia.org/wiki/", "--", ".", ":!" + str(N.relative_to(ROOT))],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout
        seen = {trim(u) for u in WIKI.findall(out)}
        self.assertIn("https://en.wikipedia.org/wiki/Microsoft_Kin", seen)  # the scan reaches the earlier corpora
        self.assertFalse(urls & seen)

    def test_no_name_or_hindsight_leak(self):
        for c in CASES:
            p = c["prompt"].lower()
            for n in c["names"]:
                self.assertNotIn(n.lower(), p, c["id"])
            for w in ("write-down", "writedown", "bankrupt", "shut down", "failure", "reintroduc", "discontinued", "flop", "success"):
                self.assertIsNone(re.search(rf"\b{w}\b", p), (c["id"], w))  # word match: "successor" is a plan feature, not an outcome


class Preregistration(unittest.TestCase):
    def test_frozen_hashes_match(self):
        lines = (N / "SHA256-frozen.txt").read_text().splitlines()
        self.assertEqual(len(lines), 7)
        for h, rel in (l.split("  ", 1) for l in lines):
            self.assertEqual(sha(N / rel), h, rel)

    def test_ledger_first_line_is_prereg_of_frozen_file(self):
        first = json.loads((N / "ledger.jsonl").read_text().splitlines()[0])
        self.assertEqual(first["event"], "preregistered")
        self.assertEqual(first["sha256"], sha(N / "SHA256-frozen.txt"))

    def test_v0_is_the_shipped_skill_and_v4_decides_first(self):
        v0, v4 = flat(ROOT / "docs/bench/idea-critic-v2-1019/prompts/skill_v0.txt"), flat(N / "prompts/skill_v4.txt")
        self.assertIn("First call, before any attack", v4)
        self.assertIn("Decide like an operator, then attack", v4)
        self.assertNotIn("First call", v0)

    def test_dev_texts_rebuild_from_v0_and_v4_is_dev_wording_b(self):
        for name, build in mk_variants.VARIANTS.items():
            self.assertEqual((N / f"dev/skill_{name}.txt").read_text(), build(), name)
        self.assertEqual((N / "prompts/skill_v4.txt").read_text(), (N / "dev/skill_v4b.txt").read_text())


class Results(unittest.TestCase):
    def test_committed_results_and_verdict_recompute(self):
        res = json.loads(RESULTS.read_text())
        self.assertEqual(set(res["arms"]), {"V0", "V4", "BASE"})
        bo.H = N
        for a in res["arms"]:
            ds = {(c["id"], r): bo.parse(bo.path(res["model"], a, c["id"], r).read_text()) for c in CASES for r in range(bo.REPS)}
            acc = sum(bo.right(c, ds[c["id"], r]) for c in CASES for r in range(bo.REPS)) / len(ds)
            self.assertAlmostEqual(acc, res["arms"][a]["accuracy"]["mean"], places=3, msg=a)
            bad = [c for c in CASES if c["key"] == "bad"]
            fg = sum(ds[c["id"], r] == "GO" for c in bad for r in range(bo.REPS)) / (len(bad) * bo.REPS)
            self.assertAlmostEqual(fg, res["arms"][a]["false_go_rate"]["mean"], places=3, msg=a)
        lo, hi = res["paired"]["V4_minus_V0"]["accuracy"]["ci95"]
        guard = res["arms"]["V4"]["false_go_rate"]["mean"] == 0
        self.assertEqual(res["verdict"], "WIN" if lo > 0 and guard else "LOSS" if hi < 0 or not guard else "TIE")

    def test_shipped_skill_matches_verdict(self):
        res = json.loads(RESULTS.read_text())
        skill = flat(ROOT / ".claude/skills/idea-critic/SKILL.md")
        self.assertEqual("First call, before any attack" in skill, res["verdict"] == "WIN", res["verdict"])


if __name__ == "__main__":
    unittest.main()
