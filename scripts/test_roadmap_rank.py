#!/usr/bin/env python3
"""Tests for agentic-ceo's roadmap_rank.py (the CEO improvement loop's scorer) and for the
committed Perun roadmap built from docs/roadmap-input.json. Offline, stdlib only."""
import contextlib
import copy
import csv
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / ".claude/skills/agentic-ceo/scripts/roadmap_rank.py"
spec = importlib.util.spec_from_file_location("roadmap_rank", SCRIPT)
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)

CTX = {k: {"value": k + " value", "src": "README.md"}
       for k in ("stage", "vision", "north_star", "direction", "constraints")}
CTX["stage"]["value"] = "mvp"
SOURCED = dict(reach_src="README.md", impact_src="README.md")


def item(i, **kw):
    d = {"id": i, "title": f"{i.upper()} {i}-{i}-{i}", "lever": "reliability", "evidence": ["README.md"],
         "reach": 4, "reach_src": "assumed: x", "impact": 2, "impact_src": "assumed: x",
         "effort": 2, "effort_src": "assumed: x",
         "vision": "aligned", "vision_reason": "serves delivery", "metric": "p95 from 10 s to 5 s",
         "risks": "r", "where": "scripts/", "done_when": "d", "verify": "v"}
    d.update(kw)
    return d


def data(*items, **over):
    d = {"as_of": "2026-10-16", "context": copy.deepcopy(CTX), "items": list(items)}
    d.update(over)
    return d


def run(d, *args):
    """Write d as JSON, run main(), return (exit code, stdout, stderr)."""
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "in.json"
        p.write_text(json.dumps(d))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = rr.main([str(p), "--root", str(ROOT), *args])
    return rc, out.getvalue(), err.getvalue()


def ranked(d):
    r, errs = rr.build(d, ROOT)
    assert not errs, errs
    return r


def ids(r, key="ranked"):
    return [x["it"]["id"] for x in r[key]]


class Scoring(unittest.TestCase):
    def test_formula_and_order_by_hand(self):
        a = item("a")  # 4 x 2 x 0.5 (assumed) / 2 x 1.25 reliability x 1.0 = 2.5
        b = item("b", lever="learning", reach=5, impact=1, effort=1, vision="partial", **SOURCED)  # 5 x 1 x 1.0 / 1 x 1.5 x 0.5 = 3.75
        r = ranked(data(a, b))
        self.assertEqual((ids(r), [round(x["s"], 6) for x in r["ranked"]]), (["b", "a"], [3.75, 2.5]))
        out = run(data(a, b))[1]
        self.assertIn("| 1 | `b` B b-b-b | open | -, learning | 3.75 |", out)
        self.assertIn("2.50 = 4 × 2 × 0.5 ÷ 2 × 1.25 × 1 (open rank 2 of 2); assumed: reach impact effort", out)

    def test_confidence_is_computed_from_real_sources_only(self):
        conf = lambda **kw: ranked(data(item("a", **kw)))["ranked"][0]["conf"]
        for good in ("README.md#x", "https://example.com/x", "issue:#1", "pr:#2"):
            self.assertEqual(conf(reach_src=good, impact_src=good), 1.0, good)
        # an assumed reach or impact keeps confidence at 0.5, whatever else is sourced
        self.assertEqual(conf(reach_src="README.md", impact_src="assumed: y"), 0.5)
        self.assertEqual(conf(reach_src="assumed: y", impact_src="README.md"), 0.5)
        # effort alone does not lower confidence
        self.assertEqual(conf(effort_src="assumed: y", **SOURCED), 1.0)

    def test_assumed_cannot_be_bypassed_by_wording(self):
        for fake in ("estimate: 4 of 5 runs", "~assumed", "assumed", "ASSUMED: y", "see the survey", "docs/does-not-exist.md",
                     "/etc/hosts", "owner:2026-10-16", "survey:2026-10-16#P1", "measured: yes", "README.md with some words"):
            r = ranked(data(item("a", reach_src=fake, impact_src="README.md")))
            self.assertEqual(r["ranked"][0]["conf"], 0.5, fake)
            self.assertIn("reach", r["ranked"][0]["asm"], fake)

    def test_typed_confidence_is_rejected(self):
        rc, _, err = run(data(item("a", confidence=1.0)))
        self.assertEqual(rc, 2)
        self.assertIn("confidence is computed", err)

    def test_stage_changes_the_order(self):
        polish, learn = item("p", lever="polish"), item("l", lever="learning")
        order = lambda stage: ids(ranked(data(polish, learn, context={**CTX, "stage": {"value": stage, "src": "README.md"}})))
        self.assertEqual((order("mvp"), order("mature")), (["l", "p"], ["p", "l"]))

    def test_weights_override_is_printed_and_applied(self):
        c = {**CTX, "weights": {"polish": [9, 9, 9, 9]}}
        self.assertEqual(ids(ranked(data(item("p", lever="polish"), item("l", lever="learning"), context=c)))[0], "p")
        self.assertIn("| polish (override) | 9 | **9** | 9 | 9 |", run(data(item("p", lever="polish"), context=c))[1])
        self.assertEqual(run(data(item("p"), context={**CTX, "weights": {"nope": [1, 1, 1, 1]}}))[0], 2)

    def test_ties_break_on_fewer_assumed_inputs_then_effort_then_id(self):
        # a and b both score 2.5; b backs reach and impact with sources, so it outranks a despite the id order
        a = item("a", reach=4, impact=2, effort=2)
        b = item("b", reach=2, impact=2, effort=2, **SOURCED)
        r = ranked(data(a, b))
        self.assertEqual([round(x["s"], 6) for x in r["ranked"]], [2.5, 2.5])
        self.assertEqual(ids(r), ["b", "a"])
        # same score, same assumed inputs: lower effort first, then id
        r = ranked(data(item("z", effort=1, reach=2), item("b", effort=2), item("a", effort=2)))
        self.assertEqual(ids(r), ["z", "a", "b"])

    def test_deterministic(self):
        d = data(item("a"), item("b", effort=3))
        self.assertEqual(run(d), run(d))


