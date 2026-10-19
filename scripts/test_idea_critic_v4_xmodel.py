#!/usr/bin/env python3
"""Offline tests for the idea-critic V4 cross-model bench (docs/bench/idea-critic-v4-xmodel-1019): every frozen file
(this bench's and the V4 bench's reused corpus, prompts, scorer and driver) matches its recorded hash, the preregistration
ledger line comes first and covers the frozen list, and that the committed per-model and pooled results and their verdicts
recompute from the committed outputs by the frozen keep rule."""
import hashlib
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N = ROOT / "docs/bench/idea-critic-v4-xmodel-1019"
sys.path.insert(0, str(ROOT / "docs/idea-critic-outcome-1019"))
import bench_outcome as bo  # noqa: E402

CASES = json.loads((ROOT / "docs/bench/idea-critic-v4-1019/corpus.json").read_text())
MODELS = ["DeepSeek-V4-Flash", "GLM-5.2"]
ARMS = ("V0", "V4", "BASE")
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
POOLED = json.loads((N / "results-pooled.json").read_text())


def per_case(model):
    """{arm: {case id: (accuracy, GO rate)}} recomputed from the committed outputs."""
    out = {}
    for a in ARMS:
        out[a] = {}
        for c in CASES:
            ds = [bo.parse((N / "outputs" / model / a / f"{c['id']}.{r}.txt").read_text()) for r in range(bo.REPS)]
            out[a][c["id"]] = (sum(bo.right(c, d) for d in ds) / bo.REPS, sum(d == "GO" for d in ds) / bo.REPS)
    return out


def verdict(lo, hi, false_go):
    return "WIN" if lo > 0 and false_go == 0 else "LOSS" if hi < 0 or false_go else "TIE"


class Frozen(unittest.TestCase):
    def test_frozen_hashes_match_and_cover_the_reused_bench_files(self):
        lines = (N / "SHA256-frozen.txt").read_text().splitlines()
        self.assertEqual(len(lines), 10)
        paths = []
        for h, rel in (l.split("  ", 1) for l in lines):
            self.assertEqual(sha(N / rel), h, rel)
            paths.append(Path(rel).name)
        for need in ("PREREG.md", "bench_xmodel.py", "corpus.json", "skill_v4.txt", "skill_v0.txt", "bench_v4.py", "bench_outcome.py"):
            self.assertIn(need, paths)

    def test_ledger_first_line_is_prereg_of_frozen_file(self):
        first = json.loads((N / "ledger.jsonl").read_text().splitlines()[0])
        self.assertEqual(first["event"], "preregistered")
        self.assertEqual(first["sha256"], sha(N / "SHA256-frozen.txt"))

    def test_corpus_is_the_v4_held_out_set_not_a_copy(self):
        self.assertFalse((N / "corpus.json").exists())
        self.assertEqual(len(CASES), 30)

    def test_every_line_after_the_prereg_line_is_a_tested_model_call(self):
        for l in (N / "ledger.jsonl").read_text().splitlines()[1:]:
            self.assertIn(json.loads(l)["model"], MODELS)


class Results(unittest.TestCase):
    def test_per_model_results_recompute(self):
        for m in MODELS:
            res = json.loads((N / f"results-{m}.json").read_text())
            pc = per_case(m)
            bad = [c["id"] for c in CASES if c["key"] == "bad"]
            for a in ARMS:
                acc = sum(v[0] for v in pc[a].values()) / len(CASES)
                fg = sum(pc[a][i][1] for i in bad) / len(bad)
                self.assertAlmostEqual(acc, res["arms"][a]["accuracy"]["mean"], places=3, msg=f"{m} {a}")
                self.assertAlmostEqual(fg, res["arms"][a]["false_go_rate"]["mean"], places=3, msg=f"{m} {a}")
            lo, hi = res["paired"]["V4_minus_V0"]["accuracy"]["ci95"]
            self.assertEqual(res["verdict"], verdict(lo, hi, res["arms"]["V4"]["false_go_rate"]["mean"]), m)

    def test_pooled_results_recompute(self):
        pcs = [per_case(m) for m in MODELS]
        bad = [c["id"] for c in CASES if c["key"] == "bad"]
        new = POOLED["new_models"]
        self.assertEqual(new["models"], MODELS)
        for a in ARMS:
            acc = sum(p[a][c["id"]][0] for p in pcs for c in CASES) / (len(pcs) * len(CASES))
            fg = sum(p[a][i][1] for p in pcs for i in bad) / (len(pcs) * len(bad))
            self.assertAlmostEqual(acc, new["arms"][a]["accuracy"]["mean"], places=3, msg=a)
            self.assertAlmostEqual(fg, new["arms"][a]["false_go_rate"]["mean"], places=3, msg=a)
        lo, hi = new["paired"]["V4_minus_V0"]["accuracy"]["ci95"]
        self.assertEqual(new["verdict"], verdict(lo, hi, new["arms"]["V4"]["false_go_rate"]["mean"]))

    def test_descriptive_pool_includes_qwen_and_carries_no_verdict(self):
        wq = POOLED["with_qwen"]
        self.assertEqual(wq["models"], MODELS + ["Qwen3.5-397B-A17B"])
        self.assertNotIn("verdict", wq)

    def test_skill_md_untouched_by_this_bench(self):
        def norm(p):  # a release stamps metadata.version; that line is not skill text
            return " ".join(re.sub(r'(?m)^\s*version: ".*"$', "", (ROOT / p).read_text()).split())
        skill = norm(".claude/skills/idea-critic/SKILL.md")
        v0 = norm("docs/bench/idea-critic-v2-1019/prompts/skill_v0.txt")
        self.assertEqual(skill, v0)


if __name__ == "__main__":
    unittest.main()
