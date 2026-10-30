#!/usr/bin/env python3
"""Tests for the token-voice rows of scripts/scoreboard.py and the capability-matrix section 5 that mirrors them: the bench
README figures reach the rows with every caveat, they equal results.json, a dropped caveat fails generation, and the matrix
counts and cells agree with the rows. Offline; reads only committed files."""
import json
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoreboard as sb  # noqa: E402

BENCH = sb.REPO / "docs" / "bench" / "token-voice-1026"
MATRIX = (sb.DOCS / "capability-matrix.md").read_text()
CAV, PONY = "JuliusBrussee/caveman (ultra level)", "DietrichGebert/ponytail"


def readme_table():
    """Every markdown table row of the bench README by its first cell."""
    return {c[0]: c for c in (sb.cells(l) for l in (BENCH / "README.md").read_text().split("\n") if l.startswith("|"))}


def rows():
    return {r["rival"]: r for r in sb.token_voice_rows()}


class TokenVoiceRows(unittest.TestCase):
    def test_rows_carry_the_published_bench_figures(self):
        cav, pony = rows()[CAV], rows()[PONY]
        for r, cost, tok in ((cav, "0.76x", "0.70x"), (pony, "0.52x", "0.41x")):
            self.assertEqual((r["v"], r["kind"], r["cost"], r["tok"], r["date"]), ("tie", "outcome", cost, tok, "2026-10-26"))
            self.assertTrue(r["q"].startswith("tie (outcome): hidden-test pass rate"))
            self.assertIn("returns win", r["q"])  # the bench's own frozen rule is quoted; the quality verdict stays a tie
            self.assertIn("`docs/bench/token-voice-1026/results.json`", r["src"])
        self.assertIn("Perun minus rival +0.008 [-0.025, +0.050]", cav["q"])
        self.assertIn("median 667 vs 976, paired median diff -292 [-355, -245]", cav["q"])
        self.assertIn("Perun minus rival 0.000 [-0.025, +0.025]", pony["q"])
        self.assertIn("median 667 vs 1647, paired median diff -919 [-1088, -852]", pony["q"])

    def test_every_readme_caveat_rides_on_both_rows(self):
        sec = (BENCH / "README.md").read_text().split("## Caveats (read before citing)")[1].split("## Reproduce")[0]
        bullets = [" ".join(b.split()) for b in re.split(r"(?m)^- ", sec)[1:]]
        self.assertTrue(bullets)
        for b in bullets:  # a caveat added to the README without an anchor fails here until it is mirrored
            self.assertTrue(b.startswith("Ponytail:") or any(a in b for a, _ in sb.TV_CAVEATS), b[:60])
        got = rows()
        for r in got.values():
            for _, shown in sb.TV_CAVEATS:
                self.assertIn(shown, r["q"])
        own = "117 of its 120 replies add test_/assert code the task did not ask for (0 of 120 in every other arm)"
        self.assertIn(own, got[PONY]["q"])
        self.assertNotIn("117 of its", got[CAV]["q"])

    def test_readme_figures_are_the_json_values(self):
        res, t = json.loads((BENCH / "results.json").read_text()), readme_table()
        for arm, key in (("perun", "perun"), ("caveman (ultra)", "caveman"), ("ponytail", "ponytail")):
            self.assertAlmostEqual(float(t[arm][1]), res["arms"][key]["median_completion_tokens"], delta=0.5 + 1e-9)
        for p in (p for p in res["paired"] if p["a"] == "perun" and p["b"] in ("caveman", "ponytail")):
            _, td, tr, pd, _ = t[f"perun vs {p['b']}"]
            for cell, raw, half in ((td, [p["median_token_diff"], *p["token_ci95"]], 0.5), (pd, [p["pass_diff"], *p["pass_ci95"]], 0.0005)):
                shown = [float(x) for x in re.findall(r"[+-]?\d+(?:\.\d+)?", cell)]
                self.assertEqual(len(shown), 3)
                for s, r in zip(shown, raw):
                    self.assertAlmostEqual(s, r, delta=half + 1e-9)
            self.assertAlmostEqual(float(tr), p["median_token_ratio"], delta=0.005 + 1e-9)
        usd = lambda arm: float(t[arm][5].lstrip("$"))  # noqa: E731
        for rival, arm in ((CAV, "caveman (ultra)"), (PONY, "ponytail")):  # README dollars give the same 2-decimal ratio as cost.json
            self.assertEqual(f"{usd('perun') / usd(arm):.2f}x", rows()[rival]["cost"])

    def test_a_caveat_the_readme_dropped_fails_generation(self):
        with mock.patch.object(sb, "TV_CAVEATS", (("a caveat the README no longer carries", "shown"),)):
            with self.assertRaises(AssertionError):
                sb.token_voice_rows()


