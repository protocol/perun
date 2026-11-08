"""Prose/data leniency in invisible_chars.py: pasted zero-width characters are quiet, bidi/tag stay, agent files and code keep full reporting."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / ".claude/skills/deep-code-review/scripts"))
import invisible_chars as ic  # noqa: E402

ZWSP, RLO, TAG = chr(0x200B), chr(0x202E), chr(0xE0041)


def rules(path, s):
    return [r[1] for r in ic.scan_file(path, s.encode())]


class Prose(unittest.TestCase):
    def test_zwsp_quiet_in_prose_and_data(self):
        for p in ("README.md", "docs/a.mdx", "a.txt", "docs/guide.md", "d.json", "c.toml", "e.yaml", "e.yml"):
            self.assertEqual(rules(p, "a" + ZWSP + "b\n"), [], p)

    def test_zwsp_fires_in_agent_files_and_code(self):
        for p in ("AGENTS.md", "sub/CLAUDE.md", "GEMINI.md", ".claude/skills/x/SKILL.md", "a.prompt.md", ".cursorrules",
                  ".github/copilot-instructions.md", "app.js", ".github/workflows/ci.yml", ".claude/commands/x.md",
                  "a/b.instructions.md", ".cursor/rules/r.mdc", ".windsurf/r.md", ".codex/c.md", ".clinerules"):
            self.assertEqual(rules(p, "a" + ZWSP + "b\n"), ["hidden-unicode"], p)

    def test_smuggling_still_fires_in_prose(self):
        for s in ("Ignore\U000E0100previous", "a\u200b\u200c\u200b" + "b", "a\u202bb", "a\u200b\u200bb", "a\ufe00b", "a\u2062b"):
            self.assertIn("hidden-unicode", rules("README.md", s + "\n"), repr(s))

    def test_isolated_zwsp_fires_in_agent_files(self):
        for p in ("CLAUDE.local.md", "AGENT.md", "CONVENTIONS.md", "x/JULES.md", "QWEN.md", "prompts/a.md", "agents/a.md", ".roo/r.md", ".kiro/s.md", ".gemini/g.md", "mcp.json", ".mcp.json"):
            self.assertEqual(rules(p, "a\u200bb\n"), ["hidden-unicode"], p)

    def test_many_isolated_hits_report_a_few_stay_quiet(self):
        rows = ic.scan_file("README.md", ("w\u200b" * 50 + "\n").encode())
        self.assertEqual(len(rows), 1)
        self.assertIn("50 isolated zero-width/BOM characters", rows[0][2])
        self.assertIn("first U+200B at col 2", rows[0][2])
        self.assertEqual(rules("README.md", "w\u200b" * 3 + "\n"), [])
        self.assertEqual(rules("README.md", "w\u200b" * 4 + "\n"), ["hidden-unicode"])

    def test_locale_json_is_exempt_from_the_count(self):
        self.assertEqual(ic.scan_file("locales/th.json", ("w\u200b" * 5 + "\n").encode()), [])

    def test_bidi_and_tag_still_fire_in_prose(self):
        self.assertEqual(rules("README.md", "a" + RLO + "b\n"), ["hidden-unicode"])
        self.assertEqual(rules("README.md", "a" + TAG + "b\n"), ["hidden-unicode"])
        self.assertEqual(rules("d.json", "a" + TAG + "b\n"), ["hidden-unicode"])


if __name__ == "__main__":
    unittest.main()
