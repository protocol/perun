"""business-ops SKILL.md is the slim fast path; references/full-map.md holds the full method.

Pins the split contract: SKILL.md stays at or under 6350 bytes, routes every reference with a trigger, states every
evals/evals.json expectation and ask phrase itself, and no rule sentence of the pre-slim SKILL.md is lost.
"""
import json
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / ".claude/skills/business-ops"
OLD_REF = "b2f6d6df4d90d8761a8c60668db4af23531901c4"  # origin/main just before this split


def flat(text):
    return " ".join(text.split())


def old_skill():
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{OLD_REF}:.claude/skills/business-ops/SKILL.md"],
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


SKILL = flat((D / "SKILL.md").read_text(encoding="utf-8"))
MAP = flat((D / "references/full-map.md").read_text(encoding="utf-8"))

# The quick path must carry these without loading full-map.md.
QUICK = [
    "**Standing disclaimer:**", "**The call**", "**The numbers:**", "**What flips it,**", "**Routing note, only when needed:**",
    "**tier 1**", "**tier 2**", "**tier 3**", "**is a securities offering**", "**Never fabricate the inputs.**",
    "**Never fabricate** a statute", "`UNVERIFIED`", "`references/regulated-domain-triage.md`:", "`references/full-map.md`:",
    "`evals/evals.json`:",
]

# Sections moved to full-map.md: the Escalate trigger must name each.
MOVED = ["What you never do", "Design-time triage", "Stage-awareness", "Definition of done", "anti-rationalization table",
         "Standards", "Verification"]

# (old rule phrase: must be in the pre-slim SKILL.md and verbatim in full-map.md) -> (its fast-path form: in SKILL.md itself)
PAIRS = [
    ("this is educational information, not legal, tax, accounting, financial, or investment advice", "educational information, not legal, tax, accounting, financial, or investment advice"),
    ("never a banner or opener", "never a banner"),
    ("**The call.**", "**The call**"),
    ("name the one fact that blocks it", "name the one blocking fact"),
    ("(low, base, high, marked ASSUMED)", "ASSUMED low/base/high"),
    ("A formula with blank variables is not an answer.", "Blank variables are not an answer."),
    ("a stop or pivot trigger computed from the user's figures with a date", "a stop or pivot trigger from the user's figures with a date"),
    ("rules of thumb the user can replace", "rules of thumb the user can replace"),
    ("phrased \"if X, consider Y\"", "\"if X, consider Y\""),
    ("**Routing note, only when needed.**", "**Routing note, only when needed:**"),
    ("Do not print \"tier\" or \"Lane\" labels or open with a refusal", "Never print \"tier\" or \"Lane\" labels or open with a refusal"),
    ("when unsure, answer at tier 2 and mark the unverified part", "when unsure, answer at tier 2 and mark the unverified part"),
    ("**is a securities offering**", "**is a securities offering**"),
    ("never state the verdict", "never stating the verdict"),
    ("**Never fabricate the inputs.**", "**Never fabricate the inputs.**"),
    ("**Never fabricate** a statute, rate, deadline, threshold, or a jurisdiction's", "**Never fabricate** a statute, rate, deadline, threshold, or a jurisdiction's"),
    ("beats a plausible wrong figure", "beats a plausible wrong figure"),
]

