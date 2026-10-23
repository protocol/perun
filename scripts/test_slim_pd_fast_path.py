"""product-discovery SKILL.md is the slim fast path; references/full-map.md holds the full method.

Pins the split contract: SKILL.md stays at or under 6200 bytes, routes every reference with a trigger, states every
evals/evals.json expectation itself, and no rule sentence of the pre-slim SKILL.md is lost.
"""
import json
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / ".claude/skills/product-discovery"
OLD_REF = "b2f6d6df4d90d8761a8c60668db4af23531901c4"  # origin/main just before this split


def flat(text):
    return " ".join(text.split())


def old_skill():
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{OLD_REF}:.claude/skills/product-discovery/SKILL.md"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


SKILL = flat((D / "SKILL.md").read_text(encoding="utf-8"))
MAP = flat((D / "references/full-map.md").read_text(encoding="utf-8"))

# The quick path must carry these without loading full-map.md.
QUICK = [
    "**Never invent**", "**empty-slot template**", "A realistic example is the fabrication", "**A scoring table has blanks, not guesses.**",
    "`UNVERIFIED`", "flattening retention cohort", "impact × uncertainty", "refuse to build yet", "numeric kill threshold",
    "labelled starting value", "go / narrow / drop rule", "never a finding", "**Route the unknowable.**", "Empty beats fabricated",
    "**Non-goals are recorded, stage-tied decisions**", "reopen it?", "core loop as acceptance", "non-pilot user",
    "`references/full-map.md`:", "`evals/evals.json`:",
]

# (old rule phrase: must be in the pre-slim SKILL.md and verbatim in full-map.md) -> (its fast-path form: in SKILL.md itself)
PAIRS = [
    ("**Never invent** interview findings", "**Never invent** interview findings"),
    ("return an **empty-slot template**", "**empty-slot template**"),
    ("A realistic example is the fabrication.", "A realistic example is the fabrication."),
    ("A scoring table has blanks, not guesses.", "A scoring table has blanks, not guesses."),
    ("never print a reach/impact/confidence number the user did not supply", "Never print a reach/impact/confidence number the user did not supply"),
    ("Empty beats fabricated.", "Empty beats fabricated"),
    ("**empirical threshold on the user's real data**", "empirical threshold on the user's real data"),
    ("the verdict is `UNVERIFIED`", "`UNVERIFIED`"),
    ("**flattening retention cohort**", "flattening retention cohort"),
    ("**ICE** (Impact × Confidence × Ease) over RICE", "ICE (Impact × Confidence × Ease) over RICE"),
    ("the skill does the arithmetic and orders the list", "the skill does the arithmetic and orders the list"),
    ("Rank by **impact × uncertainty**", "rank by impact × uncertainty"),
    ("the output is a **refusal to build yet**", "refuse to build yet"),
    ("a **numeric kill threshold**", "a numeric kill threshold"),
    ("Propose each as a labelled starting value derived by arithmetic from figures the user gave", "Propose each as a labelled starting value derived by arithmetic from figures the user gave"),
    ("add the go / narrow / drop rule, and say the user adjusts it", "add the go / narrow / drop rule, and say the user adjusts it"),
    ("Leave a slot blank only when no figure was given to derive it from.", "Leave a slot blank only when no figure was given to derive it from."),
    ("A test with no kill threshold cannot fail, so it is not a test.", "A test with no kill threshold cannot fail, so it is not a test."),
    ("Route the unknowable.", "Route the unknowable."),
    ("a licensed professional", "a licensed professional"),
    ("non-goal is a **recorded, stage-tied decision**", "**Non-goals are recorded, stage-tied decisions**"),
    ("Building *on* an untested assumption is a non-goal until the cheap test passes.", "Building on an untested assumption is a non-goal until the cheap test passes."),
    ("that is a non-goal for this stage because [reason] — reopen it?", "that is a non-goal for this stage because [reason] - reopen it?"),
    ("not invent the product's strategy or set a non-goal the user did not choose", "not invent the product's strategy or set a non-goal the user did not choose"),
    ("**Name the reference's core loop as acceptance.**", "names the reference's core loop as acceptance"),
    ("use the result as a non-pilot user and judge it against the reference", "judge the result against the reference as a non-pilot user"),
    ("The first pilot is a workflow the team itself runs.", "The first pilot is a workflow the team itself runs"),
    ("defer only what the pilot does not use", "defer only what the pilot does not use"),
    ("ask about past specific behavior, not future hypotheticals; never pitch", "past specific behavior, never pitch"),
    ("the four forces", "the four forces"),
    ("**does not** invent quotes or synthesize a persona from nothing", "does not invent quotes or synthesize a persona from nothing"),
    ("never report a result that was not measured", "never reports a result that was not measured"),
    ("`prototype` → riskiest-assumption + discovery dominate; hold polish and infra.", "`prototype`: assumption gate and discovery dominate, hold polish and infra."),
    ("do not let it justify gold-plating the core", "not gold-plating the core"),
]