class GatePricing(unittest.TestCase):
    def eff(self, **kw):
        return ranked(data(item("a", **kw)))["ranked"][0]["eff"]

    def test_each_owner_gate_adds_two_lane_days_and_waits_add_a_quarter_per_day(self):
        self.assertEqual(self.eff(), 2)
        self.assertEqual(self.eff(gate="owner: external send"), 4)
        self.assertEqual(self.eff(gate=["owner: paid run", "owner: vendor key"]), 6)
        self.assertEqual(self.eff(wait_days=8), 4)
        self.assertEqual(self.eff(gate="owner: send", wait_days=4), 5)

    def test_a_gate_lowers_the_score_and_shows_in_the_inputs_table(self):
        free, gated = ranked(data(item("a"))), ranked(data(item("a", gate="owner: send")))
        self.assertEqual((free["ranked"][0]["s"], gated["ranked"][0]["s"]), (2.5, 1.25))
        out = run(data(item("a", gate="owner: send", wait_days=4)))[1]
        self.assertIn("| 2 + 2 + 1 = 5 |", out)

    def test_a_gated_item_loses_to_an_equal_ungated_one(self):
        r = ranked(data(item("a", gate="owner: send"), item("b")))  # same typed inputs: the gated one costs 2 more lane-days
        self.assertEqual(ids(r), ["b", "a"])
        self.assertEqual([x["eff"] for x in r["ranked"]], [2, 4])

    def test_bad_gate_or_wait_is_bad_input(self):
        self.assertEqual(run(data(item("a", gate=["ok", ""])))[0], 2)
        self.assertEqual(run(data(item("a", wait_days=-1)))[0], 2)


class Rejection(unittest.TestCase):
    def test_vision_misaligned_is_rejected_with_its_reason(self):
        m = item("m", vision="misaligned", vision_reason="breaks a stated constraint")
        r = ranked(data(item("a"), m))
        self.assertEqual(ids(r), ["a"])
        self.assertEqual(r["rejected"][0][1:], ("vision: misaligned", "breaks a stated constraint"))
        self.assertIn("| `m` M m-m-m | vision: misaligned | breaks a stated constraint |", run(data(m))[1])

    def test_a_rejection_without_a_reason_is_bad_input(self):
        rc, _, err = run(data(item("m", vision="misaligned", vision_reason=" ")))
        self.assertEqual(rc, 2)
        self.assertIn("a rejection needs a stated reason", err)

    def test_ceo_reject_needs_only_id_title_reason(self):
        r = ranked(data({"id": "x", "title": "Already shipped thing", "reject": "shipped in 1.586.0"}, item("a")))
        self.assertEqual(r["rejected"][0][1:], ("CEO decision", "shipped in 1.586.0"))

    def test_critic_hold_rejects_and_reorders(self):
        hold = {"verdict": "HOLD", "independence": "inline", "dissent_ledger": "kill: costs more than it saves"}
        r = ranked(data(item("a", critic=hold), item("b", effort=4)))
        self.assertEqual(ids(r), ["b"])
        self.assertEqual(r["rejected"][0][1:], ("idea-critic: HOLD", "kill: costs more than it saves"))


