#!/usr/bin/env python3
"""Tests for docs/bench/review-cost-matched-1023 (matched.py). No network, no paid call: subprocess.run is patched to raise for the
whole module, so no test can start claude. The ledger and output dirs are always redirected to temp dirs."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "docs/bench/review-cost-matched-1023"
sys.path.insert(0, str(BENCH))
import matched  # noqa: E402

FAKE = {".claude-plugin/plugin.json": b"{}", "agents/code-reviewer.md": b"---\nname: code-reviewer\nmodel: opus\n---\n\nFake reviewer body.\n"}
FAKE_PINS = {rel: hashlib.sha256(b).hexdigest() for rel, b in FAKE.items()}
CID = matched.d.SPLIT["heldout"][0]
_guard = mock.patch.object(matched.confirm.subprocess, "run", side_effect=AssertionError("claude must never run in tests"))


def setUpModule():
    _guard.start()


def tearDownModule():
    _guard.stop()


def fake_plugin(root):
    """A stand-in for the fetched plugin: same layout, invented agent text. Pair with pin_fake() so its hashes are the pins."""
    for rel, b in FAKE.items():
        f = Path(root) / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b)
    return Path(root)


def pin_fake(case):
    p = mock.patch.object(matched, "TK_FILES", FAKE_PINS)
    p.start()
    case.addCleanup(p.stop)


class DryRun(unittest.TestCase):
    def setUp(self):
        pin_fake(self)

    def test_without_plugin_skips_tk_with_a_message_and_needs_no_network_or_claude(self):
        with mock.patch.object(matched.urllib.request, "urlopen", side_effect=AssertionError("network used")):
            n, notes = matched.dry_run()
        self.assertEqual(n, 22)
        self.assertEqual(len(notes), 1)
        self.assertIn("SKIP TK", notes[0])

    def test_with_plugin_checks_both_arms(self):
        with tempfile.TemporaryDirectory() as t:
            n, notes = matched.dry_run(fake_plugin(t))
        self.assertEqual((n, notes), (22, []))

    def test_plugin_dir_with_wrong_hash_or_missing_file_fails_the_dry_run(self):
        with tempfile.TemporaryDirectory() as t:
            p = fake_plugin(t)
            (p / "agents/code-reviewer.md").write_text("tampered")
            with self.assertRaises(SystemExit):
                matched.dry_run(p)
        with tempfile.TemporaryDirectory() as t:
            p = fake_plugin(t)
            (p / ".claude-plugin/plugin.json").unlink()
            with self.assertRaises(SystemExit):
                matched.dry_run(p)

    def test_perun_arm_ships_command_and_skill_tk_arm_ships_plugin_agent(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(matched.build(t, CID, "PERUN"), [".claude/commands/review.md", ".claude/skills/deep-code-review/SKILL.md"])
            self.assertTrue((Path(t) / "change.patch").is_file())
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as pl:
            self.assertEqual(matched.build(t, CID, "TK", fake_plugin(pl)), ["pr-review-toolkit/.claude-plugin/plugin.json", "pr-review-toolkit/agents/code-reviewer.md"])
            self.assertFalse((Path(t) / ".claude").exists())
            self.assertIn("model: inherit", (Path(t) / "pr-review-toolkit/agents/code-reviewer.md").read_text())

    def test_missing_arm_file_fails_the_dry_run(self):
        with mock.patch.object(matched, "REVIEW_CMD", ROOT / "commands/does-not-exist.md"):
            with self.assertRaises(FileNotFoundError):
                matched.dry_run()

    def test_changed_agent_body_fails_the_dry_run(self):
        orig = matched.build

        def build(w, cid, arm, plugin=None):
            r = orig(w, cid, arm, plugin)
            if arm == "TK":
                a = Path(w) / "pr-review-toolkit/agents/code-reviewer.md"
                a.write_text(a.read_text() + "tamper\n")
            return r
        with mock.patch.object(matched, "build", build), tempfile.TemporaryDirectory() as t:
            with self.assertRaises(AssertionError):
                matched.dry_run(fake_plugin(t))

    def test_this_bench_does_not_vendor_the_plugin(self):
        """Fails if a plugin copy (agent file, plugin manifest, agents/ or .claude-plugin/ dir) is added under the bench dir."""
        for p in BENCH.rglob("*"):
            self.assertNotIn(p.name, {"code-reviewer.md", "plugin.json", "agents", ".claude-plugin", "tk-plugin", "pr-review-toolkit"}, p)


class Fetch(unittest.TestCase):
    def test_fetch_writes_files_that_match_the_pinned_hashes(self):
        bodies = {matched.UPSTREAM + rel: b"body " + rel.encode() for rel in matched.TK_FILES}
        pins = {rel: hashlib.sha256(bodies[matched.UPSTREAM + rel]).hexdigest() for rel in matched.TK_FILES}
        resp = lambda url, timeout: mock.Mock(read=lambda: bodies[url])  # noqa: E731
        with mock.patch.object(matched, "TK_FILES", pins), mock.patch.object(matched.urllib.request, "urlopen", resp), tempfile.TemporaryDirectory() as t:
            out = matched.fetch_plugin(Path(t) / "p")
            self.assertEqual((out / "agents/code-reviewer.md").read_bytes(), b"body agents/code-reviewer.md")

    def test_fetch_rejects_a_hash_mismatch(self):
        with mock.patch.object(matched.urllib.request, "urlopen", lambda url, timeout: mock.Mock(read=lambda: b"changed")), tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit):
                matched.fetch_plugin(t)

    def test_fetch_leaves_no_files_when_a_later_file_mismatches(self):
        first, second = list(matched.TK_FILES)
        pins = {first: hashlib.sha256(b"ok").hexdigest(), second: "0" * 64}
        with mock.patch.object(matched, "TK_FILES", pins), mock.patch.object(matched.urllib.request, "urlopen", lambda url, timeout: mock.Mock(read=lambda: b"ok")), \
                tempfile.TemporaryDirectory() as t:
            with self.assertRaises(SystemExit):
                matched.fetch_plugin(t)
            self.assertEqual(list(Path(t).rglob("*")), [])

    def test_pin_is_a_full_commit_and_hashes_are_sha256(self):
        self.assertRegex(matched.UPSTREAM, r"/[0-9a-f]{40}/plugins/pr-review-toolkit/$")
        for h in matched.TK_FILES.values():
            self.assertRegex(h, r"^[0-9a-f]{64}$")


class Flags(unittest.TestCase):
    def test_both_arms_use_the_default_harness_and_exclude_dynamic_sections(self):
        for arm in matched.ARMS:
            f = matched.flags(arm)
            self.assertNotIn("--system-prompt", f)
            self.assertIn("--exclude-dynamic-system-prompt-sections", f)
            self.assertEqual(f[f.index("--max-budget-usd") + 1], str(matched.confirm.RESERVE))

    def test_both_arms_isolate_settings_and_mcp(self):
        for arm in matched.ARMS:
            f = matched.flags(arm)
            self.assertEqual(f[f.index("--setting-sources") + 1], "project,local")
            for flag in ("-p", "--strict-mcp-config", "--no-session-persistence"):
                self.assertIn(flag, f)

    def test_tool_lists_are_exact_and_allowed_tools_match(self):
        for arm, tools in (("PERUN", ["Read", "Grep", "Glob"]), ("TK", ["Read", "Grep", "Glob", "Agent"])):
            f = matched.flags(arm)
            self.assertEqual(f[f.index("--tools") + 1], ",".join(tools))
            i = f.index("--allowedTools")
            self.assertEqual(f[i + 1:i + 1 + len(tools)], tools)

    def test_only_tk_gets_the_agent_tool_and_plugin_dir(self):
        self.assertNotIn("Agent", matched.flags("PERUN"))
        self.assertNotIn("--plugin-dir", matched.flags("PERUN"))
        self.assertIn("Agent", matched.flags("TK"))
        self.assertEqual(matched.flags("TK")[matched.flags("TK").index("--plugin-dir") + 1], "pr-review-toolkit")

    def test_cap_is_four_dollars(self):
        self.assertEqual(matched.confirm.CAP, 4.0)

    def test_prompts_share_the_output_format(self):
        for p in matched.PROMPT.values():
            self.assertTrue(p.endswith(matched.d.bc.PRODUCER))

    def test_prompt_text_invokes_each_arm_the_way_it_ships(self):
        self.assertTrue(matched.PROMPT["PERUN"].startswith("/review FILE ./change.patch\n\n"))
        tk = matched.PROMPT["TK"]
        self.assertTrue(tk.startswith("Use the pr-review-toolkit:code-reviewer agent (Agent tool) to review this change"))
        self.assertNotIn("/review", tk)
        self.assertNotIn("pr-review-toolkit", matched.PROMPT["PERUN"])


class Cost(unittest.TestCase):
    def test_spent_for_sums_retries_of_one_arm_and_case(self):
        other = matched.d.SPLIT["heldout"][1]
        with tempfile.TemporaryDirectory() as t:
            led = Path(t) / "l.jsonl"
            led.write_text("\n".join(json.dumps(r) for r in [
                {"tag": f"TK/{CID}/1", "cost": 0.5}, {"tag": f"TK/{CID}/2", "cost": 0.25}, {"tag": f"PERUN/{CID}/1", "cost": 9},
                {"tag": f"TK/{other}/1", "cost": 7}, {"event": "run_start"}]) + "\n")
            with mock.patch.object(matched.confirm, "LEDGER", led):
                self.assertEqual(matched.spent_for("TK", CID), 0.75)

    def test_verdict_ratio_is_perun_over_tk(self):
        dollars = {"PERUN": 2.0, "TK": 1.0}
        seen = []
        with tempfile.TemporaryDirectory() as t, mock.patch.object(matched, "HERE", Path(t)), mock.patch.object(matched.d, "OUT", matched.d.OUT), \
                mock.patch.object(matched.d, "loadt", lambda a, c: dict(tokens=1, turns=1)), mock.patch.object(matched.d, "stats", lambda r: (0, 0, 0.5)), \
                mock.patch.object(matched.d, "boot", lambda a, b: (0, 0, 0.1)), mock.patch.object(matched, "spent_for", lambda a, c: dollars[a]), \
                mock.patch.object(matched.confirm, "spent", lambda: 0.0), \
                mock.patch.object(matched.confirm, "decide", lambda f1, ratio: seen.append((f1, ratio)) or "stub"):
            matched.verdict()
            res = json.loads((Path(t) / "results.json").read_text())
        self.assertEqual(seen, [(0.1, 2.0)])
        self.assertEqual(res["cost_ratio_perun_over_tk"], 2.0)
        self.assertEqual(res["n"], len(matched.d.SPLIT["heldout"]))


class Run(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        for obj, name, val in ((matched.confirm, "LEDGER", Path(self.t.name) / "ledger.jsonl"), (matched.confirm, "FLAGS", matched.confirm.FLAGS),
                               (matched, "OUT", Path(self.t.name) / "runs"), (matched, "PLUGIN", None), (matched.d, "OUT", matched.d.OUT)):
            p = mock.patch.object(obj, name, val)
            p.start()
            self.addCleanup(p.stop)

    def test_run_fetches_the_plugin_before_the_quota_probe(self):
        order = []
        with mock.patch.object(matched, "fetch_plugin", lambda dest: order.append("fetch") or Path(dest)), \
                mock.patch.object(matched.confirm, "call", lambda *a, **k: order.append("probe") or ("ok", "", {})), \
                mock.patch.object(matched, "review", lambda cid, arm: order.append(f"review {arm}")):
            matched.run(1)
        self.assertEqual(order, ["fetch", "probe", "review PERUN", "review TK"])

    def test_a_failed_fetch_makes_no_claude_call(self):
        with mock.patch.object(matched, "fetch_plugin", side_effect=SystemExit("hash")), \
                mock.patch.object(matched.confirm, "call", side_effect=AssertionError("call after failed fetch")):
            with self.assertRaises(SystemExit):
                matched.run(1)

    def test_review_sends_the_arm_prompt_and_flags_on_the_default_harness(self):
        calls = []

        def call(prompt, cwd, system, tag):
            calls.append((prompt, system, tag, list(matched.confirm.FLAGS), (Path(cwd) / "change.patch").is_file()))
            return "[]", "", {"turns": 1}
        with tempfile.TemporaryDirectory() as pl, mock.patch.object(matched, "PLUGIN", fake_plugin(pl)), mock.patch.object(matched.confirm, "call", call):
            for arm in matched.ARMS:
                matched.review(CID, arm)
        self.assertEqual(calls, [(matched.PROMPT[a], None, f"{a}/{CID}/1", matched.flags(a), True) for a in matched.ARMS])


class Guards(unittest.TestCase):
    """confirm.call must raise Stop on cap or quota before it ever reaches subprocess.run (which raises in this module)."""

    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.led = Path(self.t.name) / "ledger.jsonl"
        p = mock.patch.object(matched.confirm, "LEDGER", self.led)
        p.start()
        self.addCleanup(p.stop)

    def test_quota_at_or_above_stop_raises_before_any_subprocess(self):
        with mock.patch.dict(matched.confirm.ST, util=matched.confirm.QUOTA_STOP):
            with self.assertRaises(matched.confirm.Stop):
                matched.confirm.call("p", self.t.name, None, "x/1")
        self.assertFalse(self.led.exists())

    def test_cap_would_be_exceeded_raises_before_any_subprocess(self):
        self.led.write_text(json.dumps({"tag": "x", "cost": matched.CAP - matched.confirm.RESERVE + 0.01}) + "\n")
        with mock.patch.dict(matched.confirm.ST, util=0.0, inflight=0.0):
            with self.assertRaises(matched.confirm.Stop):
                matched.confirm.call("p", self.t.name, None, "x/2")
        self.assertEqual(len(self.led.read_text().splitlines()), 1)

    def test_subprocess_is_guarded_in_this_module(self):
        with mock.patch.dict(matched.confirm.ST, util=0.0, inflight=0.0), self.assertRaises(AssertionError):
            matched.confirm.call("p", self.t.name, None, "x/3")


if __name__ == "__main__":
    unittest.main()
