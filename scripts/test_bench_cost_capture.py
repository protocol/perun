#!/usr/bin/env python3
"""Offline tests for per-arm cost capture (rival_eval usage parsing, arm_cost) and bench_verdict.cost_report. No network."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bench_verdict as b  # noqa: E402
import rival_eval as r  # noqa: E402
import rival_eval_cost as rc  # noqa: E402
import test_rival_eval as T  # noqa: E402


def U(p, c, s=0.0):
    return {"prompt_tokens": p, "completion_tokens": c, "spend_usd": s}


class FakeResp:
    def __init__(self, body):
        self.body = body

    def read(self, *a):
        return json.dumps(self.body).encode()


class Wrapped(unittest.TestCase):
    """rival_eval itself is untouched; install() wraps it. Restore its attributes after each test."""

    def setUp(self):
        self.saved = {k: getattr(r, k) for k in ("generate", "save", "run_skill", "urllib", "subprocess")}
        self.saved["flag"] = getattr(r, "_cost_installed", False)
        rc.install()

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(r, "_cost_installed" if k == "flag" else k, v)

    def sidecar(self, body):
        """generate() through the real chat() with a faked HTTP response, then save() -> the usage sidecar content."""
        with tempfile.TemporaryDirectory() as d, mock.patch.object(rc.urllib.request, "urlopen", return_value=FakeResp(body)), \
                mock.patch.object(r, "load_key", return_value="k"):
            p = Path(d) / "o" / "x.txt"
            r.save(p, r.generate("pcss", "s", "u", None))
            s = p.with_suffix(".usage.json")
            return json.loads(s.read_text()) if s.exists() else None

    def test_chat_records_reported_usage(self):
        body = {"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 12, "completion_tokens": 5}}
        self.assertEqual(self.sidecar(body), U(12, 5, None))  # no price reported: unmeasured, never 0.0
        body["usage"]["cost"] = 0.004
        self.assertEqual(self.sidecar(body), U(12, 5, 0.004))

    def test_chat_without_usage_writes_no_sidecar(self):
        self.assertIsNone(self.sidecar({"choices": [{"message": {"content": "hi"}}]}))

    def test_save_without_generate_writes_no_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.txt"
            r.save(p, "t")
            self.assertFalse(p.with_suffix(".usage.json").exists())

    def test_claude_call_records_usage_and_cost(self):
        lines = [json.dumps({"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {"w": {"utilization": 0.1}}}}),
                 json.dumps({"type": "result", "result": "ok", "total_cost_usd": 0.02,
                             "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 5, "output_tokens": 7}})]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(rc.subprocess, "run", return_value=mock.Mock(stdout="\n".join(lines))):
            p = Path(d) / "x.txt"
            r.save(p, r.generate("claude", "s", "u", r.State(1.0)))
            self.assertEqual(json.loads(p.with_suffix(".usage.json").read_text()), U(115, 7, 0.02))

    def test_run_skill_adds_cost_per_arm_and_resume_keeps_it(self):
        tmp = Path(tempfile.mkdtemp())
        name = T.fake_fixture(tmp, T.scen("held", 10, 10), T.scen("tune", 5))

        def urlopen(req, timeout=0):
            m = json.loads(req.data)
            sysm, user = m["messages"][0]["content"], m["messages"][1]["content"]
            if T.is_judge(sysm):
                v = "1" if user.index("PERUN-ANSWER") < user.index("RIVAL-ANSWER") else "2"
                return FakeResp({"choices": [{"message": {"content": T.judge_reply(user, v)}}]})
            n = 3 if "PERUN skill text" in sysm else 6
            return FakeResp({"choices": [{"message": {"content": ("PERUN-ANSWER" if n == 3 else "RIVAL-ANSWER") + user[-20:]}}],
                             "usage": {"prompt_tokens": n, "completion_tokens": n}})
        with mock.patch.object(r, "ROOT", tmp), mock.patch.object(r, "FIX", tmp / "scripts/eval-fixtures/rival"), \
                mock.patch.object(rc.urllib.request, "urlopen", urlopen), mock.patch.object(r, "load_key", return_value="k"):
            res = r.run_skill(name, "heldout", "pcss", tmp / "out", 2, 0.5)
            again = r.run_skill(name, "heldout", "pcss", tmp / "out", 2, 0.5)  # all outputs cached: usage comes from the sidecars
        for x in (res, again):
            self.assertEqual(x["cost_per_arm"]["PERUN"], dict(n_measured=10, n_items=10, prompt_tokens=30, completion_tokens=30, spend_usd=None))
            self.assertEqual(x["cost_per_arm"]["RIVAL"]["prompt_tokens"], 60)
        saved = json.loads(next((tmp / "out" / name).glob("heldout-*/results.json")).read_text())
        self.assertEqual(saved["cost_per_arm"], res["cost_per_arm"])


class Capture(unittest.TestCase):
    def test_claude_usage_without_result_is_empty(self):
        self.assertEqual(rc.claude_usage('{"type": "assistant"}\nnot json'), {})

    def test_arm_cost_sums_only_measured(self):
        c = rc.arm_cost([U(10, 2, 0.5), U(20, 4, 0.25)], 3)
        self.assertEqual((c["n_measured"], c["n_items"], c["prompt_tokens"], c["completion_tokens"], c["spend_usd"]), (2, 3, 30, 6, 0.75))


def res(p, q, n=2):
    return {"cost_per_arm": {"PERUN": rc.arm_cost(p, n), "RIVAL": rc.arm_cost(q, n)}}


class Report(unittest.TestCase):
    def test_tokens_when_free_endpoint(self):
        rep = b.cost_report(res([U(10, 10)] * 2, [U(20, 20)] * 2))
        self.assertEqual((rep["unit"], rep["ratio"], rep["ok"]), ("tokens", 0.5, True))

    def test_usd_when_paid(self):
        rep = b.cost_report(res([U(1, 1, 0.3)] * 2, [U(1, 1, 0.1)] * 2))
        self.assertEqual((rep["unit"], rep["ok"]), ("usd", False))

    def test_partial_or_missing_is_unmeasured(self):
        self.assertIsNone(b.cost_report(res([U(1, 1)], [U(1, 1)] * 2))["ok"])
        self.assertIsNone(b.cost_report({"spend_usd": 0.0})["ok"])

    def test_ratio_value_and_direction(self):
        rep = b.cost_report(res([U(10, 10), U(20, 20)], [U(30, 30), U(50, 50)]))  # perun 30/item, rival 80/item
        self.assertEqual((rep["per_item"], rep["ratio"], rep["ok"]), ({"PERUN": 30.0, "RIVAL": 80.0}, 0.375, True))
        rep = b.cost_report(res([U(30, 30), U(50, 50)], [U(10, 10), U(20, 20)]))
        self.assertEqual((rep["ratio"], rep["ok"]), (80 / 30, False))

    def test_failed_item_is_unmeasured(self):  # 3 scenarios, one Perun generation failed: 2 measured of 3 items
        rep = b.cost_report({"cost_per_arm": {"PERUN": rc.arm_cost([U(1, 1)] * 2, 3), "RIVAL": rc.arm_cost([U(2, 2)] * 3, 3)}})
        self.assertIsNone(rep["ok"])

    def test_zero_cost_rival_fails_closed(self):
        rep = b.cost_report(res([U(1, 1)] * 2, [U(0, 0)] * 2))
        self.assertEqual((rep["ratio"], rep["ok"]), (None, False))

    def test_mixed_units_unmeasured(self):
        rep = b.cost_report(res([U(1, 1, 0.1)] * 2, [U(9, 9)] * 2))
        self.assertIsNone(rep["ok"])
        self.assertIn("units differ", rep["reason"])

    def test_missing_price_makes_usd_none(self):
        self.assertIsNone(rc.arm_cost([U(1, 1, 0.1), U(1, 1, None)], 2)["spend_usd"])

    def test_old_results_json_cli_exit_3(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "results.json"
            f.write_text(json.dumps({"spend_usd": 0.0, "n": 150}))
            self.assertEqual(b.main(["--cost", str(f)]), 3)  # unmeasured is not a loss

    def test_cli_usage_error_without_file(self):
        self.assertEqual(b.main(["--cost"]), 2)

    def test_cli_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "results.json"
            f.write_text(json.dumps(res([U(5, 5)] * 2, [U(9, 9)] * 2)))
            self.assertEqual(b.main(["--cost", str(f)]), 0)
            f.write_text(json.dumps(res([U(9, 9)] * 2, [U(5, 5)] * 2)))
            self.assertEqual(b.main(["--cost", str(f)]), 1)


if __name__ == "__main__":
    unittest.main()
