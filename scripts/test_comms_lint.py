#!/usr/bin/env python3
"""Offline tests for communication-structure comms_lint.py: budgets table, every rule fires and clears, CLI contract."""
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, ".claude/skills/communication-structure")
LINT = os.path.join(SKILL, "scripts/comms_lint.py")
sys.path.insert(0, os.path.dirname(LINT))
import comms_lint as L  # noqa: E402

GOOD = {
    "status": """**Checkout migration at risk: 3 of 5 services moved (was 1); finish slips from 2026-10-20 to 2026-10-27 unless Acme's sandbox returns by Wednesday.**
✅ Orders service verified on staging: 412 of 412 tests pass. Ravi, 2026-10-15
⏳ Billing service: 2 of 3 tables moved. Ravi, due 2026-10-22
⏳ Acme sandbox back online, unverified since Monday. Dana to chase Acme, due 2026-10-19
Ask: Dana to choose A (slip to 2026-10-27) or B (ship read-only 2026-10-20) by Tue 2026-10-20.
""",
    "pr": """Adds a composite index on orders(customer_id, created_at): order-history p95 drops from 1.8 s to 35 ms on a 42M-row staging copy; Priya, please approve the schema change before Tue 2026-10-20.

**Why:** the order-history endpoint scans the table; p95 is 1.8 s for the largest tenants.
**Change:** `CREATE INDEX CONCURRENTLY`, so no table lock; 11 min on staging, +2.1 GB disk.
**Risk and rollback:** insert overhead at 900 writes/s is not measured. Rollback: `DROP INDEX CONCURRENTLY`; nothing depends on it yet.
**Verified:** ✅ staging query 35 ms over 3 runs  ⏳ insert throughput at peak, not measured; Priya to decide if it blocks, by Tue 2026-10-20
**Ask:** Priya to approve by Tue 2026-10-20.
""",
    "release": """**Export v2.4: CSV exports now include tax category and amount, and the old column order is retired on 2026-11-30.**
- Exports: two new columns, `Tax category` and `Amount`, appended after column 7; existing scripts that read by position are unaffected.
- Old format: removed on 2026-11-30; 14 of 120 accounts still request it.
Action: admins of those 14 accounts must switch to v2 exports by 2026-11-30.
""",
    "decision": """**Approve 22 seats of the tracing tool: $10,560 a year (22 seats x $480), inside the $15,000 limit.**
- A: buy 22 seats now; incident triage drops from about 40 min to 15 min in the vendor trial.
- B: wait a quarter; triage stays at 40 min and the discount (12%) expires on 2026-10-31.
- Not known: whether the vendor adds fees above 20 seats.
Ask: Elena to approve A or B by Fri 2026-10-23.
""",
    "incident": """**Checkout was down from 09:12 to 13:20 UTC (4 h 8 min) on 2026-10-12; no orders were lost and service is fully restored.**
- Impact: 31% of checkout attempts failed; 1,204 customers saw an error.
- Cause: an expired TLS certificate on the payments gateway, confirmed 13:05 UTC.
- Fix: ✅ certificate renewed 13:15 UTC and verified on production  ⏳ expiry alerting. Wen, due 2026-10-19
Customer action: none.
""",
    "readme": """Runs the review gates on a pull request in about 90 seconds.

`python3 scripts/ci-gates.sh routing .claude/skills/deep-code-review`

Expected result: `routing: ok` and exit code 0 for each of the 11 skill folders.
""",
    "meeting-notes": None,  # filled from scripts/comms-fixtures after read() is defined
    "message": "The export fix is merged and passes 412 of 412 tests; I am verifying it on staging now and will post the result by 16:00 UTC today.\n",
}
def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


GOOD["meeting-notes"] = read("scripts/comms-fixtures/meeting-notes-good.md")
SOURCE = "Orders service moved. Three of five services done, was one. Slip from October 20 to October 27. Acme sandbox down since Monday."


def rules(kind, text, source=None):
    r = L.lint(kind, text, source)
    return {x["rule"]: x for x in r["rules"]}, r


def failed(kind, text, source=None):
    return sorted(k for k, v in rules(kind, text, source)[0].items() if not v["ok"] and not v["advisory"])