class InFlight(unittest.TestCase):
    def flight(self, i="f", **kw):
        return item(i, status="in_flight", where="", done_when="", verify="", **kw)

    def test_in_flight_is_scored_flagged_and_kept_out_of_issues_and_critic(self):
        f = self.flight(**SOURCED, effort=1)  # 4 x 2 x 1 / 1 x 1.25 = 10: ranks first overall
        d = data(f, item("a"))
        r = ranked(d)
        self.assertEqual((ids(r), ids(r, "opens")), (["f", "a"], ["a"]))
        self.assertTrue(r["ranked"][0]["flight"])
        out = run(d)[1]
        self.assertIn("| 1 | `f` F f-f-f | in flight |", out)
        self.assertIn("`f` 10.00 (in flight)", out)
        self.assertNotIn("### P1: F f-f-f", out)
        self.assertIn("### P1: A a-a-a", out)

    def test_strict_looks_only_at_open_items(self):
        ok = {"verdict": "PASS_TO_USER", "independence": "inline", "strongest_attack_survived": "cost"}
        d = data(self.flight(effort=1), item("a", critic=ok), item("b", critic=ok, effort=3), item("c", critic=ok, effort=4))
        self.assertEqual(run(d, "--strict")[0], 0)

    def test_in_flight_still_needs_scoring_inputs_but_not_issue_fields(self):
        f = self.flight()
        del f["reach"]
        self.assertIn("reach is missing", run(data(f))[2])
        self.assertEqual(run(data(self.flight()))[0], 0)


class Critic(unittest.TestCase):
    def three(self, **crit):
        return data(*[item(i, effort=e, **({"critic": crit} if crit else {})) for i, e in (("a", 1), ("b", 2), ("c", 3))])

    def test_top3_without_critic_is_unverified_and_strict_fails(self):
        d = self.three()
        rc, out, err = run(d)
        self.assertEqual(rc, 0)
        self.assertEqual(out.count("**UNVERIFIED**, idea-critic has not run"), 3)
        self.assertEqual(run(d, "--strict")[0], 1)

    def test_pass_everywhere_satisfies_strict_and_revise_does_not(self):
        ok = {"verdict": "PASS_TO_USER", "independence": "inline", "strongest_attack_survived": "cost; capped by effort"}
        self.assertEqual(run(self.three(**ok), "--strict")[0], 0)
        rc, out, _ = run(self.three(verdict="REVISE", independence="inline"), "--strict")
        self.assertEqual(rc, 1)
        self.assertIn("Unresolved REVISE (not a pass)", out)

    def test_bad_critic_is_bad_input(self):
        self.assertEqual(run(self.three(verdict="MAYBE", independence="inline"))[0], 2)
        self.assertEqual(run(self.three(verdict="PASS_TO_USER", independence="inline"))[0], 2)