class TokenVoicePage(unittest.TestCase):
    def test_section5_rows_are_replaced_and_the_other_unmeasured_rows_stay(self):
        page = sb.build()
        for rival in ("JuliusBrussee/caveman", "DietrichGebert/ponytail"):
            self.assertNotIn(f"| Compressed-prose and minimal-code modes | {rival} | UNMEASURED", page)
        for row in ("Compressed-prose and minimal-code modes | multica-ai/andrej-karpathy-skills", "Compressed-prose and minimal-code modes | Claude Code Concise output style",
                    "Token usage optimisation | JuliusBrussee/caveman"):
            self.assertIn(f"| {row} | UNMEASURED", page)
        self.assertIn("| tie (outcome): hidden-test pass rate, Perun minus rival +0.008 [-0.025, +0.050]", page)
        self.assertIn("Clean outcome wins: 0 (Perun has no clean outcome win)", page)  # a tie plus a quoted keep rule is not a clean win


class PerunArm(unittest.TestCase):
    def test_arm_is_the_opt_in_budget_plus_the_lane_default_zero_chat_rule(self):
        prompt = (BENCH / "prompts" / "perun.txt").read_text()
        template = ".claude/skills/agentic-delivery/templates/lane-preamble.md"
        zero = next(l for l in prompt.split("\n") if l.startswith("- Zero chat between tool calls"))
        self.assertIn(zero, (sb.REPO / template).read_text().split("\n"))  # the measured rule is the lane default, line for line
        self.assertIn("Reply budget: at most 3 lines / 500 chars", prompt)
        self.assertIn("lane preamble", sb.TV_CAVEATS[0][1])
        self.assertNotIn("text only", sb.TV_CAVEATS[0][1])
        for doc in ((BENCH / "README.md").read_text(), MATRIX.split("\n## 5. ")[1].split("\n## 6. ")[0]):
            self.assertIn(template, doc)


class MatrixSection5(unittest.TestCase):
    def test_section5_cells_cite_the_bench_with_its_numbers_and_caveats(self):
        sec = MATRIX.split("\n## 5. ")[1].split("\n## 6. ")[0]
        status = [sb.cells(l)[2] for l in sec.split("\n") if l.startswith("| [")]
        self.assertEqual([s.startswith("Measured elsewhere: `docs/bench/token-voice-1026/README.md`") for s in status], [True, True, False, False])
        self.assertTrue(all(s.startswith("Not measured") for s in status[2:]))
        t, got = readme_table(), rows()
        n = re.search(r"(\d+) hidden-test bug-fix tasks x (\d+) samples", " ".join((BENCH / "README.md").read_text().split()))
        for s, key, arm, rival in zip(status, ("caveman", "ponytail"), ("caveman (ultra)", "ponytail"), (CAV, PONY)):
            for cell in t[f"perun vs {key}"][1:4:2]:  # token diff and pass diff, each as "x (lo to hi)"
                for num in re.findall(r"[+-]?\d+(?:\.\d+)?", cell):
                    self.assertIn(num, s)
            # the medians (Perun first, then the rival), the bench date and N, as the README and the generator publish them
            for want in (f"at {t['perun'][1]} median output tokens per task against {t[arm][1]} for the", f"({got[rival]['date']}, ",
                         f"{n[1]} hidden-test bug-fix tasks x {n[2]} samples"):
                self.assertIn(want, s)
            self.assertIn("returns `win` on a pass-rate tie", s)  # the keep rule's win is not a quality win
            self.assertIn("not on `perun-vs-rivals.md`", s)
        self.assertIn("117 of ponytail's 120 replies add tests the task did not ask for", status[1])
        for caveat in ("default Perun is not measured", "hard length cap", "117 of its 120 replies", "no multiplicity correction", "near 100%",
                       "Haiku 5.5, thinking disabled", "list cost and includes input tokens", "Deviation from the preregistration"):
            self.assertIn(caveat, sec)

    def test_counts_add_up_and_match_the_prose(self):
        rows = [sb.cells(l)[2] for l in MATRIX.split("\n") if l.startswith("| [")]
        vs = sum(s.startswith("Measured") and not s.startswith("Measured elsewhere") for s in rows)
        readme = sum(s.startswith("Measured elsewhere: `README.md`") for s in rows)
        bench = sum(s.startswith("Measured elsewhere: `docs/bench/") for s in rows)
        none = sum(s.startswith("Not measured") for s in rows)
        self.assertEqual(vs + readme + bench + none, len(rows))
        got = re.search(r"\((\d+) rows\), (\d+) rows have a result on `perun-vs-rivals.md`, (\d+) has one only in the README, "
                        r"(\d+) have one only in the token-voice bench README \(`[^`]+`\) and (\d+) are not measured", MATRIX.split("\n")[2])
        self.assertEqual(tuple(map(int, got.groups())), (len(rows), vs, readme, bench, none))
        total = re.search(r"\*\*Total\*\* \| [^|]+\| (\d+) \| (\d+) \(\+(\d+) README only, \+(\d+) bench README only\)", MATRIX)
        self.assertEqual(tuple(map(int, total.groups())), (len(rows), vs, readme, bench))
        self.assertIn("| 5 | Compressed prose, minimal code | Gap | 4 | 0 (+2 bench README only) |", MATRIX)


if __name__ == "__main__":
    unittest.main()
