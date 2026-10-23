#!/usr/bin/env python3
"""Tests for scripts/review_load_bytes.py and the SKILL.md quick-path load cut. Offline; temp git repo only."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import review_load_bytes as r  # noqa: E402

D = ROOT / ".claude/skills/deep-code-review"
SKILL = (D / "references/full-map.md").read_text()  # the full map holds the former SKILL.md body


class LoadSet(unittest.TestCase):
    def test_quick_path_skips_index_only_when_exempted(self):
        self.assertEqual(r.load_set(r.EXEMPT, 300)[1], ["SKILL.md", "references/compact-mode.md"])
        self.assertIn("INDEX.md", r.load_set("no exemption", 300)[1])

    def test_over_300_lines_takes_full_method(self):
        route, files = r.load_set(r.EXEMPT, 301)
        self.assertEqual((route, files), ("full", ["SKILL.md", "INDEX.md", "references/method.md"]))

    def test_shipped_skill_exempts_quick_path_from_index(self):
        self.assertIn(r.EXEMPT, SKILL)
        qp = SKILL[SKILL.index("**DIFF quick-path**"):].split("\n\n")[0]
        self.assertIn("compact-mode.md", qp)
        self.assertIn("INDEX.md", qp)

    def test_quick_path_load_stays_under_budget(self):
        # regression: SKILL.md + compact-mode.md (no INDEX.md) was ~48 KB with INDEX.md read; keep it near 25 KB
        b = sum(len((D / f).read_bytes()) for f in ("SKILL.md", "references/compact-mode.md"))
        self.assertLess(b, 26000)


class Counter(unittest.TestCase):
    def test_lines_changed_counts_added_plus_deleted_ignoring_binary(self):
        with tempfile.TemporaryDirectory() as t:
            g = lambda *a: subprocess.run(["git", "-C", t, "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-c", "user.name=a", "-c", "user.email=a@example.com", *a], check=True, capture_output=True)
            g("init", "-q")
            Path(t, "a.txt").write_text("1\n2\n3\n")
            Path(t, "b.bin").write_bytes(b"\0\1\2")
            g("add", "."); g("commit", "-q", "-m", "x")
            Path(t, "a.txt").write_text("1\nX\n3\n4\n")
            g("commit", "-qam", "y")
            cwd = os.getcwd(); os.chdir(t)
            try:
                self.assertEqual(r.lines_changed("HEAD"), 3)  # +X +4 -2
                self.assertEqual(r.lines_changed("HEAD~1"), 3)  # +3 lines, binary "-" counted 0
            finally:
                os.chdir(cwd)


class Moved(unittest.TestCase):
    def test_overlays_routed_and_triggered(self):
        self.assertIn("`overlays.md`", SKILL)
        self.assertTrue((D / "references/overlays.md").read_text().splitlines()[0].startswith("Read this when"))
        self.assertIn("--with-gates", (D / "references/overlays.md").read_text())

    def test_safety_floor_stays_in_skill(self):
        self.assertIn("Black Team — the agent boundary is absolute", SKILL)
        self.assertIn("`infra-evolution-by-stage.md`", SKILL)


FAST_FLOOR = 3000  # bytes; SKILL.md (the small-DIFF fast path) was 2785 when set. Move DOWN only.
# Phase 0-2 floor a large or flagged DIFF also loads; test_floor_refs_named_in_full_map keeps this list honest.
FLOOR_REFS = ["full-map.md", "method.md", "testing-and-evals.md", "language-stack-redflags.md", "domain-checklists.md"]


class FastPathFloor(unittest.TestCase):
    def test_fast_path_under_floor_and_table(self):
        fast = (D / "SKILL.md").stat().st_size
        large = fast + sum((D / "references" / n).stat().st_size for n in FLOOR_REFS)
        print(f"\n{'diff size':<24}{'must-load bytes':>16}{'est tokens':>12}")
        for name, b in (("<=50 lines", fast), ("<=300 lines", fast), (">300 lines or flagged", large)):
            print(f"{name:<24}{b:>16}{b // 4:>12}")
        self.assertLessEqual(fast, FAST_FLOOR)
        self.assertIn("references/full-map.md", (D / "SKILL.md").read_text())

    def test_floor_refs_named_in_full_map(self):
        for n in FLOOR_REFS[1:]:
            self.assertIn(f"`{n}`", SKILL, n)


if __name__ == "__main__":
    unittest.main()
