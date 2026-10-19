#!/usr/bin/env python3
"""Offline tests for the idea-critic V3 bench (docs/bench/idea-critic-v3-1019): fresh held-out corpus integrity and
disjointness from every earlier idea-critic set and every Wikipedia page cited in other tracked files, frozen-file
hashes, preregistration ledger order, that committed results and the verdict recompute from the committed outputs, and
that the shipped SKILL.md matches the verdict (V3 text only on a WIN)."""
import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N = ROOT / "docs/bench/idea-critic-v3-1019"
sys.path.insert(0, str(ROOT / "docs/idea-critic-outcome-1019"))
import bench_outcome as bo  # noqa: E402

CASES = json.loads((N / "corpus.json").read_text())
EARLIER = [ROOT / "docs/idea-critic-outcome-1019/corpus.json", ROOT / "docs/idea-critic-calibration-1019/corpus.json",
           ROOT / "docs/bench/idea-critic-v2-1019/corpus.json"]
WIKI = re.compile(r"https://en\.wikipedia\.org/wiki/[^\s\"'<>\]|`,]+")
trim = lambda u: u[:-1] if u.endswith(")") and u.count(")") > u.count("(") else u  # markdown link closer
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
flat = lambda p: " ".join(p.read_text().split())
urls = {u for c in CASES for u in c["source_urls"]}


class Corpus(unittest.TestCase):
    def test_size_and_balance(self):
        keys = [c["key"] for c in CASES]
        self.assertEqual((len(CASES), keys.count("good"), keys.count("bad")), (30, 15, 15))

    def test_fields_and_unique_ids(self):
        self.assertEqual(len({c["id"] for c in CASES}), len(CASES))
        for c in CASES:
            self.assertTrue(c["source_urls"] and all(u.startswith("https://en.wikipedia.org/wiki/") for u in c["source_urls"]), c["id"])
            self.assertTrue(c["evidence_quote"].strip(), c["id"])
            self.assertEqual(c["fetched"], "2026-10-19")

    def test_disjoint_from_earlier_idea_critic_sets(self):
        for f in EARLIER:
            old = json.loads(f.read_text())
            self.assertFalse({c["id"] for c in old} & {c["id"] for c in CASES}, f)
            self.assertFalse({u for c in old for u in c["source_urls"]} & urls, f)

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

    def test_v0_is_the_shipped_skill_and_v3_has_the_edge_gate(self):
        v0, v3 = flat(ROOT / "docs/bench/idea-critic-v2-1019/prompts/skill_v0.txt"), flat(N / "prompts/skill_v3.txt")
        self.assertIn("blocker test", v3)
        self.assertIn("no edge means no-go", v3)
        self.assertNotIn("blocker test", v0)


class Results(unittest.TestCase):
    def test_committed_results_and_verdict_recompute(self):
        res = json.loads((N / "results-Qwen3.5-397B-A17B.json").read_text())
        self.assertEqual(set(res["arms"]), {"V0", "V3", "BASE"})
        bo.H = N
        for a in res["arms"]:
            ds = {(c["id"], r): bo.parse(bo.path(res["model"], a, c["id"], r).read_text()) for c in CASES for r in range(bo.REPS)}
            acc = sum(bo.right(c, ds[c["id"], r]) for c in CASES for r in range(bo.REPS)) / len(ds)
            self.assertAlmostEqual(acc, res["arms"][a]["accuracy"]["mean"], places=3, msg=a)
            bad = [c for c in CASES if c["key"] == "bad"]
            fg = sum(ds[c["id"], r] == "GO" for c in bad for r in range(bo.REPS)) / (len(bad) * bo.REPS)
            self.assertAlmostEqual(fg, res["arms"][a]["false_go_rate"]["mean"], places=3, msg=a)
        lo, hi = res["paired"]["V3_minus_V0"]["accuracy"]["ci95"]
        guard = res["arms"]["V3"]["false_go_rate"]["mean"] == 0
        self.assertEqual(res["verdict"], "WIN" if lo > 0 and guard else "LOSS" if hi < 0 or not guard else "TIE")

    def test_shipped_skill_matches_verdict(self):
        res = json.loads((N / "results-Qwen3.5-397B-A17B.json").read_text())
        skill = flat(ROOT / ".claude/skills/idea-critic/SKILL.md")
        self.assertEqual("no edge means no-go" in skill, res["verdict"] == "WIN", res["verdict"])


if __name__ == "__main__":
    unittest.main()
