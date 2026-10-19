#!/usr/bin/env python3
"""Offline tests for the idea-critic V5 bench (docs/bench/idea-critic-v5-1019): fresh held-out corpus integrity and
disjointness from every earlier idea-critic set (V3's recorded in the V4 bench's prior-v3-ids.json) and every Wikipedia
page cited in other tracked files, frozen-file hashes, preregistration ledger order, that the dev texts rebuild from V4 and
V5 is the variant the preregistered selection rule picks from the committed tune results, that committed tune and held-out
results and verdicts recompute from the committed outputs, and that the shipped SKILL.md matches the verdict (kill-check
text only on a WIN)."""
import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N = ROOT / "docs/bench/idea-critic-v5-1019"
V4 = ROOT / "docs/bench/idea-critic-v4-1019"
sys.path[:0] = [str(ROOT / "docs/idea-critic-outcome-1019"), str(N / "dev"), str(ROOT / "scripts")]
import bench_outcome as bo  # noqa: E402
import mk_variants5  # noqa: E402
from rival_eval import boot  # noqa: E402

CASES = json.loads((N / "corpus.json").read_text())
EARLIER = [ROOT / "docs/idea-critic-outcome-1019/corpus.json", ROOT / "docs/idea-critic-calibration-1019/corpus.json",
           ROOT / "docs/bench/idea-critic-v2-1019/corpus.json", V4 / "corpus.json"]
V3 = json.loads((V4 / "prior-v3-ids.json").read_text())
WIKI = re.compile(r"https://en\.wikipedia\.org/wiki/[^\s\"'<>\]|`,]+")
trim = lambda u: u[:-1] if u.endswith(")") and u.count(")") > u.count("(") else u  # markdown link closer
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
flat = lambda p: " ".join(p.read_text().split())
urls = {u for c in CASES for u in c["source_urls"]}
MODELS = ["Qwen3.5-397B-A17B", "DeepSeek-V4-Flash", "GLM-5.2"]
ARMS = ["V0", "V4", "V5", "BASE"]
KC = "Kill check before any go"
TUNE_CASES = [c for f in EARLIER for c in json.loads(f.read_text())]


def verdict(lo, hi, fg):
    return "WIN" if lo > 0 and fg == 0 else "LOSS" if hi < 0 or fg != 0 else "TIE"


def decisions(model, arm, cid):
    return [bo.parse(bo.path(model, arm, cid, r).read_text()) for r in range(bo.REPS)]


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
    def frozen(self):
        """[(hash, path)] of SHA256-frozen.txt: the original 9 lines, then one appended line per file the amendment changed."""
        return [tuple(l.split("  ", 1)) for l in (N / "SHA256-frozen.txt").read_text().splitlines()]

    def test_frozen_hashes_match(self):
        fr = self.frozen()
        self.assertEqual(len(fr), 12)
        latest = dict((rel, h) for h, rel in fr)  # a later line for the same path supersedes the earlier one
        self.assertEqual(len(latest), 9)
        for rel, h in latest.items():
            self.assertEqual(sha(N / rel), h, rel)
        self.assertEqual({rel for _, rel in fr[9:]}, {"PREREGISTERED.md", "corpus.json", "bench_v5.py"})

    def test_original_frozen_lines_are_what_the_prereg_line_hashed(self):
        head = "".join(f"{h}  {rel}\n" for h, rel in self.frozen()[:9])
        first = json.loads((N / "ledger.jsonl").read_text().splitlines()[0])
        self.assertEqual(hashlib.sha256(head.encode()).hexdigest(), first["sha256"])

    def test_ledger_prereg_first_then_amendment_of_frozen_file(self):
        """Line 1 preregisters the first frozen file; the `amended` line (two stale cases replaced, see PREREGISTERED.md)
        carries the current hash and precedes every call on the replacement cases and on no voided case's retry."""
        lines = [json.loads(l) for l in (N / "ledger.jsonl").read_text().splitlines()]
        self.assertEqual(lines[0]["event"], "preregistered")
        am = [i for i, j in enumerate(lines) if j.get("event") == "amended"]
        self.assertEqual(len(am), 1)
        latest = dict((rel, h) for h, rel in self.frozen())  # current version of each frozen file, in original order
        current = "".join(f"{latest[rel]}  {rel}\n" for _, rel in self.frozen()[:9])
        self.assertEqual(lines[am[0]]["sha256"], hashlib.sha256(current.encode()).hexdigest())
        files = [j for j in lines if j.get("event") == "amendment_files"]
        self.assertEqual(len(files), 1)
        self.assertEqual({rel: h for h, rel in self.frozen()[9:]}, files[0]["files"])
        self.assertEqual(lines[am[0]]["prior_prereg_sha256"], lines[0]["sha256"])
        voided = set(lines[am[0]]["voided_cases"])
        self.assertFalse(voided & {c["id"] for c in CASES})
        calls = [(i, j["tag"].split("/")) for i, j in enumerate(lines) if "tag" in j]
        self.assertTrue(all(i > 0 for i, _ in calls))
        self.assertFalse([t for i, t in calls if t[3] in voided and i > am[0]])  # nothing was re-run on a voided case
        new = {c["id"] for c in CASES if c["id"] in ("personal-transporter-2001", "social-site-acquisition-2005")}
        self.assertEqual(len(new), 2)
        self.assertTrue(all(i > am[0] for i, t in calls if t[3] in new))

    def test_v5_is_v4_plus_a_kill_check_and_dev_texts_rebuild(self):
        v0, v4, v5 = (flat(ROOT / "docs/bench/idea-critic-v2-1019/prompts/skill_v0.txt"), flat(V4 / "prompts/skill_v4.txt"),
                      flat(N / "prompts/skill_v5.txt"))
        self.assertIn(KC, v5)
        self.assertNotIn(KC, v4)
        self.assertNotIn(KC, v0)
        for name, build in mk_variants5.VARIANTS.items():
            self.assertEqual((N / f"dev/skill_{name}.txt").read_text(), build(), name)


