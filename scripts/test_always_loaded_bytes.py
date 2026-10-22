#!/usr/bin/env python3
"""Ratchet on the bytes a default Perun install loads into every session (scripts/always_loaded_bytes.py), plus a
check that every trigger keyword survives trimming. Offline; runs the SessionStart hooks in a temp dir.

Lowering BUDGET after a further trim is welcome; raising it needs a stated reason (the budget only moves down)."""
import os
import sys
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import always_loaded_bytes as alb  # noqa: E402
from trigger_coverage import description  # noqa: E402

ROOT = os.path.dirname(HERE)
# 3952 adds the /critic, /council, /idea command descriptions (+84 B over 3868 after trimming); 3889 included the restored "jurisdiction-specific" business-ops trigger (+23 B over 3866); baseline was 4000.
BUDGET = 3952  # total bytes across skill_descriptions + command_descriptions + sessionstart_hooks (baseline 4000)

# Trigger keywords each skill description must keep (the words a model matches a task against).
KEYWORDS = {
    "agentic-ceo": ["START", "multi-step", "multi-skill", "choosing a skill", "Conductor", "idea-critic",
                    "communication-structure", "human-facing", "agentic-delivery", "deep-code-review",
                    "idea-critic before any plan or owner ask", "communication-structure before any human-facing message",
                    "agentic-delivery to build, deep-code-review to review"],
    "agentic-delivery": ["feature", "migration", "end-to-end", "build", "ship", "deliver", "fix a ticket", "FIRST",
                         "Invoke FIRST, before inspecting files",
                         "independent QA and security", "one writer per worktree", "human approval", "Not a typo fix"],
    "business-ops": ["pricing", "unit economics", "LTV/CAC", "runway", "TAM sizing", "legal", "tax", "accounting",
                     "fundraising", "Leads with the call", "professional", "Educational, not advice", "--with-business",
                     "routes the binding, jurisdiction-specific part to a professional"],
    "communication-structure": ["BEFORE", "PR body", "issue/PR comment", "status update", "reply", "report", "plan",
                                "summary", "table", "BLUF", "one ask", "AI-slop", "Skip for chat",
                                "Skip for chat with the user"],
    "contribution": ["upstream improvement", "generalizable lesson", "fix", "private work", "skillset",
                     "third-party identifiers", "privacy gate", "draft the PR", "a human opens it",
                     "--with-contribution"],
    "deep-code-review": ["reviewing", "auditing", "hardening", "red-teaming", "quality-gating", "PR", "diff",
                         "even without the word review", "file:line", "correctness", "security", "a11y", "privacy"],
    "growth-analytics": ["measure", "North Star", "AARRR", "retention first", "event taxonomy", "A/B",
                         "never fabricates benchmarks", "product-discovery", "--with-growth"],
    "idea-critic": ["BEFORE", "owner", "plan", "architecture", "unsolicited", "we should", "Skeptic", "better-way",
                    "kill-criteria", "HOLD", "REVISE", "PASS_TO_USER", "Not code review", "--with-critic", "--full",
                    "BEFORE asking the owner anything",
                    "Skeptic, better-way, kill-criteria hats return HOLD, REVISE or PASS_TO_USER",
                    "Owner-request cannot HOLD"],
    "positioning": ["positioned", "value proposition", "segment", "differentiation", "messaging",
                    "Value Proposition Canvas", "message house", "real buyers", "never fabricates",
                    "--with-positioning"],
    "product-discovery": ["worth building", "what to build first", "what not to build", "Mom-Test",
                          "riskiest-assumption", "PMF survey", "ICE", "Never fabricates findings", "--with-discovery"],
    "product-output-safety": ["OWN AI outputs", "automated decisions", "bias", "hallucination", "AI disclosure",
                              "high-stakes", "MAP, MEASURE, MANAGE", "human gate", "never certifies safe",
                              "--with-output-safety"],
}
COMMAND_KEYWORDS = {
    "cost-retro": ["session", "spent", "cheaper"],
    "critic": ["idea-critic", "claim"],
    "council": ["Veche", "council"],
    "deliver": ["gated"],
    "idea": ["idea", "one-page"],
    "perun-run": ["owner-authorised", "autonomous run", "task ledger"],
    "perun": ["weekly value receipt"],
    "review": ["deep code review", "diff"],
}
HOST_RULE_KEYWORDS = ["sleep N", "completion notification", "Monitor", "cd X &&", "worktree root", "INDEX.md"]


def missing(text, words):
    """The words/phrases (case-insensitive) absent from `text`."""
    return [w for w in words if w.lower() not in text.lower()]


class AlwaysLoadedBytes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = alb.measure(ROOT)

    def test_total_within_ratchet(self):
        total = sum(n for items in self.data.values() for _, n in items)
        self.assertLessEqual(total, BUDGET, f"always-loaded bytes {total} > budget {BUDGET}")

    def test_every_source_measured(self):
        self.assertEqual({n for n, _ in self.data["skill_descriptions"]}, set(KEYWORDS))
        self.assertEqual({n[1:] for n, _ in self.data["command_descriptions"]}, set(COMMAND_KEYWORDS))
        self.assertGreater(dict(self.data["sessionstart_hooks"])["session_brief.py"], 0)

    def test_skill_trigger_keywords_kept(self):
        for skill, words in KEYWORDS.items():
            path = os.path.join(ROOT, ".claude/skills", skill, "SKILL.md")
            gone = missing(description(Path(path).read_text(encoding="utf-8")), words)
            self.assertEqual(gone, [], f"{skill}: trigger keywords/phrases dropped from description")

    def test_dropping_a_qualifier_is_caught(self):
        """Mutation check: the pinned phrases fail when one qualifier is removed from the real description."""
        text = description(Path(ROOT, ".claude/skills/business-ops/SKILL.md").read_text(encoding="utf-8"))
        self.assertEqual(missing(text, KEYWORDS["business-ops"]), [])
        self.assertTrue(missing(text.replace("jurisdiction-specific ", ""), KEYWORDS["business-ops"]))
        ceo = description(Path(ROOT, ".claude/skills/agentic-ceo/SKILL.md").read_text(encoding="utf-8"))
        self.assertTrue(missing(ceo.replace("any plan or ", ""), KEYWORDS["agentic-ceo"]))

    def test_command_keywords_kept(self):
        for cmd, words in COMMAND_KEYWORDS.items():
            text = Path(ROOT, "commands", cmd + ".md").read_text(encoding="utf-8").split("---")[1].lower()
            for w in words:
                self.assertIn(w.lower(), text, f"/{cmd}: keyword {w!r} dropped")

    def test_host_rules_keywords_kept(self):
        sys.path.insert(0, os.path.join(ROOT, ".claude/skills/agentic-delivery/scripts"))
        from subagent_start_inject import HOST_RULES
        for w in HOST_RULE_KEYWORDS:
            self.assertIn(w, HOST_RULES)


if __name__ == "__main__":
    unittest.main()
