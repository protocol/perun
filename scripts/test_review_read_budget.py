"""The small-diff fast path in SKILL.md carries the read/output budget rule and keeps the security floor."""
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / ".claude/skills/deep-code-review/SKILL.md"


class ReadBudget(unittest.TestCase):
    def test_rule_in_fast_path(self):
        s = SKILL.read_text()
        m = re.search(r"^BUDGET \(small DIFF\):.*$", s, re.M)
        self.assertTrue(m, "BUDGET line missing")
        for needle in ("git diff --stat -p", "grep", "callers", "offset/limit", "~200 lines", "tail -n 40", "no narration"):
            self.assertIn(needle, m.group(0))
        self.assertLess(m.start(), s.index("\nOUTPUT."), "rule must sit in the fast path")
        self.assertIn("never skips a security check", m.group(0))
        self.assertRegex(s, r"(?m)^1\. Read every hunk")
        self.assertRegex(s, r"(?m)^5\. Guarantees:")


if __name__ == "__main__":
    unittest.main()
