#!/usr/bin/env python3
"""Tests for `token_report.py --advise`: one test per rule on a synthetic transcript, plus the "never recommend a
setting that is already set", fail-closed, UNPRICED and names-only guarantees.

Fixtures are generated in a temp dir from fictional models and tools; settings come from a temp project and a temp
CLAUDE_CONFIG_DIR, never the machine's real ones.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude/skills/agentic-ceo/scripts"))
import token_report as tr  # noqa: E402

OPUS, SONNET = "claude-opus-5", "claude-sonnet-5"
SETTING_ENV = ("ENABLE_TOOL_SEARCH", "CLAUDE_CODE_SUBAGENT_MODEL", "BASH_MAX_OUTPUT_LENGTH",
               "CLAUDE_CODE_AUTO_COMPACT_WINDOW", "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE")


def line(i, model=SONNET, ctx=1000, write=0, out=50, tools=(), iters=None, stop=None):
    """One assistant transcript line; `ctx` is cache-read tokens, `write` is 5m cache-write tokens."""
    usage = {"input_tokens": 10, "cache_read_input_tokens": ctx, "cache_creation_input_tokens": write,
             "cache_creation": {"ephemeral_5m_input_tokens": write, "ephemeral_1h_input_tokens": 0},
             "output_tokens": out}
    if iters:
        usage["iterations"] = iters
    return {"type": "assistant", "requestId": f"r{i}", "timestamp": f"2026-10-19T10:{i // 60:02d}:{i % 60:02d}Z",
            "message": {"model": model, "usage": usage, "stop_reason": stop,
                        "content": [{"type": "tool_use", "id": f"t{i}-{n}", "name": t, "input": {}}
                                    for n, t in enumerate(tools)] + [{"type": "text", "text": "SECRET-BODY"}]}}


def write_jsonl(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("".join(json.dumps(r) + "\n" for r in rows))


class Advise(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.project = self.dir / "proj"
        (self.project / ".claude").mkdir(parents=True)
        self.sess = self.dir / "s.jsonl"
        env = {k: v for k, v in os.environ.items() if k not in SETTING_ENV}
        env["CLAUDE_CONFIG_DIR"] = str(self.dir / "home")
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def settings(self, obj, name="settings.json"):
        (self.project / ".claude" / name).write_text(obj if isinstance(obj, str) else json.dumps(obj))

    def lane(self, n, rows):
        write_jsonl(self.dir / "s" / "subagents" / f"agent-{n}.jsonl", rows)

    def advise(self, main_rows):
        write_jsonl(self.sess, main_rows)
        report = tr.build_report(str(self.sess), None, 5, tr.DEFAULT_RATES)
        return tr.advise(report, None, tr.DEFAULT_RATES, str(self.project))

    def run_advise(self, main_rows):
        return {a["id"]: a for a in self.advise(main_rows)["advice"]}

    def ids(self, main_rows):
        return set(self.run_advise(main_rows))

    # -- one test per rule -------------------------------------------------
    def test_ctx_drops(self):
        sizes = [150_000, 160_000, 20_000, 150_000, 10_000]
        self.assertIn("ctx-drops", self.ids([line(i, ctx=c) for i, c in enumerate(sizes)]))
        self.assertNotIn("ctx-drops", self.ids([line(i, ctx=c) for i, c in enumerate([150_000, 160_000, 20_000])]))

    def test_ctx_window_fires_then_silent_when_set(self):
        rows = [line(i, ctx=c) for i, c in enumerate([100_000, 450_000])]
        self.assertIn("ctx-window", self.ids(rows))
        self.settings({"autoCompactWindow": 200000})
        self.assertNotIn("ctx-window", self.ids(rows))

    def test_ctx_window_silent_when_env_set(self):
        rows = [line(i, ctx=c) for i, c in enumerate([100_000, 450_000])]
        with mock.patch.dict(os.environ, {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "60"}):
            self.assertNotIn("ctx-window", self.ids(rows))

    def test_cache_switch(self):
        rows = [line(i, model=(OPUS, SONNET)[i % 2], ctx=100, write=5000) for i in range(12)]
        got = self.run_advise(rows)
        self.assertIn("cache-switch", got)
        self.assertNotIn("cache-churn", got)
        self.assertIsInstance(got["cache-switch"]["at_stake_usd"], float)

    def test_cache_churn_without_switch(self):
        got = self.run_advise([line(i, ctx=100, write=5000) for i in range(12)])
        self.assertIn("cache-churn", got)
        self.assertNotIn("cache-switch", got)

    def test_healthy_cache_is_silent(self):
        got = self.run_advise([line(i, ctx=50_000, write=100) for i in range(12)])
        self.assertFalse({"cache-churn", "cache-switch"} & set(got))

    def test_tool_output(self):
        self.assertIn("tool-output", self.ids([line(i, ctx=10_000 + i * 40_000) for i in range(5)]))
        self.assertNotIn("tool-output", self.ids([line(i, ctx=10_000 + i * 5_000) for i in range(5)]))

    def test_tool_output_never_recommends_a_set_cap(self):
        rows = [line(i, ctx=10_000 + i * 40_000) for i in range(5)]
        self.assertIn("bashOutputMaxChars", self.run_advise(rows)["tool-output"]["recommendation"])
        self.settings({"bashOutputMaxChars": 10000})
        self.assertNotIn("bashOutputMaxChars", self.run_advise(rows)["tool-output"]["recommendation"])
        self.settings({})
        with mock.patch.dict(os.environ, {"BASH_MAX_OUTPUT_LENGTH": "10000"}):
            self.assertNotIn("bashOutputMaxChars", self.run_advise(rows)["tool-output"]["recommendation"])

    def test_mcp_unused(self):
        (self.project / ".mcp.json").write_text(json.dumps({"mcpServers": {"acme-docs": {}, "acme-crm": {}, "acme-wiki": {}}}))
        got = self.run_advise([line(0, tools=["mcp__acme-docs__search"]), line(1)])
        self.assertIn("mcp-unused", got)
        idle = got["mcp-unused"]["evidence"].split(": ", 1)[1]
        self.assertIn("acme-crm", idle)
        self.assertNotIn("acme-docs", idle)

    def test_mcp_disabled_in_settings_is_not_recommended(self):
        (self.project / ".mcp.json").write_text(json.dumps({"mcpServers": {"acme-docs": {}, "acme-crm": {}, "acme-wiki": {}}}))
        self.settings({"disabledMcpjsonServers": ["acme-crm", "acme-wiki"]})
        self.assertNotIn("mcp-unused", self.ids([line(0, tools=["mcp__acme-docs__search"]), line(1)]))
        self.settings({"enabledMcpjsonServers": ["acme-docs"]})
        self.assertNotIn("mcp-unused", self.ids([line(0, tools=["mcp__acme-docs__search"]), line(1)]))

    def test_short_cache_session_is_silent(self):
        self.assertFalse({"cache-churn", "cache-switch"} & set(self.run_advise([line(i, ctx=100, write=5000) for i in range(9)])))
        self.assertIn("cache-churn", self.run_advise([line(i, ctx=100, write=5000) for i in range(10)]))

    def test_disabled_lists_merge_across_scopes(self):
        (self.project / ".mcp.json").write_text(json.dumps({"mcpServers": {"acme-docs": {}, "acme-crm": {}, "acme-wiki": {}, "acme-kb": {}}}))
        self.settings({"disabledMcpjsonServers": ["acme-crm"]})
        self.settings({"disabledMcpjsonServers": ["acme-wiki", 5, ["x"]]}, "settings.local.json")
        self.assertNotIn("mcp-unused", self.ids([line(0, tools=["mcp__acme-docs__search"]), line(1)]))

    def test_mcp_used_by_a_lane_counts_as_used(self):
        (self.project / ".mcp.json").write_text(json.dumps({"mcpServers": {"acme-docs": {}, "acme-crm": {}}}))
        self.lane(1, [line(0, tools=["mcp__acme-crm__lookup"])])
        self.assertNotIn("mcp-unused", self.ids([line(0, tools=["mcp__acme-docs__search"]), line(1)]))

    def test_mcp_unused_silent_on_unreadable_settings(self):
        (self.project / ".mcp.json").write_text("{not json")
        self.assertNotIn("mcp-unused", self.ids([line(0), line(1)]))

    def test_mcp_tool_search_off(self):
        (self.project / ".mcp.json").write_text(json.dumps({"mcpServers": {"acme-docs": {}}}))
        self.assertNotIn("mcp-no-toolsearch", self.ids([line(0)]))
        self.settings({"env": {"ENABLE_TOOL_SEARCH": "false"}})
        self.assertIn("mcp-no-toolsearch", self.ids([line(0)]))

    def test_tier_top_on_mechanical_lane(self):
        self.lane(1, [line(i, model=OPUS, out=20, tools=["Read"]) for i in range(10)])
        got = self.run_advise([line(0)])
        self.assertIn("tier", got)
        self.assertIsInstance(got["tier"]["at_stake_usd"], float)

    def test_tier_silent_for_cheap_or_wordy_lane(self):
        self.lane(1, [line(i, model=SONNET, out=20, tools=["Read"]) for i in range(10)])
        self.lane(2, [line(i, model=OPUS, out=4000, tools=["Read"]) for i in range(10)])
        self.assertNotIn("tier", self.ids([line(0)]))

    def test_tier_silent_when_subagent_model_set(self):
        self.lane(1, [line(i, model=OPUS, out=20, tools=["Read"]) for i in range(10)])
        self.settings({"env": {"CLAUDE_CODE_SUBAGENT_MODEL": "sonnet"}})
        self.assertNotIn("tier", self.ids([line(0)]))

    def test_main_tier_fires_on_top_tier_main_turns(self):
        got = self.run_advise([line(i, model=OPUS, ctx=2_000_000, out=2000) for i in range(30)])
        self.assertIn("main-tier", got)
        self.assertGreaterEqual(got["main-tier"]["at_stake_usd"], tr.ADV["main_top_usd"])

    def test_main_tier_silent_below_share(self):
        rows = [line(i, model=OPUS, ctx=2_000_000, out=2000) for i in range(30)]
        rows += [line(100 + i, model=SONNET, ctx=20_000_000, out=2000) for i in range(30)]
        self.assertNotIn("main-tier", self.ids(rows))

    def test_main_tier_silent_below_floor(self):
        self.assertNotIn("main-tier", self.ids([line(i, model=OPUS) for i in range(3)]))

    def test_main_tier_silent_when_only_lanes_are_top_tier(self):
        self.lane(1, [line(i, model=OPUS, ctx=2_000_000, out=2000) for i in range(30)])
        self.assertNotIn("main-tier", self.ids([line(i, model=SONNET) for i in range(3)]))

    def test_main_tier_silent_when_unpriced_or_model_set(self):
        self.assertNotIn("main-tier", self.ids([line(i, model="acme-opus-1", ctx=2_000_000, out=2000) for i in range(30)]))
        self.settings({"model": "sonnet"})
        self.assertNotIn("main-tier", self.ids([line(i, model=OPUS, ctx=2_000_000, out=2000) for i in range(30)]))

    def test_short_lanes(self):
        for n in range(5):
            self.lane(n, [line(0, tools=["Read"]), line(1, stop="end_turn")])
        self.assertIn("short-lanes", self.ids([line(0)]))

    def test_in_flight_short_lanes_silent(self):
        for n in range(5):
            self.lane(n, [line(0, tools=["Read"])])
        self.assertNotIn("short-lanes", self.ids([line(0)]))

    def test_few_short_lanes_silent(self):
        for n in range(4):
            self.lane(n, [line(0, tools=["Read"]), line(1, stop="end_turn")])
        self.assertNotIn("short-lanes", self.ids([line(0)]))

    def test_consults(self):
        iters = [{"type": "message"}, {"type": "advisor_message", "model": OPUS, "input_tokens": 9000,
                                         "output_tokens": 500, "cache_read_input_tokens": 0}]
        self.lane(1, [line(0, tools=["Read"], iters=iters), line(1, tools=["Read"])])
        got = self.run_advise([line(0)])
        self.assertIn("consults", got)
        self.assertGreater(got["consults"]["at_stake_usd"], 0)
        self.assertIn("1 lane consult", got["consults"]["evidence"])

    # -- cross-cutting guarantees ------------------------------------------
    def test_quiet_session_fires_nothing(self):
        self.assertEqual(self.ids([line(i, ctx=2000, write=10) for i in range(3)]), set())

    def test_unreadable_settings_assume_set(self):
        self.settings("{broken")
        out = self.advise([line(i, ctx=c) for i, c in enumerate([100_000, 450_000])])
        self.assertNotIn("ctx-window", {a["id"] for a in out["advice"]})
        self.assertTrue(out["notes"])

    def test_unknown_model_is_unpriced_never_zero(self):
        got = self.run_advise([line(i, model="acme-model-1", ctx=100, write=5000) for i in range(12)])["cache-churn"]
        self.assertIsNone(got["at_stake_usd"])
        self.assertIn("UNPRICED", tr.render_advice({"advice": [got], "notes": []}))

    def test_message_text_never_reaches_output(self):
        write_jsonl(self.sess, [line(i, ctx=10_000 + i * 40_000) for i in range(5)])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = tr.main(["--session", str(self.sess), "--advise", "--project", str(self.project)])
        self.assertEqual(rc, 0)
        self.assertIn("ADVICE", buf.getvalue())
        self.assertNotIn("SECRET-BODY", buf.getvalue())

    def test_json_has_advice_only_with_the_flag(self):
        write_jsonl(self.sess, [line(i, ctx=10_000 + i * 40_000) for i in range(5)])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            tr.main(["--session", str(self.sess), "--advise", "--json", "--project", str(self.project)])
        self.assertIn("tool-output", [a["id"] for a in json.loads(buf.getvalue())["advice"]["advice"]])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            tr.main(["--session", str(self.sess), "--json"])
        self.assertNotIn("advice", json.loads(buf.getvalue()))

    def test_every_rule_links_a_real_doc_and_tip(self):
        tips = (ROOT / "docs/token-cost-tips.md").read_text()
        for rid, _check, _rec, doc in tr.ADVICE_RULES:
            self.assertTrue(list(ROOT.glob("**/model-tiering.md")) if "model-tiering" in doc else True, rid)
            for n in __import__("re").findall(r"tips? (\d+)(?: and (\d+))?", doc):
                for num in filter(None, n):
                    self.assertIn(f"\n{num}. **", tips, f"{rid}: tip {num} missing")


if __name__ == "__main__":
    unittest.main()
