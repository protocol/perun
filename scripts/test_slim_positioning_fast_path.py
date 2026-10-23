"""positioning SKILL.md is the slim fast path; references/full-map.md holds the full method.

Pins the split contract: SKILL.md stays small, keeps the frontmatter, routes every reference with a trigger, carries each
eval's ask phrase (an exact substring of the eval prompt) and key terms on its own, and no rule of the pre-slim SKILL.md is lost.
"""
import json
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / ".claude/skills/positioning"
OLD_REF = "6388e04163c73e9bf64bb5f7839f31817ff53e1a"  # origin/main just before this split
OLD = subprocess.run(["git", "-C", str(ROOT), "show", f"{OLD_REF}:.claude/skills/positioning/SKILL.md"],
                     capture_output=True, text=True)


def flat(text):
    return " ".join(text.split())


RAW = (D / "SKILL.md").read_text(encoding="utf-8")
SKILL = flat(RAW)
MAP = flat((D / "references/full-map.md").read_text(encoding="utf-8"))
EVALS = {e["id"]: e for e in json.loads((D / "evals/evals.json").read_text(encoding="utf-8"))["evals"]}

# eval id -> (ask phrase: exact substring of the eval prompt, key terms: in SKILL.md and in the eval's own expected text)
ASKS = {
    "refuses-fabricated-market-facts": ("total addressable market", ["top three competitors' weaknesses", "how-to-obtain", "slots"]),
    "positioning-is-a-hypothesis": ("Write our positioning statement.", ["hypothesis", "how-to-obtain"]),
    "no-invented-quotes-or-outcomes": ("customer testimonials", ["'3x faster' outcome stat", "UNVERIFIED — needs proof"]),
    "trademark-clearance-routed": ("is it clear for us to use", ["clearance", "professional"]),
    "positioning-names-alternative-and-proof": ("unlike the competition", ["teams", "proof point", "UNVERIFIED"]),
    "committed-draft-with-assumed-tags": ("I have no customers and no research", ["[ASSUMED]", "riskiest assumption"]),
    "commits-to-one-call-and-answers-each-alternative": ("lead with accountants or agency owners",
                                                          ["ready-to-use", "headline", "hypothesis", "riskiest assumption"]),
}

# (old phrase, verbatim in the pre-slim SKILL.md and in full-map.md) -> (its fast-path form, in SKILL.md itself)
PAIRS = [
    ("**Never fabricate** market size / TAM", "**Never fabricate** market size / TAM"),
    ("customer quotes or testimonials, outcome / ROI numbers", "customer quotes or testimonials, outcome / ROI numbers"),
    ("trademark / domain availability or clearance", "trademark / domain availability or clearance"),
    ("Empty slots for market facts, a committed draft for everything else", "Empty slots for market facts, a committed draft for everything else"),
    ("each element the user did not supply tagged `[ASSUMED]`", "tag every element the user did not supply `[ASSUMED]`"),
    ("plus the one riskiest assumption and how to\n  test it", "add the riskiest assumption and its test"),
    ("Never a named vendor, number or quote", "Never a named vendor, number or quote"),
    ("a search is *not* legal\n  clearance, route to a\n  professional", "A search is not legal clearance: trademark / domain goes to a professional"),
    ("any factual claim in a message → the user's own proof", "A factual claim in a message needs the user's own proof"),
    ("**commit**: one\nsegment, one lead message, and one line on why", "commit to one segment, one lead message and one line why"),
    ("answer each named alternative in turn", "answer each named alternative"),
    ("Say \"hypothesis\" once", "Say \"hypothesis\" once"),
    ("the riskiest assumption and the\ntest that would prove it wrong", "the riskiest assumption and the test that would disprove it"),
    ("Raise trademark, legal or market-size routing only when the\nuser asks or the draft makes that kind of claim", "Trademark, legal or market-size routing only when asked or the draft makes that claim"),
    ("route to `product-discovery`, do not invent\nthe profile", "route to `product-discovery`, never invent it"),
    ("*for [segment] who [need], [product] is a [category]\nthat [key benefit]; unlike [alternative], it [differentiator].*", "*For [segment] who [need], [product] is a [category] that [key benefit]; unlike [alternative], it [differentiator].*"),
    ("not a\n  demographic or \"teams\"", "not a demographic or \"teams\""),
    ("\"Unlike the competition\" is a blank", "\"Unlike the competition\" is a blank"),
    ("**one proof point** the user supplies, and\n  states what it costs the buyer to give up the alternative", "one user-supplied proof point plus what leaving the alternative costs"),
    ("`UNVERIFIED — needs proof`", "`UNVERIFIED — needs proof`"),
    ("swap in a rival's name; if the sentence still reads true, it is not\n  differentiated yet", "Swap in a rival's name: still true means undifferentiated"),
    ("One core message, a few supporting pillars, and **proof under each pillar**", "One core message, a few pillars, the user's real proof under each"),
    ("never report a reaction that was not gathered", "never report a reaction that was not gathered"),
    ("**Pre-PMF: a minimum viable brand.**", "Pre-PMF: a minimum viable brand"),
    ("premature scaling", "premature scaling"),
]


