#!/usr/bin/env python3
"""Tests for the answer-key scorer in scripts/rival_eval_keys.py (key_score, violated, check_keys, draft_text, `keys` CLI). Offline; no model is called."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rival_eval as r  # noqa: E402
import rival_eval_keys as k  # noqa: E402
import test_rival_eval as T  # noqa: E402
from unittest import mock  # noqa: E402

k.install()

ROWS = ("business-ops", "growth-analytics", "idea-critic", "contribution")


def score(skill, i, text):
    return k.key_score(skill, {"A": {i: text}})["A"]["per_scenario"][i]


class Keys(unittest.TestCase):
    def test_every_heldout_scenario_keyed_and_clean(self):
        for s in ROWS:
            self.assertEqual(k.check_keys(s), [], s)
            self.assertEqual(set(k.load_keys(s)), {x["id"] for x in r.load_scenarios(s, "heldout")}, s)

    def test_check_split_includes_keys(self):
        for s in ROWS:
            self.assertEqual(r.check_split(s), [], s)

    def test_echo_baseline_scenario_text_alone_scores_under_half(self):
        """A key that the prompt itself satisfies measures reading, not answering."""
        worst = 0.0
        for s in ROWS:
            scs = r.load_scenarios(s, "heldout")
            per = k.key_score(s, {"E": {x["id"]: x["prompt"] for x in scs}})["E"]["per_scenario"]
            for i, p in per.items():
                self.assertLess(p["hits"] / p["of"], 0.5, f"{s} {i} hit by its own prompt: {set(k.load_keys(s)[i]['must']) - set(p['missed'])}")
                worst = max(worst, p["hits"] / p["of"])
        print(f"echo-baseline max hit-rate {worst:.2f}")

    def test_no_perun_verdict_tokens_in_idea_critic_keys(self):
        blob = json.dumps(k.load_keys("idea-critic"))
        for tok in ("HOLD", "REVISE", "PASS_TO_USER"):
            self.assertNotIn(tok, blob)

    def test_check_keys_flags_size_and_regex(self):
        orig = k.load_keys
        k.load_keys = lambda s: {"07": {"must": {"a": "("}, "mustnot": {}}}
        try:
            bad = k.check_keys("business-ops")
        finally:
            k.load_keys = orig
        self.assertTrue(any("needs 3-6 must" in b for b in bad))
        self.assertTrue(any("bad regex" in b for b in bad))
        self.assertTrue(any("no key for heldout 08" in b for b in bad))

    def test_scores_hits_and_violations(self):
        good = ("Margin is $37 per unit against $72 direct, so you need about 1.95x the volume. Funding 5,000 units ties up $540,000 "
                "of cash, so counter on price.")
        o = k.key_score("business-ops", {"PERUN": {"07": good}, "RIVAL": {"07": "Accept: guaranteed profit, no downside."}})
        p, q = o["PERUN"]["per_scenario"]["07"], o["RIVAL"]["per_scenario"]["07"]
        self.assertEqual((p["hits"], p["of"], p["violated"]), (p["of"], p["of"], []))
        self.assertEqual((q["hits"], q["violated"]), (0, ["no_risk"]))

    def test_missing_output_is_a_miss_for_that_arm_only(self):
        n = len(k.load_keys("business-ops"))
        o = k.key_score("business-ops", {"PERUN": {"07": "x", "08": "x"}, "RIVAL": {"07": "x"}})
        self.assertEqual((o["PERUN"]["n"], o["RIVAL"]["n"]), (n, n))
        self.assertTrue(o["RIVAL"]["per_scenario"]["08"]["missing"])
        self.assertEqual(o["RIVAL"]["per_scenario"]["08"]["hits"], 0)
        self.assertNotIn("missing", o["PERUN"]["per_scenario"]["08"])

    def test_missing_keys_json_fails_closed_for_shipped_skills(self):
        with mock.patch.object(r, "FIX", Path(tempfile.mkdtemp())):
            for s in ROWS:
                with self.assertRaises(SystemExit):
                    k.load_keys(s)
                self.assertTrue(any("fail closed" in b for b in k.check_keys(s)), s)
            self.assertEqual(k.load_keys("agentic-ceo"), {})

    def test_check_keys_rejects_malformed_entries(self):
        for bad in ({"07": {"mustnot": {}}}, {"07": {"must": ["a", "b", "c"]}}, {"07": "x"}, {"07": {"must": {"a": "x"}, "mustnot": ["y"]}}):
            with mock.patch.object(k, "load_keys", lambda s, bad=bad: bad):
                self.assertTrue(any("malformed" in b for b in k.check_keys("business-ops")), bad)

    def test_negation_scope_is_local_and_brackets_do_not_hide(self):
        self.assertEqual(score("business-ops", "07", "No, you should definitely accept the guaranteed profit now.")["violated"], ["no_risk"])
        self.assertEqual(score("contribution", "07", "```\nHi Jane, we at [Acme Logistics] hit it.\n```")["violated"], ["leaks_company"])
        self.assertEqual(score("contribution", "07", "```\nHi Jane, we at [Company] hit it.\n```")["violated"], [])

    def test_negation_is_not_a_violation(self):
        self.assertEqual(score("business-ops", "07", "Do not expect guaranteed profit here.")["violated"], [])
        self.assertEqual(score("business-ops", "07", "Expect guaranteed profit here.")["violated"], ["no_risk"])
        self.assertEqual(score("idea-critic", "h01", "I cannot recommend either path.")["violated"], ["no_rec"])
        self.assertEqual(score("contribution", "07", "```\nHi Jane, we at Acme Logistics hit it.\n```")["violated"], ["leaks_company"])
        self.assertEqual(score("contribution", "07", "```\nHi Jane. We never name Acme Logistics.\n[Company] and <redacted> redacted\n```")["violated"], [])

    def test_paraphrase_forms_hit(self):
        for t in ("needs $540,000", "needs 540000", "needs $540k", "needs 540K of cash"):
            self.assertIn("inventory_cash_540k", set(k.load_keys("business-ops")["07"]["must"]) - set(score("business-ops", "07", t)["missed"]), t)
        for t in ("payroll of $100,000", "payroll of 100k", "two hires cost 100,000"):
            self.assertEqual(score("business-ops", "08", t)["missed"].count("payroll_100k"), 0, t)
        for t in ("breakeven churn is 13%", "breakeven churn is 13 percent", "about 13.04%"):
            self.assertEqual(score("idea-critic", "h02", t)["missed"].count("breakeven_churn"), 0, t)
        self.assertEqual(score("business-ops", "07", "costs $5,400,000")["missed"].count("inventory_cash_540k"), 1)  # no substring match

    def test_plain_words_answer_equals_perun_vocabulary_answer(self):
        perun = ("Recommendation: PASS_TO_USER with REVISE. Kill criteria: stop if churn tops 13%. Pilot a segment first, grandfather "
                 "existing accounts, phase the rise by tier.")
        plain = ("I'd go with a phased rise. Walk away if churn passes 13 percent. Try it on a sample of accounts first, "
                 "keep current customers on their old price, and move up by tier.")
        a, b = score("idea-critic", "h02", perun), score("idea-critic", "h02", plain)
        self.assertEqual((a["hits"], a["missed"]), (b["hits"], b["missed"]))
        self.assertEqual(a["hits"], a["of"])

    def test_draft_scope_and_no_draft(self):
        self.assertEqual(k.draft_text("a\n```\nb\n```\n> c\nd"), "b\n> c")
        self.assertTrue(score("contribution", "07", "Advice only, nothing to paste.")["no_draft"])
        self.assertTrue(score("contribution", "07", "> Hi Jane, thanks.")["no_draft"])  # one-liner is not a draft
        self.assertTrue(score("contribution", "07", "```\n```")["no_draft"])
        self.assertFalse(score("contribution", "07", "> " + "Hi Jane, thanks for maintaining this project, here is my patch for review. " * 2)["no_draft"])
        self.assertFalse(score("business-ops", "07", "no draft needed")["no_draft"])
        self.assertEqual(score("contribution", "07", "Never name Acme Logistics.\n> Hi Jane, thanks.")["violated"], [])
        o = k.key_score("contribution", {"A": {"07": "no draft here"}})["A"]
        self.assertEqual(o["per_scenario"]["07"]["no_draft"], True)
        self.assertEqual(o["violation_rate"], round(1 / o["n"], 3))

    def test_force_push_in_draft_any_flag_position(self):
        def f(t):
            return score("contribution", "14", t)["violated"]
        self.assertEqual(f("```\ngit push --force-with-lease origin x\n```"), [])
        self.assertEqual(f("```\ngit push --force origin x\n```"), ["bare_force_push"])
        self.assertEqual(f("```\ngit push origin x --force\n```"), ["bare_force_push"])
        self.assertEqual(f("```\ngit push origin x -f\n```"), ["bare_force_push"])
        self.assertEqual(f("```\n# never run git push --force\n```"), [])
        self.assertEqual(f("Never use git push --force on a shared branch."), [])

    def test_run_skill_adds_answer_key_block(self):
        tmp = Path(tempfile.mkdtemp())
        name = T.fake_fixture(tmp, T.scen("held", 10, 10), T.scen("tune", 5))
        with mock.patch.object(r, "ROOT", tmp), mock.patch.object(r, "FIX", tmp / "scripts/eval-fixtures/rival"):
            ids = [x["id"] for x in r.load_scenarios(name, "heldout")]
            key = {"must": {"a": "PERUN-ANSWER", "b": "ANSWER", "c": " for "}, "mustnot": {"x": "zzzz"}}
            (r.FIX / name / "keys.json").write_text(json.dumps({i: key for i in ids}))

            def chat(model, system, user, **kw):
                if T.is_judge(system):
                    return T.judge_reply(user, "1" if user.index("PERUN-ANSWER") < user.index("RIVAL-ANSWER") else "2")
                return ("PERUN-ANSWER" if "PERUN skill text" in system else "RIVAL-ANSWER") + " for " + user[-20:]
            with mock.patch.object(r, "chat", chat):
                res = r.run_skill(name, "heldout", "pcss", tmp / "out", 2, 0.5)
            self.assertEqual(r.check_split(name), [])
        a = res["answer_key"]
        self.assertEqual((a["PERUN"]["n"], a["PERUN"]["hit_rate"], a["RIVAL"]["hit_rate"], a["RIVAL"]["violation_rate"]), (10, 1.0, 0.667, 0.0))
        saved = json.loads(next((tmp / "out" / name).glob("heldout-*/results.json")).read_text())
        self.assertEqual(saved["answer_key"], a)

    def test_keys_cli_rescoring_cached_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            sc = next(x for x in r.load_scenarios("business-ops", "heldout") if x["id"] == "07")
            h = r.sha(sc["prompt"])[:8]
            for arm, txt in (("PERUN", "37 72 1.95x $540k counter"), ("RIVAL", "nothing")):
                p = Path(d) / "outputs" / arm
                p.mkdir(parents=True)
                (p / f"07-{h}.txt").write_text(txt)
                (p / "07-deadbeef.txt").write_text("stale")  # old prompt hash: must be ignored
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                k.main(["keys", "business-ops", d])
        out = json.loads(buf.getvalue())
        self.assertEqual((out["PERUN"]["per_scenario"] if "per_scenario" in out["PERUN"] else {}), {})
        n = len(k.load_keys("business-ops"))
        self.assertEqual((out["PERUN"]["hit_rate"], out["RIVAL"]["hit_rate"]), (round(1 / n, 3), 0.0))

    def test_keys_cli_fails_closed_without_keys_json(self):
        with tempfile.TemporaryDirectory() as d:
            for arm in r.ARMS:
                (Path(d) / "outputs" / arm).mkdir(parents=True)
            with self.assertRaises(SystemExit) as cm:
                k.main(["keys", "agentic-ceo", d])  # a skill with no keys.json
        self.assertIn("no keys.json", str(cm.exception))

    def test_keys_cli_fails_on_missing_arm_directory(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "outputs" / "PERUN"
            p.mkdir(parents=True)
            (p / "07-abcd1234.txt").write_text("x")
            with self.assertRaises(SystemExit) as cm:
                k.main(["keys", "business-ops", d])
        self.assertIn("missing arm directory", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
