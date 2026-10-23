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


def U(p, c, s=0.0):
    return {"prompt_tokens": p, "completion_tokens": c, "spend_usd": s}


class FakeResp:
    def __init__(self, body):
        self.body = body

    def read(self, *a):
        return json.dumps(self.body).encode()


def chat_usage(body):
    u = {}
    with mock.patch.object(r.urllib.request, "urlopen", return_value=FakeResp(body)), mock.patch.object(r, "load_key", return_value="k"):
        assert r.chat("m", "s", "u", usage=u) == "hi"
    return u


class Capture(unittest.TestCase):
    def test_chat_records_reported_usage(self):
        body = {"choices": [{"message": {"content": "hi"}}], "usage": {"prompt_tokens": 12, "completion_tokens": 5}}
        self.assertEqual(chat_usage(body), U(12, 5, None))  # no price reported: unmeasured, never 0.0
        body["usage"]["cost"] = 0.004
        self.assertEqual(chat_usage(body), U(12, 5, 0.004))

    def test_chat_without_usage_records_nothing(self):
        self.assertEqual(chat_usage({"choices": [{"message": {"content": "hi"}}]}), {})

    def test_claude_call_records_usage_and_cost(self):
        lines = [json.dumps({"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {"w": {"utilization": 0.1}}}}),
                 json.dumps({"type": "result", "result": "ok", "total_cost_usd": 0.02,
                             "usage": {"input_tokens": 10, "cache_creation_input_tokens": 100, "cache_read_input_tokens": 5, "output_tokens": 7}})]
        u = {}
        with mock.patch.object(r.subprocess, "run", return_value=mock.Mock(stdout="\n".join(lines))):
            self.assertEqual(r.claude_call("s", "u", r.State(1.0), usage=u), "ok")
        self.assertEqual(u, U(115, 7, 0.02))

    def test_arm_cost_sums_only_measured(self):
        c = r.arm_cost([U(10, 2, 0.5), U(20, 4, 0.25)], 3)
        self.assertEqual((c["n_measured"], c["n_items"], c["prompt_tokens"], c["completion_tokens"], c["spend_usd"]), (2, 3, 30, 6, 0.75))


def res(p, q, n=2):
    return {"cost_per_arm": {"PERUN": r.arm_cost(p, n), "RIVAL": r.arm_cost(q, n)}}


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
        rep = b.cost_report({"cost_per_arm": {"PERUN": r.arm_cost([U(1, 1)] * 2, 3), "RIVAL": r.arm_cost([U(2, 2)] * 3, 3)}})
        self.assertIsNone(rep["ok"])

    def test_zero_cost_rival_fails_closed(self):
        rep = b.cost_report(res([U(1, 1)] * 2, [U(0, 0)] * 2))
        self.assertEqual((rep["ratio"], rep["ok"]), (None, False))

    def test_mixed_units_unmeasured(self):
        rep = b.cost_report(res([U(1, 1, 0.1)] * 2, [U(9, 9)] * 2))
        self.assertIsNone(rep["ok"])
        self.assertIn("units differ", rep["reason"])

    def test_missing_price_makes_usd_none(self):
        self.assertIsNone(r.arm_cost([U(1, 1, 0.1), U(1, 1, None)], 2)["spend_usd"])

    def test_old_results_json_cli_exit_1(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "results.json"
            f.write_text(json.dumps({"spend_usd": 0.0, "n": 150}))
            self.assertEqual(b.main(["--cost", str(f)]), 1)

    def test_cli_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "results.json"
            f.write_text(json.dumps(res([U(5, 5)] * 2, [U(9, 9)] * 2)))
            self.assertEqual(b.main(["--cost", str(f)]), 0)
            f.write_text(json.dumps(res([U(9, 9)] * 2, [U(5, 5)] * 2)))
            self.assertEqual(b.main(["--cost", str(f)]), 1)


if __name__ == "__main__":
    unittest.main()
