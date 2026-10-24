"""The small-diff fast path in SKILL.md routes to the read/output budget reference, which holds the rule and keeps the security floor."""
import re
import unittest
from pathlib import Path

D = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review"
SKILL = (D / "SKILL.md").read_text()
REF = (D / "references/small-diff-read-budget.md").read_text()


class ReadBudget(unittest.TestCase):
    def test_skill_routes_to_reference_in_fast_path(self):
        m = re.search(r"^BUDGET \(small DIFF\):.*$", SKILL, re.M)
        self.assertTrue(m, "BUDGET line missing")
        self.assertIn("`references/small-diff-read-budget.md`", m.group(0))
        self.assertLess(m.start(), SKILL.index("\nOUTPUT."), "rule must sit in the fast path")
        self.assertRegex(SKILL, r"(?m)^1\. Read every hunk")
        self.assertRegex(SKILL, r"(?m)^5\. Guarantees:")

    def test_reference_has_trigger_and_rules(self):
        self.assertTrue(REF.startswith("Read this when"))
        for needle in ("git diff --stat -p", "grep", "callers", "offset/limit", "~200 lines", "tail -n 40", "No narration", "never skips a security check"):
            self.assertIn(needle, REF)


if __name__ == "__main__":
    unittest.main()