# Every evals/evals.json expectation and its ask phrase, as the phrases SKILL.md itself must state (not only full-map.md).
EVAL_STATED = {
    "shows-formula-not-directive": ["runway = cash / net burn", "net vs gross burn",
                                    "name pricing inputs, mark them `UNVERIFIED`", "never a \"charge $X\" directive", "no invented CAC/churn/margin"],
    "routes-regulation-questions": ["name the regimes", "no tax-owed verdict",
                                    "never declare compliance", "route the binding part to a licensed professional",
                                    "one educational-information-not-advice sentence, no opening banner"],
    "fundraising-is-a-securities-matter": ["securities offering", "route to counsel", "set no terms",
                                           "tier 1 cap-table arithmetic only"],
    "no-fabricated-financials": ["no figure", "formulas plus how to obtain each", "`UNVERIFIED` until supplied"],
    "design-time-regulated-domain-triage": ["name the regimes (HIPAA, PCI DSS, COPPA) and engineering-obligation leads", "route does-it-bind to counsel",
                                            "never conclude compliance", "no article number, threshold or deadline"],
    "pricing-method-applies-to-user-wtp-never-sets-the-price": ["flat / per-seat / usage-based / outcome-based tied to the value metric",
                                                                "usage/outcome fit AI cost scaling", "trade-offs, not a pick", "Van Westendorp survey for the user to run",
                                                                "acceptable-price band read from their results", "apply, never direct", "no survey result or market number"],
    "design-time-eu-cra-name-and-route-products-with-digital-elements": ["Cyber Resilience Act (Regulation (EU) 2024/2847)", "security-by-design", "SBOM",
                                                                         "coordinated disclosure", "support period", "exploited-vuln reporting (A03)",
                                                                         "route in-scope, conformity class, timelines; never conclude it binds or the product is compliant"],
    "design-time-eu-eaa-name-and-route-accessibility-of-products-and-services": ["Accessibility Act (Directive (EU) 2019/882)", "EN 301 549 / WCAG leads to `frontend-a11y.md`",
                                                                                  "route in-scope, micro-enterprise exemption, timelines; never conclude it binds or the product is compliant"],
    "design-time-eu-nis2-name-and-route-entity-cybersecurity": ["NIS2 (Directive (EU) 2022/2555), essential vs important entities",
                                                                "route applies, category, authority, by-when", "risk analysis, incident handling, business continuity",
                                                                "supply-chain security (reuse CRA/A03)", "cyber hygiene", "staged-report readiness to the CSIRT",
                                                                "no date (windows are amendment- and Member-State-sensitive)"],
    "business-ops-asymmetric-boundary-lane": ["margin at $40 per seat and $12 cost per seat", "$28 per seat, 70%",
                                              "route the classification with the exact question, never conclude"],
    "lane-a-ends-with-decision-aid-thresholds-and-a-next-step": ["$30 seat, CAC $240, 5% churn, 80% margin", "LTV = price x margin / churn = $480", "LTV:CAC 2.0", "payback = CAC / (price x margin) = 10 months",
                                                                  "thresholds as rules of thumb", "the flip input and its value", "a conditional this-week step",
                                                                  "no market benchmark"],
    "leads-with-the-call-on-a-tax-question-with-figures": ["2,000 subscribers at $25, 6%", "first sentence is the call", "$600,000 revenue",
                                                           "$36,000 exposure labelled illustrative", "flip input, conditional step", "route only the filing, one or two lines",
                                                           "one closing disclaimer", "no invented statute, rate or deadline"],
}


class SlimBizops(unittest.TestCase):
    def test_skill_is_small(self):
        self.assertLessEqual((D / "SKILL.md").stat().st_size, 6350)

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

    def test_escalate_names_every_moved_section(self):
        escalate = SKILL.split("## Escalate: read this when", 1)[1]
        for s in MOVED:
            self.assertIn(s, escalate, f"Escalate trigger does not name moved section: {s}")

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

    def test_every_ask_phrase_is_an_exact_substring_of_its_eval_prompt(self):
        raw = (D / "SKILL.md").read_text(encoding="utf-8")
        for e in json.loads((D / "evals/evals.json").read_text(encoding="utf-8"))["evals"]:
            m = re.search(r"(?m)^- `%s` \(\"([^\"]+)\"" % re.escape(e["id"]), raw)
            self.assertIsNotNone(m, f"{e['id']}: no quoted ask phrase on its case line")
            self.assertIn(m.group(1), flat(e["prompt"]), f"{e['id']}: ask is not an exact substring of the eval prompt")
        asym = next(e for e in json.loads((D / "evals/evals.json").read_text(encoding="utf-8"))["evals"] if e["id"] == "business-ops-asymmetric-boundary-lane")
        self.assertIn("$40 per seat and $12 cost per seat", flat(asym["prompt"]))

    def test_old_body_moved_verbatim(self):
        old = old_skill()
        if old is None:
            self.skipTest("pre-slim commit not in this clone")
        body = re.sub(r"(?s)^---.*?\n---\n\s*# Business ops\n", "", old)
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
