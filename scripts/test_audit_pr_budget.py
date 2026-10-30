#!/usr/bin/env python3
"""comms_lint audit-pr budget: the table budget (1200 words, 160 lines, fail above 1.5x) counts everything outside
`## Changes by area`; each `### ` area there fails above 200 words and the whole body above 3000. A body written to the
template with many areas must pass, and the reference states the same numbers. Synthetic input (Acme); no network."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude/skills/communication-structure/scripts"))
import comms_lint as L  # noqa: E402

REFERENCE = ROOT / ".claude/skills/communication-structure/references/artifact-templates.md"


def words(n):
    return " ".join(["plain"] * n)


def body(areas=(), bullets=(), deps=""):
    """An audit-pr body in the template's shape. `areas`: a word count per `### Area N` heading; `bullets`: a word count per
    `- **Area N:**` bullet (the template's own form); `deps`: text for `## Dependency upgrades` (outside the areas section)."""
    out = ["## Summary", "Adds sign-in checks to the Acme export routes. Please review the new limit.",
           "## What changes for reviewers and users", "- GET /export now needs sign-in.", "## Changes by area"]
    out += [f"### Area {i}\n{words(n)}" for i, n in enumerate(areas)]
    out += [f"- **Area {i}:** {words(n)}" for i, n in enumerate(bullets)]
    out += ["## Dependency upgrades", deps] if deps else []
    out += ["## How to verify", "✅ `npm test` on this head: 42/42 pass.", "## Not fixed", "2 high, 5 medium, tracked privately."]
    return "\n".join(out) + "\n"


def hits(res, rule):
    return [h for r in res["rules"] if r["rule"] == rule for h in r["hits"]]


def bullets_of(n_lines, n_words=30):
    return "\n".join("- " + words(n_words) for _ in range(n_lines))


class Budget(unittest.TestCase):
    def test_many_areas_pass_though_the_body_is_over_the_table_budget(self):
        text = body(areas=[190] * 10)
        self.assertGreater(len(text.split()), 1800)  # over 1.5 x 1200: the earlier rule failed this
        res = L.lint("audit-pr", text)
        self.assertEqual(hits(res, "budget"), [])
        self.assertTrue(res["ok"])

    def test_bullet_areas_of_the_template_are_outside_the_budget_too(self):
        res = L.lint("audit-pr", body(bullets=[250] * 8))  # eight areas, 2000+ words
        self.assertEqual(hits(res, "budget"), [])
        self.assertTrue(res["ok"])

    def test_an_area_over_the_cap_fails_at_its_heading(self):
        text = body(areas=[150, 201, 150])
        res = L.lint("audit-pr", text)
        (h,) = hits(res, "budget")
        self.assertEqual(h["line"], text.splitlines().index("### Area 1") + 1)
        self.assertIn("area 'Area 1' is 201 words against 200", h["problem"])
        self.assertIn(h["problem"], L.render(res))
        self.assertFalse(res["ok"])

    def test_an_area_at_the_cap_passes(self):
        self.assertEqual(hits(L.lint("audit-pr", body(areas=[200])), "budget"), [])

    def test_whole_body_hard_cap(self):
        base = body(areas=[190] * 15)

        def total(n):  # a body of exactly n words: a last area of the right length, 200 words or fewer
            return body(areas=[190] * 15 + [n - len(base.split()) - 3])

        for n, fails in ((3000, False), (3001, True)):
            text = total(n)
            self.assertEqual(len(text.split()), n)
            res = L.lint("audit-pr", text)
            self.assertEqual([h["problem"] for h in hits(res, "budget")], [f"{n} words against the 3000 hard cap for audit-pr"] * fails)
            self.assertEqual(res["ok"], not fails)

    def test_outside_the_areas_section_the_table_budget_still_applies(self):
        res = L.lint("audit-pr", body(areas=[100], deps=bullets_of(60)))  # about 1900 words outside the section
        (h,) = hits(res, "budget")
        self.assertIn("outside `## Changes by area` against 1200 / 160 for audit-pr", h["problem"])
        self.assertFalse(res["ok"])

    def test_between_the_table_value_and_1_5x_outside_it_only_warns(self):
        res = L.lint("audit-pr", body(areas=[100], deps=bullets_of(50)))  # about 1600 words outside the section
        self.assertEqual(hits(res, "budget"), [])
        self.assertTrue(hits(res, "length"))
        self.assertTrue(res["ok"])

    def test_without_the_areas_section_the_whole_body_is_counted(self):
        res = L.lint("audit-pr", body(areas=[100], deps=bullets_of(60)).replace("## Changes by area", "## Elsewhere"))
        (h,) = hits(res, "budget")
        self.assertNotIn("outside", h["problem"])

    def test_fenced_lines_neither_count_nor_split_an_area(self):
        text = body(areas=[150]).replace("### Area 0\n", "### Area 0\n" + words(150) + "\n```\n### Not an area\n" + words(300) + "\n```\n")
        (h,) = hits(L.lint("audit-pr", text), "budget")
        self.assertIn("area 'Area 0' is 300 words", h["problem"])  # 150 + 150 prose words; the fenced 300 and its heading are not counted

    def test_a_deeper_heading_stays_in_its_area(self):
        text = body(areas=[120]).replace("### Area 0\n", "### Area 0\n" + words(120) + "\n#### Detail\n")
        (h,) = hits(L.lint("audit-pr", text), "budget")
        self.assertIn("area 'Area 0' is 242 words", h["problem"])

    def test_reported_words_and_lines_are_what_the_budget_counts(self):
        res = L.lint("audit-pr", body(areas=[190] * 10))
        self.assertLess(res["words"], 100)
        self.assertLess(res["lines"], 20)
        self.assertIn(f"{res['words']}/1200 words, {res['lines']}/160 lines", L.render(res))
        msg = "Cleanup now runs hourly. Review by Friday 2026-10-30."  # other kinds count the whole body
        self.assertEqual(L.lint("message", msg)["words"], len(msg.split()))

    def test_reference_states_the_scope_and_the_caps(self):
        doc = REFERENCE.read_text(encoding="utf-8")
        para = doc[doc.index("`audit-pr` is the body"):doc.index("## Templates")]
        for want in ("outside `Changes by area`", f"{L.AREA_WORDS} words", f"{L.TOTAL_WORDS} words"):
            self.assertIn(want, para)
        self.assertEqual((L.AREA_WORDS, L.TOTAL_WORDS), (200, 3000))
        self.assertEqual(L.load_kinds()["audit-pr"][:2], (1200, 160))


if __name__ == "__main__":
    unittest.main()
