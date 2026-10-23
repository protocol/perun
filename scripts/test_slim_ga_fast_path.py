"""growth-analytics SKILL.md is the slim fast path; references/full-map.md holds the full method.

Pins the split contract: SKILL.md stays at or under 6000 bytes, routes every reference with a trigger, carries the
hard rules and the key expectation terms itself (never via full-map.md), quotes each eval's ask phrase verbatim from its
prompt in evals.json, and the old body moves verbatim.
"""
import json
import pathlib
import re
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
D = ROOT / ".claude/skills/growth-analytics"
OLD_REF = "6388e04163c73e9bf64bb5f7839f31817ff53e1a"  # origin/main just before this split
OLD_PATH = ".claude/skills/growth-analytics/SKILL.md"


def flat(text):
    return " ".join(text.split())


SKILL = flat((D / "SKILL.md").read_text(encoding="utf-8"))
MAP = flat((D / "references/full-map.md").read_text(encoding="utf-8"))

# Each eval's ask/excuse phrase and each expectation must be answerable from SKILL.md alone.
QUICK = [
    "Never assert \"good retention is X%\"", "No baseline: `UNVERIFIED`, name what to instrument", "never estimate it",
    "the query to run in the user's analytics", "Reject vanity (cumulative signups, pageviews, downloads)",
    "name the input metrics", "Retention, activation, then acquisition", "doubling the ad budget amplifies it",
    "never track every click", "Size to stage", "stable pseudonymous user id", "`privacy-compliance.md`",
    "p = 0.03 on a 14-day test", "secondary click-through", "`UNVERIFIED`, not a win", "fixed N or duration read once",
    "always-valid mSPRT", "group-sequential alpha-spending", "primary and a guardrail", "CUPED",
    "about 30% relative, not 50%", "lead with the figure that does not reconcile", "concurrent email campaign",
    "ONE call", "not a menu or a request for more data", "at a level the plan does not already trip",
    "re-run length at stated traffic", "salvageable outside contaminated days", "the full event list",
    "before any caveat", "money consequence", "what each result means", "never close with \"share your data and I can help\"",
    "decision threshold the team sets", "retained-value metric",
    "multiple-comparison", "false-positive rate above the nominal 5%", "a secondary win is not cherry-picked",
    "a leaky bucket", "arbitrary round threshold is not a tripwire", "Leave a reserved decision", "break-even rate",
    "novelty, seasonality, mix shift, a lagging guardrail", "average order value",
    "`references/full-map.md`:", "`evals/evals.json`:",
]


def old_skill():
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"{OLD_REF}:{OLD_PATH}"], capture_output=True, text=True)
    if r.returncode:
        raise unittest.SkipTest("pre-slim commit not in this clone")
    return r.stdout


class SlimGa(unittest.TestCase):
    def test_skill_is_small(self):
        self.assertLessEqual((D / "SKILL.md").stat().st_size, 6011)

    def test_frontmatter_unchanged_and_single_h1(self):
        fm = lambda t: re.match(r"(?s)---\n.*?\n---\n", t).group(0)
        self.assertEqual(fm((D / "SKILL.md").read_text(encoding="utf-8")), fm(old_skill()))
        for rel in ("SKILL.md", "references/full-map.md"):
            self.assertEqual(len(re.findall(r"(?m)^# ", (D / rel).read_text(encoding="utf-8"))), 1, rel)

    def test_every_reference_and_script_is_routed_with_a_trigger(self):
        for ref in sorted((D / "references").glob("*.md")):
            self.assertIn(f"`references/{ref.name}`:", SKILL, f"{ref.name} not routed with a trigger from SKILL.md")
        for s in sorted((D / "scripts").glob("*.*")) if (D / "scripts").is_dir() else []:
            self.assertIn(f"`scripts/{s.name}`", SKILL, f"{s.name} not routed from SKILL.md")

    def test_escalate_names_every_moved_section(self):
        esc = SKILL.split("## Escalate: read this when")[1]
        for h in re.findall(r"(?m)^### \d+\. (.+)$", (D / "references/full-map.md").read_text(encoding="utf-8")):
            self.assertIn(" ".join(h.split()[:2]), esc, h)
        for h in ("Definition of done", "Anti-rationalization", "Standards", "Verification"):
            self.assertIn(h.lower(), esc.lower(), h)

    def test_quick_path_carries_its_contract(self):
        for p in QUICK:
            self.assertIn(p, SKILL, f"quick path missing: {p}")

    def test_every_eval_ask_phrase_is_verbatim_in_its_prompt_and_in_skill_md_alone(self):
        # The excuse bullet of each eval reads `- "<ask phrase>": ... (`<eval id>`)`; the phrase must be an exact
        # substring of that eval's prompt in evals.json (case and punctuation), and SKILL.md must carry it itself.
        evals = json.loads((D / "evals/evals.json").read_text(encoding="utf-8"))["evals"]
        raw = (D / "SKILL.md").read_text(encoding="utf-8")
        for e in evals:
            m = re.search(r'(?m)^- "(.+?)": .*\(`' + re.escape(e["id"]) + r'`\)', raw)
            self.assertIsNotNone(m, f"no quoted ask phrase for eval {e['id']} in SKILL.md")
            self.assertIn(m.group(1), e["prompt"], f"ask phrase is not verbatim in the eval prompt: {e['id']}")
            self.assertIn(m.group(1), SKILL, e["id"])

    def test_old_body_moved_verbatim(self):
        body = re.sub(r"(?s)^---.*?\n---\n\s*# Growth analytics\n", "", old_skill())
        self.assertIn(flat(body), MAP, "old SKILL.md body is not carried verbatim in full-map.md")


if __name__ == "__main__":
    unittest.main()
