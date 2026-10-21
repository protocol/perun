#!/usr/bin/env python3
"""Tests for the hidden-test bench r2 additions: ablation arms (perun-no-<block>), perun-core and the per-call API seed. Offline."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hidden_test_bench as H  # noqa: E402


class Ablation(unittest.TestCase):
    def test_skip_drops_only_the_named_blocks(self):
        full = H.perun_text()
        self.assertNotIn("## Gates (G0", H.perun_text(("delivery",)))
        self.assertIn("## Operating principles (non-negotiable)", H.perun_text(("delivery",)))
        self.assertNotIn("# Testing & evaluation review", H.perun_text(("testing",)))
        self.assertLess(len(H.perun_text(("delivery", "testing"))), len(full))

    def test_perun_core_is_principles_plus_definition_of_done(self):
        sys_, _ = H.arm_systems("unused", ("perun-core", "perun-no-delivery+testing"))
        self.assertEqual(sys_["perun-core"], sys_["perun-no-delivery+testing"])
        core = sys_["perun-core"]
        self.assertIn("## Operating principles (non-negotiable)", core)
        self.assertIn("## Definition of done", core)
        self.assertNotIn("## Gates (G0", core)
        self.assertNotIn("# Testing & evaluation review", core)

    def test_report_pairs_ablation_arms_against_perun(self):
        recs = [{"arm": a, "id": "t", "sample": 0, "pass": a != "perun", "why": "pass", "completion_tokens": 1, "prompt_tokens": 1, "finish": "stop"}
                for a in ("none", "perun", "perun-core")]
        res = H.report(recs, ["t"], ("none", "perun", "perun-core"))
        self.assertIn(("perun-core", "perun"), [(p["a"], p["b"]) for p in res["paired"]])


class Seed(unittest.TestCase):
    def test_seed_is_sent_only_when_set(self):
        sent = []

        class R:
            def read(self):
                return json.dumps({"choices": [{"message": {"content": "x"}, "finish_reason": "stop"}], "usage": {}}).encode()

        def fake(req, timeout=0):
            sent.append(json.loads(req.data))
            return R()

        real_open, real_key = H.urllib.request.urlopen, H.load_key
        H.urllib.request.urlopen, H.load_key = fake, lambda: "k"
        try:
            H.chat("m", "s", "u")
            H.chat("m", "s", "u", seed=7)
        finally:
            H.urllib.request.urlopen, H.load_key = real_open, real_key
        self.assertNotIn("seed", sent[0])
        self.assertEqual(sent[1]["seed"], 7)


if __name__ == "__main__":
    unittest.main()