# Every evals/evals.json expectation, as the phrase SKILL.md itself must state (not only full-map.md).
EVAL_STATED = {
    "refuses-example-finding": ["empty-slot template", "how to obtain each", "A realistic example is the fabrication", "Mom Test or JTBD interviews"],
    "no-invented-scores": ["blank inputs and a how-to-obtain note per column", "the skill does the arithmetic", "did not supply"],
    "pmf-not-declared-from-chat": ["flattening retention cohort", "`UNVERIFIED`", "not a yes"],
    "riskiest-assumption-gate": ["impact × uncertainty", "cheapest test that could disconfirm", "refuse to build yet", "build after, not instead"],
    "routes-unknowable-to-owner": ["routed open question", "the owner", "never conclude it"],
    "non-goals-scope-defense": ["stage-tied", "reopen it?", "set a non-goal the user did not choose"],
    "reference-core-loop-acceptance": ["not a narrow agent-written", "non-pilot user", "already exposes", "defer only what the pilot does not use"],
    "assumption-test-has-numeric-kill-threshold": ["fake door, concierge or pre-sale", "not a survey of intent", "sample size", "a deadline", "fixed before the test runs", "Leave a slot blank only when no figure was given"],
    "proposes-starting-threshold-from-given-figures": ["numeric kill threshold", "derived by arithmetic from figures the user gave", "show the basis", "the user adjusts it", "Invent no result, market size or conversion benchmark"],
}


class SlimPd(unittest.TestCase):
    def test_skill_is_small(self):
        self.assertLessEqual((D / "SKILL.md").stat().st_size, 6200)

    def test_frontmatter_unchanged_and_single_h1(self):
        old = old_skill()
        if old is None:
            self.skipTest("pre-slim commit not in this clone")
        fm = lambda t: re.match(r"(?s)---\n.*?\n---\n", t).group(0)
        self.assertEqual(fm((D / "SKILL.md").read_text(encoding="utf-8")), fm(old))
        for rel in ("SKILL.md", "references/full-map.md"):
            self.assertEqual(len(re.findall(r"(?m)^# ", (D / rel).read_text(encoding="utf-8"))), 1, rel)

    def test_every_reference_and_script_is_routed_with_a_trigger(self):
        for ref in sorted((D / "references").glob("*.md")):
            self.assertIn(f"`references/{ref.name}`:", SKILL, f"{ref.name} not routed with a trigger from SKILL.md")
        for s in sorted((D / "scripts").glob("*.*")) if (D / "scripts").is_dir() else []:
            self.assertIn(f"`scripts/{s.name}`", SKILL, f"{s.name} not routed from SKILL.md")

    def test_quick_path_carries_its_contract(self):
        for p in QUICK:
            self.assertIn(p, SKILL, f"quick path missing: {p}")

    def test_every_eval_expectation_is_stated_in_skill_md(self):
        ids = {e["id"] for e in json.loads((D / "evals/evals.json").read_text(encoding="utf-8"))["evals"]}
        self.assertEqual(ids, set(EVAL_STATED), "evals.json ids changed: update EVAL_STATED")
        for eid, phrases in EVAL_STATED.items():
            self.assertIn(f"`{eid}`", SKILL, f"eval id not named in SKILL.md: {eid}")
            for p in phrases:
                self.assertIn(p, SKILL, f"{eid}: SKILL.md does not state: {p}")

    def test_old_body_moved_verbatim(self):
        old = old_skill()
        if old is None:
            self.skipTest("pre-slim commit not in this clone")
        body = re.sub(r"(?s)^---.*?\n---\n\s*# Product discovery\n", "", old)
        self.assertIn(flat(body), MAP, "old SKILL.md body is not carried verbatim in full-map.md")

    def test_every_pre_slim_hard_rule_is_pinned_to_the_fast_path(self):
        old = old_skill()
        if old is None:
            self.skipTest("pre-slim commit not in this clone")
        for o, new in PAIRS:
            self.assertIn(o, flat(old), f"stale pair, not in the pre-slim SKILL.md: {o}")
            self.assertIn(o, MAP, f"rule not carried in full-map.md: {o}")
            self.assertIn(new, SKILL, f"fast path lost the rule: {new}")


if __name__ == "__main__":
    unittest.main()
