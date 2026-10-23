"""idea-critic SKILL.md is the slim quick-attack fast path; references/full-map.md holds the full method.

Pins the split contract: SKILL.md stays at or under 5000 bytes, names every reference with a trigger, carries the
output contract and the hard rules a single quick attack needs, and no MUST/never rule of the pre-slim SKILL.md is lost.
"""
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / ".claude/skills/idea-critic"
OLD_REF = "c9ff88db9752e2cd46e33e847cf81ea8dcae830a"  # origin/main just before this split
RULE = re.compile(r"\b(never|must|illegal|do not|cannot|is a lie|is rejected|also rejected)\b", re.I)


def flat(text):
    return " ".join(text.split())


SKILL = flat((D / "SKILL.md").read_text(encoding="utf-8"))
MAP = flat((D / "references/full-map.md").read_text(encoding="utf-8"))

# Pre-slim hard rules, by a distinctive phrase; each must survive in SKILL.md or full-map.md.
PINNED = [
    "reflexive agreement", "Agreement is **earned by surviving the attack**", "Attack **before substantive work**",
    "check the premise against current, verified state", "Never dissent from a remembered or stale number",
    "Direct owner requests are never silently killed", "never repeat one the owner overruled",
    "keeps its human gate until the owner confirms that specific action", "never a menu", "Do not invent a fourth",
    "Any unresolved check means `REVISE`, never `PASS_TO_USER`", "ends with exactly one concrete next action",
    "requires a **concrete failure scenario tied to this proposal**", "A malformed or missing verdict is `HOLD`",
    'Calling `inline` "independent" is a lie', "never loop, never treat exhausted rechecks as a pass",
    "pending or missing stays `UNVERIFIED`, never a silent pass", "`owner-request` + `HOLD` is illegal",
    "`steelman` and `strongest_attack_survived` must not be empty", "Missing evidence is `UNVERIFIED`, never pass",
    "Do not create a new identity, bot, or profile", "Do not route a private `HOLD` / `REVISE` attack to the owner",
    "Do not ask the owner questions the parent can answer", "After a recurring miss, patch **this** skill",
    "never makes the call or invents a probability", "A planted unsupported claim yields `HOLD` or `REVISE`, never `PASS_TO_USER`",
    "An agent-originated `HOLD` never appears in the owner-facing reply",
]

# The quick path must carry these without loading full-map.md.
QUICK = [
    "never open with reflexive agreement", "owner-request` + `HOLD` is illegal", "At most two rechecks",
    "A malformed or missing verdict is `HOLD`", "never a silent pass", "Never label an `inline` pass `independent`",
    "ONE decision", "Do not create a new identity", "at most 3 lines", "verdict HOLD | REVISE | PASS_TO_USER",
    "strongest_attack_survived", "validate_verdict.py",
]


class SlimCritic(unittest.TestCase):
    def test_skill_is_small(self):
        self.assertLessEqual((D / "SKILL.md").stat().st_size, 5000)

    def test_every_reference_is_routed_with_a_trigger(self):
        for ref in sorted((D / "references").glob("*.md")):
            self.assertIn(f"`references/{ref.name}`:", SKILL, f"{ref.name} not routed with a trigger from SKILL.md")

    def test_pinned_hard_rules_survive(self):
        for p in PINNED:
            self.assertTrue(p in SKILL or p in MAP, f"hard rule lost: {p}")

    def test_quick_path_carries_its_contract(self):
        for p in QUICK:
            self.assertIn(p, SKILL, f"quick path missing: {p}")

    def test_every_rule_sentence_of_pre_slim_skill_survives(self):
        r = subprocess.run(["git", "-C", str(ROOT), "show", f"{OLD_REF}:.claude/skills/idea-critic/SKILL.md"],
                           capture_output=True, text=True)
        if r.returncode:
            self.skipTest("pre-slim commit not in this clone")
        old = re.sub(r"(?s)^---.*?\n---\n", "", r.stdout)
        lost = []
        for para in re.split(r"\n\s*\n", old):
            if para.lstrip().startswith(("```", "|", "Validate:")):
                continue
            for s in re.split(r"(?<=[.;:])\s+", flat(para)):
                if RULE.search(s) and s not in SKILL and s not in MAP:
                    lost.append(s)
        self.assertEqual(lost, [], "rule sentences not carried verbatim in SKILL.md or full-map.md")


if __name__ == "__main__":
    unittest.main()
