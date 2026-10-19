#!/usr/bin/env python3
"""Tests for the review-cost-per-recall cut: SKILL.md sheds the stage guardrails and the definition-of-done
checklists to references/review-closeout.md, and keeps everything a small-diff review needs.
Read-only; run with `python3 scripts/test_review_closeout.py`."""
import re
import unittest
from pathlib import Path

D = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review"
SKILL = (D / "SKILL.md").read_text()
CLOSE = (D / "references/review-closeout.md").read_text()


class ReviewCloseout(unittest.TestCase):
    def test_skill_stays_under_cut_size(self):
        # Pre-cut size was 23848 bytes; the cut must not creep back.
        self.assertLessEqual(len(SKILL.encode()), 22000)

    def test_closeout_routed_with_trigger(self):
        self.assertEqual(SKILL.count("`review-closeout.md`"), 3)  # Phase 5 row, stage pointer, DoD pointer
        self.assertRegex(CLOSE.splitlines()[2], r"^Read this when")

    def test_closeout_keeps_moved_content(self):
        for s in ("Declared or evidenced, never guessed", "Stage moves urgency, not intrinsic severity",
                  "Definition of done (a)", "`infra-evolution-by-stage.md`",
                  "`docs-evolution-by-stage.md`"):
            self.assertIn(s, CLOSE)

    def test_skill_keeps_never_relax_rule_and_evolution_routes(self):
        self.assertIn("**Security, secret-exposure, and data-loss/integrity findings never relax**", SKILL)
        self.assertIn("**(b) Target ship-ready**", SKILL)  # pinned by scripts/floor-anchors.tsv
        for r in ("infra-evolution-by-stage.md", "docs-evolution-by-stage.md"):
            self.assertIn(r, SKILL)

    def test_no_duplicate_checklist(self):
        self.assertNotIn("**(b) Target ship-ready**", CLOSE)  # one home per checklist
        self.assertEqual(len(re.findall(r"(?m)^## Definition of done", SKILL)), 1)

    def test_quick_path_untouched(self):
        self.assertIn("**DIFF quick-path**", SKILL)
        self.assertTrue((D / "references/compact-mode.md").exists())


if __name__ == "__main__":
    unittest.main()