def flagged(kind, text, source=None):
    """Rules with any hit, advisory ones (WARN) included."""
    return sorted(k for k, v in rules(kind, text, source)[0].items() if not v["ok"])


class Table(unittest.TestCase):
    def test_reference_table_is_the_source_of_truth(self):
        kinds = L.load_kinds()
        self.assertEqual(set(kinds), set(GOOD) | {"leadership"})
        known = {"numbers", "ask", "askif", "markers", "vocab", "timezone", "structure", "verified", "command", "nolead", "table", "numeric", "dri", "links"}
        for kind, (words, lines, checks) in kinds.items():
            self.assertGreater(words, 0)
            self.assertGreater(lines, 0)
            self.assertLessEqual(set(checks), known, kind)
        self.assertEqual(kinds["pr"], (200, 28, ("numbers", "askif", "verified")))
        self.assertEqual(kinds["message"], (200, 20, ()))

    def test_every_kind_has_a_template_in_the_reference(self):
        text = read(".claude/skills/communication-structure/references/artifact-templates.md")
        for kind in GOOD:
            self.assertIn(f"**{kind}**", text, kind)

    def test_list_matches_table(self):
        out = subprocess.run([sys.executable, LINT, "--list"], capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(len(out), len(L.load_kinds()))
        self.assertIn("pr\t200\t28\tnumbers,askif,verified", out)

    def test_missing_table_raises(self):
        with self.assertRaises(ValueError):
            L.load_kinds(LINT)


class GoldenGood(unittest.TestCase):
    def test_every_kind_template_example_passes(self):
        for kind, text in GOOD.items():
            self.assertEqual(failed(kind, text), [], f"{kind}: {L.render(L.lint(kind, text))}")

    def test_leadership_form_is_detected_and_structure_checked(self):
        good = read("scripts/status-update-fixtures/good.txt")
        res = L.lint("status", good)
        self.assertEqual(res["kind"], "leadership")
        self.assertEqual(failed("status", good), [])
        self.assertEqual(flagged("status", good), [])  # no source: the ask check does not run, nothing is demanded
        fixed = good.replace("Recommended: A, merge and publish today. B, keep holding.",
                             "Recommended: A, merge and publish today. Dana to reply A or B by Tue 2026-10-20.")
        self.assertEqual(failed("status", fixed), [])
        red = read("scripts/status-update-fixtures/red-live.txt")
        self.assertIn("structure", failed("status", red))


class Rules(unittest.TestCase):
    def test_lead_greeting_and_background_openers(self):
        for opener in ("Hi team, quick update on the migration.", "Just wanted to share where we are.", "Background: the export job was slow.",
                       "This PR aims to add an index.", "Thanks for the review.", "I wanted to reach out about 3 items."):
            self.assertIn("lead", failed("message", opener + "\nThe fix is merged, 12 of 12 tests pass.\n"), opener)

    def test_lead_buried_in_a_long_first_paragraph(self):
        long_lead = " ".join(["word"] * 70) + "."
        self.assertIn("lead", failed("message", long_lead))
        self.assertIn("lead", failed("message", "A " + " ".join(["word"] * 40) + ". Then more.\n"))  # first sentence over 35 words

    def test_lead_skips_headings_labels_greetings_and_subject_lines(self):
        text = "## Summary\n\nHi Dana,\n\n**Fixed the 3 export bugs; 412 of 412 tests pass.**\n"
        self.assertEqual(failed("message", text), [])
        self.assertIn("lead", failed("message", "## Summary\n\nHope you are well.\n"))
        self.assertIn("lead", failed("message", ""))

    def test_budget_words_and_lines_and_fenced_code_is_free(self):
        lines = "Merged: 12 of 12 tests pass.\n" + "\n".join("detail line %d" % i for i in range(35)) + "\n"
        self.assertIn("budget", failed("message", lines))  # 36 lines: over 1.5 x 20
        many_words = "Merged: 12 of 12 tests pass.\n" + " ".join(["more"] * 310) + "\n"
        self.assertIn("budget", failed("message", many_words))  # over 1.5 x 200 words
        between = "Merged: 12 of 12 tests pass.\n" + " ".join(["more"] * 250) + "\n"
        self.assertNotIn("budget", failed("message", between))  # over the target, under the ceiling: WARN only
        self.assertIn("length", flagged("message", between))
        self.assertTrue(L.lint("message", between)["ok"])
        fenced = "Merged: 12 of 12 tests pass.\n```\n" + "\n".join("log %d" % i for i in range(60)) + "\n```\n"
        self.assertNotIn("budget", failed("message", fenced))

    def test_numbers_needs_a_figure_in_the_lead_zone_for_long_bodies(self):
        body = "The migration is going to finish soon and the team is aligned on the plan for the remaining services.\n" + \
               "Nothing else is blocked and the rest of the work proceeds as planned by the same people today.\n" * 3
        self.assertIn("numbers", flagged("decision", body))
        self.assertTrue(L.lint("decision", body)["ok"])  # WARN only: the input may hold no figure
        self.assertNotIn("numbers", flagged("decision", body.replace("soon", "by 2026-10-27")))
        self.assertNotIn("numbers", flagged("decision", "No figures here at all.\n"))  # under 60 words

    def test_ask_is_checked_only_against_an_ask_in_the_source(self):
        base, src = GOOD["decision"], "Elena has to approve A or B by Friday 2026-10-23."
        ask = "Ask: Elena to approve A or B by Fri 2026-10-23."
        for bad, miss in (("Ask: choose A or B.", "owner"), ("Ask: Elena to approve A or B.", "date"), ("Ask: approve.", "date")):
            res = rules("decision", base.replace(ask, bad), src)[0]["ask"]
            self.assertFalse(res["ok"], bad)
            self.assertTrue(res["advisory"])  # WARN: forcing owner and date taught stand-ins readers rejected
            self.assertIn(miss, res["hits"][0]["problem"])
        self.assertNotIn("ask", flagged("decision", base, src))
        self.assertNotIn("ask", flagged("decision", base.replace(ask, "Ask: choose A or B.")))  # no source: nothing demanded
        self.assertNotIn("ask", flagged("decision", base.replace(ask, "Ask: approve."), "Please decide."))  # source has no owner or date to carry over
        quiet = " ".join(["Costs are 12 percent lower and triage takes 15 minutes."] * 8) + "\n"
        self.assertIn("ask", flagged("decision", quiet, src))  # the draft drops the source's ask
        for stand_in in ("Ask: owner unassigned, no deadline.", "Ask: Elena to approve; no deadline given.", "Rollback: not stated."):
            self.assertIn("placeholder", failed("decision", base.replace(ask, stand_in)), stand_in)

    def test_ask_heading_form_reads_the_next_line(self):
        text = GOOD["decision"].replace("Ask: Elena to approve A or B by Fri 2026-10-23.", "**Decision needed**\nElena to approve A or B by Fri 2026-10-23.")
        self.assertNotIn("ask", flagged("decision", text, "Elena must approve by Friday 2026-10-23."))

    def test_pr_ask_check_needs_an_ask_in_the_source(self):
        pr = GOOD["pr"].replace("**Ask:** Priya to approve by Tue 2026-10-20.\n", "")
        self.assertNotIn("ask", flagged("pr", pr))
        self.assertNotIn("ask", flagged("pr", pr, "Priya, please approve before Tuesday."))  # the draft still asks ("please approve")
        quiet = " ".join(["The index cuts p95 from 1.8 s to 35 ms on 42M rows."] * 8) + "\n"
        self.assertIn("ask", flagged("pr", quiet, "Priya, please approve before Tuesday."))
        self.assertNotIn("ask", flagged("pr", quiet, "The index cuts p95."))

    def test_markers_are_advisory(self):
        base = GOOD["status"]
        self.assertIn("markers", flagged("status", base.replace("✅", "-").replace("⏳", "-")))
        self.assertIn("markers", flagged("status", base.replace("verified on staging: 412 of 412 tests pass.", "looks fine.")))
        self.assertIn("markers", flagged("status", base.replace("Ravi, due 2026-10-22", "later")))
        self.assertTrue(L.lint("status", base.replace("✅", "-").replace("⏳", "-"))["ok"])

    def test_weekday_must_fit_the_date(self):
        for bad in ("Decide by Wed 2026-10-22.", "Decide by Wednesday, October 22, 2026.", "Decide by Wed 10/22/2026."):
            self.assertIn("dates", failed("message", bad), bad)
        for good in ("Decide by Thu 2026-10-22.", "Decide by Thursday, Oct 22, 2026.", "Decide by Thu 10/22/2026.", "Decide by Tuesday.", "Decide by 31/12."):
            self.assertNotIn("dates", failed("message", good), good)
        self.assertIn("dates", failed("message", "Decide by Wed 2026-10-22."))  # the report names the real day
        self.assertIn("Thursday", L.render(L.lint("message", "Decide by Wed 2026-10-22.")))

    def test_vocab_flags_live_without_evidence(self):
        text = GOOD["release"].replace("two new columns", "two new columns, live now")
        self.assertIn("vocab", failed("release", text))
        self.assertNotIn("vocab", failed("release", text.replace("live now", "live now (verified-on-export page)")))

    def test_timezone(self):
        text = GOOD["incident"]
        self.assertIn("timezone", flagged("incident", text.replace("09:12 to 13:20 UTC", "09:12 to 13:20")))
        self.assertTrue(L.lint("incident", text.replace("09:12 to 13:20 UTC", "09:12 to 13:20"))["ok"])  # WARN only
        self.assertNotIn("timezone", flagged("incident", text.replace("09:12 to 13:20 UTC", "09:12 to 13:20 (zone not given)")))
        self.assertNotIn("timezone", flagged("incident", text.replace("09:12 to 13:20 UTC", "09:12 PT to 13:20 PT")))

    def test_verified_for_pr_and_command_for_readme(self):
        self.assertIn("verified", flagged("pr", GOOD["pr"].replace("**Verified:** ✅ staging query 35 ms over 3 runs  ⏳ insert throughput at peak, not measured; Priya to decide if it blocks, by Tue 2026-10-20\n", "")))
        no_cmd = GOOD["readme"].replace("`python3 scripts/ci-gates.sh routing .claude/skills/deep-code-review`", "Run the gates.").replace("`routing: ok`", "ok")
        longer = no_cmd + "The gates cover routing, version stamps, privacy and size budgets across eleven skill folders and run the same way in CI as on a laptop, so a local failure predicts a pull request failure before anything is pushed or reviewed by anyone.\n"
        self.assertIn("command", failed("readme", longer))
        self.assertNotIn("command", failed("readme", GOOD["readme"] + longer.split("\n", 4)[-1]))

    def test_filler_placeholder_vague(self):
        base = GOOD["decision"]
        for kind, phrase in (("filler", "A robust and comprehensive plan."), ("filler", "Feel free to reach out."), ("placeholder", "Owner: [owner]."),
                             ("placeholder", "TBD by finance."), ("vague", "Costs are significantly lower.")):
            self.assertIn(kind, failed("decision", base + phrase + "\n"), phrase)
        self.assertNotIn("vague", failed("decision", base + "Costs fell significantly: 40 min to 15 min.\n"))
        self.assertEqual(failed("decision", base + "That is statistically significant (p = 0.01).\n"), [])

    def test_hedge_is_advisory_and_does_not_fail(self):
        r = L.lint("decision", GOOD["decision"] + "It depends on the vendor.\n")
        self.assertTrue(r["ok"])
        hedge = [x for x in r["rules"] if x["rule"] == "hedge"][0]
        self.assertTrue(hedge["advisory"] and not hedge["ok"])
        self.assertIn("WARN hedge", L.render(r))

    def test_grounded_flags_figures_and_claims_the_source_lacks(self):
        draft = "**Three of 5 services moved; the 4 lost days slip launch to Oct 27, and I recommend A.**\n"
        bad = failed("message", draft, SOURCE)
        self.assertEqual(bad, ["grounded"])
        hits = [h["problem"] for h in rules("message", draft, SOURCE)[0]["grounded"]["hits"]]
        self.assertTrue(any("4" in h for h in hits) and any("recommend" in h for h in hits))
        self.assertEqual(failed("message", "Three of 5 services moved; launch slips to Oct 27.\n", SOURCE), [])
        self.assertEqual(failed("message", "Roughly 15 days remain (~ 27 minus 12).\n", SOURCE), [])  # marked as estimated
        self.assertEqual(failed("message", "Orders: 3 x 4 = 12 checks.\n", "Orders: 3 services, 4 checks, 12 total"), [])
        self.assertEqual(failed("message", "We lost 4 days.\n", "we have lost four days of testing"), [])  # spelled-out number in the source
        self.assertEqual(failed("message", "1. Option 2 wins.\n", "option B wins"), [])  # list index and option label are not figures
        self.assertNotIn("grounded", rules("message", draft)[0])  # no source, no check

    def test_below_sixty_words_skips_structural_rules(self):
        r = L.lint("pr", "Fixes a typo in the README.\n")
        self.assertTrue(r["ok"])
        self.assertEqual({x["rule"] for x in r["rules"]}, {"lead", "budget", "dates", "filler", "placeholder", "vague", "hedge"})


class MeetingNotes(unittest.TestCase):
    def test_good_fixture_passes_and_bad_fixture_trips_every_meeting_rule(self):
        self.assertEqual(failed("meeting-notes", GOOD["meeting-notes"]), [])
        bad = read("scripts/comms-fixtures/meeting-notes-bad.md")
        self.assertEqual(failed("meeting-notes", bad), ["dri", "links", "numeric", "table"])
        probs = " ".join(h["problem"] for r in L.lint("meeting-notes", bad)["rules"] for h in r["hits"])
        for want in ("bullet above the table", "emoji", "status key", "repeats line", "top-level line", "no DRI", "not a link", "Decided: line has no link"):
            self.assertIn(want, probs)

    def test_no_table_and_blank_dri_and_bluf_is_not_required(self):
        self.assertIn("table", failed("meeting-notes", "1. Billing moves to 2026-10-27.\n"))
        self.assertNotIn("lead", {r["rule"] for r in L.lint("meeting-notes", GOOD["meeting-notes"])["rules"]})
        self.assertIn("dri", failed("meeting-notes", GOOD["meeting-notes"].replace("DRI: not set", "DRI:")))
        self.assertEqual(failed("meeting-notes", GOOD["meeting-notes"].replace("[#1541](https://example.com/pr/1541)", "[#1541](u)")), [])


class Cli(unittest.TestCase):
    def run_cli(self, *args, stdin=None):
        return subprocess.run([sys.executable, LINT, *args], input=stdin, capture_output=True, text=True)

    def test_exit_codes_and_report(self):
        ok = self.run_cli("--kind", "message", stdin=GOOD["message"])
        self.assertEqual((ok.returncode, ok.stdout.strip().endswith("ok")), (0, True))
        bad = self.run_cli("--kind", "message", stdin="Hope you are well, just wanted to share an update.\n")
        self.assertEqual(bad.returncode, 1)
        self.assertRegex(bad.stdout, r"FAIL lead L1: .*Fix: ")
        self.assertIn("BELOW BAR", bad.stdout)
        self.assertEqual(self.run_cli().returncode, 2)
        self.assertEqual(self.run_cli("--kind", "nope").returncode, 2)
        self.assertEqual(self.run_cli("--kind", "pr", "--file", "/nonexistent/x.md").returncode, 2)

    def test_json_output_and_source_file(self):
        out = self.run_cli("--kind", "message", "--json", stdin=GOOD["message"])
        data = json.loads(out.stdout)
        self.assertTrue(data["ok"])
        self.assertEqual(data["budget"], [200, 20])
        self.assertTrue(all({"rule", "ok", "advisory", "hits"} <= set(r) for r in data["rules"]))
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".md") as f:
            f.write("services are 7 now")
            f.flush()
            bad = self.run_cli("--kind", "message", "--source", f.name, stdin="Moved 9 services.\n")
        self.assertEqual(bad.returncode, 1)
        self.assertRegex(bad.stdout, r"grounded L1: figure not in the source: 9")


if __name__ == "__main__":
    unittest.main()
