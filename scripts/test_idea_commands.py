#!/usr/bin/env python3
"""/critic, /council and /idea name skills, scripts and flags that exist; the one-pager template is routed from G0."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / ".claude/skills"
# command -> (token the body must name, path under .claude/skills that must exist)
NAMES = {
    "critic": [("idea-critic", "idea-critic/SKILL.md")],
    "council": [("veche.py", "idea-critic/scripts/veche.py"), ("council.md", "idea-critic/references/council.md")],
    "idea": [("idea-critic", "idea-critic/SKILL.md"), ("template-onepager.md", "agentic-delivery/references/template-onepager.md")],
}


def read(path):
    return Path(path).read_text(encoding="utf-8")


class IdeaCommands(unittest.TestCase):
    def test_commands_name_existing_targets(self):
        for cmd, pairs in NAMES.items():
            body = read(ROOT / "commands" / f"{cmd}.md")
            for token, rel in pairs:
                self.assertTrue((SKILLS / rel).is_file(), f"{rel} missing")
                self.assertIn(token, body, f"/{cmd} does not name {token}")

    def test_council_flags_exist_in_veche(self):
        src = read(SKILLS / "idea-critic/scripts/veche.py")
        defined = set(re.findall(r'add_argument\("(--[a-z-]+)"', src))
        flags = set(re.findall(r"`(--[a-z-]+)", read(ROOT / "commands/council.md")))
        self.assertTrue({"--stakes", "--reversibility", "--criteria", "--option", "--steelman", "--twin", "--cmd",
                         "--max-calls", "--claim"} <= flags)
        self.assertEqual(flags - defined, set(), "not veche.py options")

    def test_idea_guards_overwrite_and_name(self):
        body = read(ROOT / "commands/idea.md")
        self.assertIn("already exists", body)
        self.assertIn("lowercase letters, digits and hyphens", body)

    def test_template_routed_from_g0(self):
        row = next(l for l in read(SKILLS / "agentic-delivery/SKILL.md").splitlines() if l.startswith("| G0 "))
        self.assertIn("references/template-onepager.md", row)


if __name__ == "__main__":
    unittest.main()