class SlimPositioning(unittest.TestCase):
    def test_skill_is_small(self):
        self.assertLessEqual((D / "SKILL.md").stat().st_size, 5852)  # 5800 + the one-line positioning_check.py route

    def test_frontmatter_unchanged_and_single_h1(self):
        if OLD.returncode:
            self.skipTest("pre-slim commit not in this clone")
        fm = lambda t: re.match(r"(?s)---\n.*?\n---\n", t).group(0)
        self.assertEqual(fm(RAW), fm(OLD.stdout))
        for rel in ("SKILL.md", "references/full-map.md"):
            self.assertEqual(len(re.findall(r"(?m)^# ", (D / rel).read_text(encoding="utf-8"))), 1, rel)

    def test_every_reference_is_routed_with_a_trigger_and_no_scripts(self):
        for ref in sorted((D / "references").glob("*.md")):
            self.assertIn(f"`references/{ref.name}`:", SKILL, f"{ref.name} not routed with a trigger from SKILL.md")
        scripts = sorted(p.name for p in (D / "scripts").glob("*.py")) if (D / "scripts").exists() else []
        self.assertEqual(scripts, ["positioning_check.py"], "scripts/ changed: route every script from SKILL.md and update this list")
        self.assertIn("`scripts/positioning_check.py`:", SKILL)
        self.assertIn("`evals/evals.json`:", SKILL)

    def test_escalate_names_every_moved_section(self):
        esc = SKILL.split("## Escalate: read this when")[1]
        for s in ("boundary", "prime directive", "Deliver the call", "the method", "stage-awareness", "definition of done",
                  "anti-rationalization table", "standards list", "verification cases"):
            self.assertIn(s, esc, f"Escalate does not name the moved section: {s}")

    def test_every_eval_is_enumerated_with_its_ask_and_terms_on_the_fast_path(self):
        self.assertEqual(set(EVALS), set(ASKS), "evals.json and ASKS drifted: update the test")
        for eid, (ask, terms) in ASKS.items():
            ev = EVALS[eid]
            self.assertIn(ask, ev["prompt"], f"{eid}: ask phrase is not an exact substring of the eval prompt")
            self.assertIn(f"`{eid}`", SKILL, f"{eid}: id not enumerated in SKILL.md")
            self.assertIn(f'"{ask}"', SKILL, f"{eid}: ask phrase missing from SKILL.md")
            text = ev["prompt"] + ev["expected_output"] + " ".join(ev["expectations"])
            for t in terms:
                self.assertIn(t.lower(), text.lower(), f"{eid}: term is not in the eval: {t}")
                self.assertIn(t, SKILL, f"{eid}: key term missing from SKILL.md: {t}")

    def test_old_body_moved_verbatim(self):
        if OLD.returncode:
            self.skipTest("pre-slim commit not in this clone")
        body = re.sub(r"(?s)^---.*?\n---\n\s*# Positioning\n", "", OLD.stdout)
        self.assertIn(flat(body), MAP, "old SKILL.md body is not carried verbatim in full-map.md")

    def test_every_pre_slim_rule_is_pinned_to_the_fast_path(self):
        if OLD.returncode:
            self.skipTest("pre-slim commit not in this clone")
        for old, new in PAIRS:
            self.assertIn(flat(old), flat(OLD.stdout), f"stale pair, not in the pre-slim SKILL.md: {old}")
            self.assertIn(flat(old), MAP, f"rule not carried in full-map.md: {old}")
            self.assertIn(new, SKILL, f"fast path lost the rule: {new}")


if __name__ == "__main__":
    unittest.main()