class Input(unittest.TestCase):
    def test_context_is_required_and_stage_must_be_known(self):
        d = data(item("a"))
        del d["context"]["north_star"]
        rc, _, err = run(d)
        self.assertEqual(rc, 2)
        self.assertIn("context.north_star needs value and src", err)
        self.assertEqual(run(data(item("a"), context={**CTX, "stage": {"value": "beta", "src": "x"}}))[0], 2)
        self.assertEqual(run(data(item("a"), as_of="today"))[0], 2)

    def test_one_batched_owner_question_for_assumed_context(self):
        c = {**CTX, "stage": {"value": "mvp", "src": "assumed: no doc"}, "north_star": {"value": "n", "src": "assumed: x"}}
        out = run(data(item("a"), context=c))[1]
        self.assertEqual(out.count("Owner question (one batch)"), 1)
        self.assertIn("confirm or correct the assumed stage, north star.", out)
        self.assertNotIn("Owner question", run(data(item("a")))[1])

    def test_evidence_must_resolve(self):
        rc, _, err = run(data(item("a", evidence=["docs/does-not-exist.md#x"])))
        self.assertEqual(rc, 2)
        self.assertIn("evidence not found: docs/does-not-exist.md#x", err)
        self.assertEqual(run(data(item("a", evidence=["README.md#top", "https://example.com/x", "issue:#1531", "survey:2026-10-16#P1", "owner:2026-10-16"])))[0], 0)
        self.assertIn("evidence not found: /etc/hosts", run(data(item("a", evidence=["/etc/hosts"])))[2])  # outside the repo root
        self.assertIn("evidence not found: guess:1", run(data(item("a", evidence=["guess:1"])))[2])  # a tag that is not allowed

    def test_every_violation_is_listed_at_once(self):
        _, _, err = run(data(item("a", reach=6, impact=5, effort=0, metric="better",
                                  lever="nope", vision="maybe", where="", role="CXO")))
        for needle in ("reach is missing", "impact is missing", "effort is missing",
                       "metric must be measurable", "lever must be one of", "vision must be", "where is required", "role must be"):
            self.assertIn(needle, err)

    def test_every_input_needs_a_source_field(self):
        i = item("a")
        del i["effort_src"]
        self.assertIn("effort_src is required", run(data(i))[2])

    def test_duplicate_ids_fail_and_near_duplicate_titles_are_flagged(self):
        self.assertIn("duplicate id", run(data(item("a"), item("a")))[2])
        out = run(data(item("a", title="Per-test flake ledger"), item("b", title="Per-test flake ledgers")))[1]
        self.assertIn("a ~ b", out)
        self.assertIn("near-duplicate titles (similarity 0.85 or more): none.", run(data(item("a"), item("b")))[1])

    def test_csv_input_matches_json(self):
        a, b = item("a"), item("b", lever="learning", effort=1)
        with tempfile.TemporaryDirectory() as t:
            t = Path(t)
            rows = [dict(i, evidence="README.md; CHANGELOG.md") for i in (a, b)]
            with (t / "i.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
                w.writeheader()
                w.writerows(rows)
            (t / "c.json").write_text(json.dumps({k: v for k, v in data().items() if k != "items"}))
            got = rr.load(str(t / "i.csv"), str(t / "c.json"))
            self.assertEqual(rr.build(got, ROOT)[1], [])
            self.assertEqual(ids(ranked(got)), ["b", "a"])
            with self.assertRaises(ValueError):
                rr.load(str(t / "i.csv"))


class Output(unittest.TestCase):
    def test_sections_come_in_the_fixed_order(self):
        adr = {"id": "ADR-1", "item": "a", "area": "tooling", "title": "t", "context": "c", "decision": "We will x.",
               "options": [{"name": "A", "tradeoffs": "t"}, {"name": "do nothing", "tradeoffs": "t"}],
               "consequences": "c", "reversal_cost": "low"}
        out = run(data(item("a"), item("m", vision="misaligned", vision_reason="r"), adrs=[adr]))[1]
        heads = [out.index(h) for h in ("## 1. Strategy context", "## 2. Rejected items", "## 3. Ranked roadmap",
                                        "## 4. Technical-direction decisions (ADRs)", "## 5. Tracker-ready issues")]
        self.assertEqual(heads, sorted(heads))
        self.assertIn("### ADR-1: t (tooling), serves `a`", out)
        self.assertIn("### P1: A a-a-a", out)

    def test_adr_rules(self):
        ok = {"id": "ADR-1", "item": "a", "area": "tooling", "title": "t", "context": "c", "decision": "We will x.",
              "options": [{"name": "A", "tradeoffs": "t"}, {"name": "B", "tradeoffs": "t"}], "consequences": "c",
              "reversal_cost": "low"}
        base = (item("a"), item("m", vision="misaligned", vision_reason="r"))
        self.assertEqual(run(data(*base, adrs=[ok]))[0], 0)
        for patch, needle in (({"item": "m"}, "item must name a ranked or in-flight item"), ({"area": "ui"}, "area must be"),
                              ({"decision": "Maybe x."}, "We will"), ({"options": [ok["options"][0]]}, "at least 2 entries"),
                              ({"reversal_cost": ""}, "reversal_cost is required")):
            self.assertIn(needle, run(data(*base, adrs=[{**ok, **patch}]))[2])

    def test_bluf_names_top_items_and_the_first_ungated_open_item(self):
        out = run(data(item("a", gate="owner: external send", reach=5), item("b", effort=3)))[1]
        self.assertTrue(out.startswith("**BLUF.** Stage `mvp`. 2 items ranked (2 open, 0 in flight), 0 rejected. Top: `b` 1.67, `a` 1.56."))
        self.assertIn("Start now (highest-ranked open item with no gate): `b`.", out)
        self.assertIn("Every reach input is assumed, so read the order as a hypothesis.", out)
        self.assertIn("Every open item is gated.", run(data(item("a", gate="g")))[1])

    def test_evidence_paths_become_links_relative_to_the_target_file(self):
        d = data(item("a", evidence=["README.md#top", "https://example.com/x", "issue:#1"]))
        self.assertIn("[README.md#top](../README.md#top); https://example.com/x; issue:#1", rr.render(d, ranked(d), "../"))

    def test_priorities_are_rank_derived_and_only_p1_p2_get_issues(self):
        out = run(data(*[item(c, effort=e) for c, e in zip("abcdefg", range(1, 8))]))[1]
        self.assertEqual([out.count(f"### {p}:") for p in ("P1", "P2", "P3")], [3, 3, 0])
        self.assertIn("P3, no issue drafted until promoted: `g`.", out)

    def test_update_replaces_only_the_marked_block(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "doc.md"
            f.write_text(f"before\n{rr.BEGIN}\nSTALE-SENTINEL\n{rr.END}\nafter\n")
            p = Path(t) / "in.json"
            p.write_text(json.dumps(data(item("a"))))
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(rr.main([str(p), "--root", str(ROOT), "--update", str(f)]), 0)
            s = f.read_text()
            self.assertTrue(s.startswith("before\n") and s.endswith(f"{rr.END}\nafter\n") and "STALE-SENTINEL" not in s)
            f.write_text("no markers\n")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(rr.main([str(p), "--root", str(ROOT), "--update", str(f)]), 2)
                self.assertEqual(rr.main([str(p), "--root", str(ROOT), "--update", str(Path(t) / "nope.md")]), 2)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "in.json"
            p.write_text(json.dumps(data(item("a"))))
            cmd = [sys.executable, str(SCRIPT), str(p), "--root", str(ROOT)]
            ok = subprocess.run(cmd, capture_output=True, text=True)
            strict = subprocess.run(cmd + ["--strict"], capture_output=True, text=True)
            gone = subprocess.run([sys.executable, str(SCRIPT), str(Path(t) / "missing.json")], capture_output=True, text=True)
        self.assertEqual((ok.returncode, strict.returncode, gone.returncode), (0, 1, 2))
        self.assertTrue(ok.stdout.startswith("**BLUF.**") and "\n## 1. Strategy context\n" in ok.stdout)


class PerunRoadmap(unittest.TestCase):
    """The committed docs/roadmap.md block is exactly what the input produces, and its critic verdicts are valid."""
    inp = ROOT / "docs/roadmap-input.json"

    def test_roadmap_block_is_current(self):
        d = json.loads(self.inp.read_text())
        body = rr.render(d, ranked(d), "../")
        s = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
        block = s.split(rr.BEGIN)[1].split(rr.END)[0]
        self.assertEqual(block.strip("\n"), body, "docs/roadmap.md is stale: run roadmap_rank.py docs/roadmap-input.json --update docs/roadmap.md")

    def test_top3_open_items_have_valid_idea_critic_verdicts_and_strict_passes(self):
        d = json.loads(self.inp.read_text())
        top = [x["it"] for x in ranked(d)["opens"][:3]]
        self.assertEqual(run(d, "--strict")[0], 0)
        validator = ROOT / ".claude/skills/idea-critic/scripts/validate_verdict.py"
        for it in top:
            with tempfile.TemporaryDirectory() as t:
                v = Path(t) / "v.json"
                v.write_text(json.dumps(it["critic"]))
                p = subprocess.run([sys.executable, str(validator), "--file", str(v)], capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, f"{it['id']}: {p.stderr}")

    def test_owner_listed_in_flight_work_is_scored_and_flagged(self):
        d = json.loads(self.inp.read_text())
        fl = [i for i in d["items"] if i.get("status") == "in_flight"]
        r = ranked(d)
        self.assertEqual({i["id"] for i in fl}, {x["it"]["id"] for x in r["ranked"] if x["flight"]})
        text = " ".join(i["id"] + " " + i["title"] for i in fl).lower()
        for needle in ("pr_state", "gate cache", "sandbox preflight", "host", "low-context", "review lenses", "url switch"):
            self.assertIn(needle, text)

    def test_field_proven_items_are_present_with_real_sources(self):
        d = json.loads(self.inp.read_text())
        r = {x["it"]["id"]: x for x in ranked(d)["ranked"]}
        for i in ("gate-cache-tree-sha", "autonomy-advisor", "zero-chat-lanes"):
            self.assertIn(i, r)
        for i in ("gate-cache-tree-sha", "autonomy-advisor"):  # reach and impact cite the committed field page
            self.assertEqual((r[i]["conf"], r[i]["asm"]), (1.0, ["effort"]))
        self.assertTrue((ROOT / "docs/peer-survey-2026-10-16.md").exists())

    def test_survey_items_are_all_accounted_for(self):
        d = json.loads(self.inp.read_text())
        cited = " ".join(" ".join(i.get("evidence", [])) for i in d["items"])
        for n in range(1, 11):
            self.assertIn(f"survey:2026-10-16#P{n}", cited, f"survey row P{n} is not on the roadmap")


if __name__ == "__main__":
    unittest.main()