class Tuning(unittest.TestCase):
    def tune(self):
        """{variant: (accuracy, false-GO, mean completion tokens)} recomputed from the committed tune outputs, Qwen only."""
        m, res = MODELS[0], {}
        for v in mk_variants5.VARIANTS:
            bo.H = N / "tune" / v
            ds = {c["id"]: decisions(m, "V5", c["id"]) for c in TUNE_CASES}
            acc = sum(bo.right(c, d) for c in TUNE_CASES for d in ds[c["id"]]) / (3 * len(TUNE_CASES))
            bad = [c for c in TUNE_CASES if c["key"] == "bad"]
            fg = sum(d == "GO" for c in bad for d in ds[c["id"]]) / (3 * len(bad))
            tok = [json.loads(l)["usage"]["completion_tokens"] for l in (bo.H / "ledger.jsonl").read_text().splitlines()
                   if not json.loads(l)["err"]]
            res[v] = (acc, fg, sum(tok) / len(tok))
            stored = json.loads((bo.H / f"results-{m}.json").read_text())["arms"]["V5"]
            self.assertAlmostEqual(acc, stored["accuracy"]["mean"], places=3, msg=v)
            self.assertAlmostEqual(fg, stored["false_go_rate"]["mean"], places=3, msg=v)
        bo.H = N
        return res

    def test_tune_split_is_the_118_earlier_cases(self):
        self.assertEqual((len(TUNE_CASES), len({c["id"] for c in TUNE_CASES})), (118, 118))

    def test_selection_rule_picks_the_shipped_variant(self):
        """Preregistered rule (bench_v5.py docstring): false-GO <= 0.03, highest accuracy, a gap under 0.01 goes to lower
        false-GO then fewer tokens; none eligible -> lowest false-GO, ties by accuracy."""
        res = self.tune()
        ok = {v: r for v, r in res.items() if r[1] <= 0.03}
        if ok:
            best = max(r[0] for r in ok.values())
            pick = min((v for v, r in ok.items() if best - r[0] < 0.01), key=lambda v: (ok[v][1], ok[v][2]))
        else:
            pick = min(res, key=lambda v: (res[v][1], -res[v][0]))
        self.assertEqual((N / "prompts/skill_v5.txt").read_text(), (N / f"dev/skill_{pick}.txt").read_text(), pick)


class Results(unittest.TestCase):
    def per_case(self, model):
        bo.H = N
        return {a: {c["id"]: dict(acc=sum(bo.right(c, d) for d in decisions(model, a, c["id"])) / bo.REPS,
                                  go=sum(d == "GO" for d in decisions(model, a, c["id"])) / bo.REPS) for c in CASES} for a in ARMS}

    def summary(self, pers):
        ids, bad = [c["id"] for c in CASES], [c["id"] for c in CASES if c["key"] == "bad"]
        avg = lambda a, i, k: sum(p[a][i][k] for p in pers) / len(pers)  # noqa: E731
        lo, hi = boot([avg("V5", i, "acc") - avg("V0", i, "acc") for i in ids])
        fg = sum(avg("V5", i, "go") for i in bad) / len(bad)
        return {a: (sum(avg(a, i, "acc") for i in ids) / len(ids), sum(avg(a, i, "go") for i in bad) / len(bad)) for a in ARMS}, \
            (lo, hi), fg

    def check(self, stored, pers):
        arms, (lo, hi), fg = self.summary(pers)
        self.assertEqual(set(stored["arms"]), set(ARMS))
        for a in ARMS:
            self.assertAlmostEqual(arms[a][0], stored["arms"][a]["accuracy"]["mean"], places=3, msg=a)
            self.assertAlmostEqual(arms[a][1], stored["arms"][a]["false_go_rate"]["mean"], places=3, msg=a)
        self.assertEqual([round(lo, 3), round(hi, 3)], stored["paired"]["V5_minus_V0"]["accuracy"]["ci95"])
        self.assertEqual(stored["verdict"], verdict(lo, hi, fg))

    def test_committed_per_model_results_and_verdict_recompute(self):
        for m in MODELS:
            self.check(json.loads((N / f"results-{m}.json").read_text()), [self.per_case(m)])

    def test_committed_pooled_results_and_verdict_recompute(self):
        self.check(json.loads((N / "results-pooled.json").read_text()), [self.per_case(m) for m in MODELS])

    def test_shipped_skill_matches_pooled_verdict(self):
        res = json.loads((N / "results-pooled.json").read_text())
        self.assertEqual(KC in flat(ROOT / ".claude/skills/idea-critic/SKILL.md"), res["verdict"] == "WIN", res["verdict"])


if __name__ == "__main__":
    unittest.main()
