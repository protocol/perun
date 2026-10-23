"""agentic-delivery SKILL.md is the slim fast path; references/full-map.md holds the complete previous body.

Pins the split: SKILL.md stays small and names every reference and full-map.md; full-map.md opens with a
"Read this when" paragraph; no hard-rule line of the pre-slim SKILL.md (frozen in
scripts/eval-fixtures/slim-delivery-hard-rules.txt, 86 lines) is lost from SKILL.md plus full-map.md; and the
rules the always-loaded file must carry on its own stay in SKILL.md. Offline.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / ".claude/skills/agentic-delivery"
SKILL = (D / "SKILL.md").read_text()
MAP = (D / "references/full-map.md").read_text()
FIXTURE = (ROOT / "scripts/eval-fixtures/slim-delivery-hard-rules.txt").read_text().splitlines()


def norm(s):
    return re.sub(r"\s+", " ", s)


class SlimDelivery(unittest.TestCase):
    def test_skill_md_is_small(self):
        self.assertLessEqual(len(SKILL.encode()), 8192)

    def test_every_reference_is_routed_from_skill_md(self):
        for f in sorted((D / "references").glob("*.md")):
            self.assertIn(f.name, SKILL, f"{f.name} not named in SKILL.md")

    def test_full_map_is_self_describing(self):
        self.assertTrue(MAP.split("\n", 2)[2].startswith("Read this when"))
        self.assertIn("references/full-map.md", SKILL)

    def test_no_hard_rule_line_lost(self):
        both = norm(SKILL + "\n" + MAP)
        self.assertGreater(len(FIXTURE), 50)
        missing = [ln for ln in FIXTURE if norm(ln) not in both]
        self.assertEqual(missing, [])

    def test_always_loaded_rules_stay_in_skill_md(self):
        for needle in (
            "never self-approves", "builder never reviews builder", "one writer per worktree",
            "`UNVERIFIED`, never pass", "`UNPRICED`, never zero", "`BLOCKED`, never unlimited",
            "owner-authored artifact", "never creates, widens, extends, or re-dates", "triggers deploy or publish",
            "**owner approves**", "a stale SHA fails closed", "**A running lane is not a finished one.**",
            "never a list of questions", "idea-critic", "Done-when",
        ):
            self.assertIn(needle.lower(), SKILL.lower(), needle)

    def test_fast_path_carries_gate_rows_scripts_and_section_pointer(self):
        self.assertIn("| G3 Design |", SKILL)
        row = next(ln for ln in SKILL.splitlines() if "references/focus-kit.md" in ln)
        for cue in ("compaction", "memory", "scripts/focus_kit.py handoff set", "each gate", "context-heavy", "handback"):
            self.assertIn(cue, row)
        for name in ("flake_ledger", "focus_kit", "handback_cap", "heavy_gate", "operating_selfcheck", "outcome_claim_guard",
                     "pipeline_profile", "queue_guard", "review_gate", "serial_gate", "session_brief", "wired_check",
                     "templates/review-tiers.tsv"):
            self.assertIn(name, SKILL, name)
        self.assertIn('cited as "SKILL.md <section>"', SKILL)

    def test_full_map_has_one_h1(self):
        self.assertEqual(len(re.findall(r"^# ", MAP, re.M)), 1)

    def test_fast_path_keeps_the_task_to_entry_skip_rule(self):
        self.assertIn("a match skips `INDEX.md`", SKILL)


if __name__ == "__main__":
    unittest.main()
