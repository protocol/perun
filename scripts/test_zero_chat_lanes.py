#!/usr/bin/env python3
"""Zero-chat lanes (#1571): the lane rules injected at SubagentStart, the fields-only handback and lower caps at
SubagentStop, and the lane audit ledger. Offline and hermetic: temp dirs only, synthetic transcripts (the shape was
observed on real Claude Code lane transcripts on 2026-10-16; the host documents no entry format), no real prose."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
import handback_cap as hc  # noqa: E402
import subagent_start_inject as si  # noqa: E402

CANARY = "CANARYTEXT"  # appears only inside transcript prose; it must never reach the ledger or any output


def clean_env(**extra):
    """The process env minus every knob these hooks read, so defaults are what a fresh install sees."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HANDBACK_", "HOUSE_", "SKILL_ROUTE", "LANE_RULES")) and k != "XDG_CACHE_HOME"}
    env.update(extra)
    return env


def run(script, args=(), payload=None, **env):
    p = subprocess.run([sys.executable, str(SC / script), *args], input=json.dumps(payload) if payload is not None else None,
                       capture_output=True, text=True, env=clean_env(**env))
    return p.returncode, p.stdout, p.stderr


def asst(block, rid="r1"):
    """One assistant entry per content block, as real transcripts log them (plus the surrounding metadata keys)."""
    return {"parentUuid": "p", "isSidechain": True, "agentId": "a1", "type": "assistant", "requestId": rid,
            "message": {"model": "m", "id": "msg_" + rid, "type": "message", "role": "assistant", "content": [block],
                        "usage": {"input_tokens": 1, "output_tokens": 2}}}


def text(t):
    return asst({"type": "text", "text": t})


def tool(name, **inp):
    return asst({"type": "tool_use", "id": "toolu_1", "name": name, "input": inp})


def noise():
    """Entries the parser must skip: prompt, attachment, a thinking block with only a signature, a tool result that
    itself contains the word "assistant" (so the cheap pre-filter lets the line through to the JSON check)."""
    return [{"type": "user", "message": {"role": "user", "content": f"{CANARY}-prompt"}},
            {"type": "attachment", "attachment": {"type": "hook_success"}},
            asst({"type": "thinking", "thinking": "", "signature": "s" * 80}),
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t",
                                                                      "content": 'the "assistant" said ' + "x" * 500}]}}]


def write(path, entries):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("".join(json.dumps(e) + "\n" for e in entries))
    return str(path)


FINAL = "status=VERIFIED\nsha=abc123"  # 26 chars = 7 estimated tokens
# One lane: 40 chars of narration (10 tok), Bash (4+21... see TOOL_*), a Write, then the final message.
LANE = [*noise(), text(CANARY + "n" * 30), tool("Bash", command="ls"), tool("Write", file_path="/x", content="c" * 62), text(FINAL)]
# Bash: 4 + len('{"command": "ls"}')=17 -> 21 chars; Write: 5 + len('{"file_path": "/x", "content": "<62 c>"}')=96 -> 101 chars; 122 chars -> 31 tok.


class Tmp(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        self.state, self.ledger = self.d / "state", self.d / "ledger.jsonl"
        self.env = dict(HANDBACK_STATE_DIR=str(self.state), HANDBACK_AUDIT_LEDGER=str(self.ledger))
        self.saved = hc.STATE_DIR
        hc.STATE_DIR = str(self.state)
        self.addCleanup(setattr, hc, "STATE_DIR", self.saved)

    def stop(self, msg, agent_id="a1", agent_type="builder", transcript=None, **extra_env):
        p = {"hook_event_name": "SubagentStop", "agent_id": agent_id, "agent_type": agent_type, "last_assistant_message": msg}
        if transcript:
            p["agent_transcript_path"] = str(transcript)
        return run("handback_cap.py", payload=p, **{**self.env, **extra_env})

    def rows(self):
        return [json.loads(x) for x in self.ledger.read_text().splitlines()] if self.ledger.exists() else []


class FieldsOnly(Tmp):
    def test_key_value_fields_pass(self):
        msg = "status=VERIFIED\nsha=1a2b3c4\nresult=lane rules shipped\ntests=12/12\nblockers=none\nreport=/tmp/x.md"
        self.assertEqual(self.stop(msg)[0], 0)

    def test_older_pipe_list_bare_token_colon_and_bullet_forms_pass(self):
        for msg in ("done | 4b2765b | next=merge", "VERIFIED", "status: VERIFIED\nsha: abc", "- sha=abc\n- tests=3/3"):
            self.assertEqual(self.stop(msg, agent_id="x" + str(abs(hash(msg))))[0], 0, msg)

    def test_a_sentence_is_rejected_with_the_line_and_the_fix(self):
        rc, _, err = self.stop("Done. All the tests pass and I pushed the branch.")
        self.assertEqual(rc, 2)
        self.assertIn("prose on line 1", err)
        self.assertIn("key=value", err)

    def test_one_prose_line_among_fields_is_named(self):
        rc, _, err = self.stop("sha=abc\ntests=3/3\nI also tidied the docs while there.")
        self.assertEqual((rc, "prose on line 3" in err), (2, True))

    def test_sentence_with_equals_sign_inside_is_still_prose(self):
        self.assertEqual(self.stop("I set x=3 and everything passed")[0], 2)

    def test_fields_only_knob_off_keeps_the_caps(self):
        off = dict(HANDBACK_FIELDS_ONLY="0")
        self.assertEqual(self.stop("Done. All the tests pass.", agent_id="k1", **off)[0], 0)
        self.assertEqual(self.stop("word " * 100, agent_id="k2", **off)[0], 2)  # 500 chars: over the 400 cap

    def test_exempt_types_skip_the_check(self):
        for t in hc.DEFAULT_EXEMPT_TYPES.split(","):
            self.assertEqual(self.stop("A long answer in prose. " * 30, agent_id="e" + t, agent_type=t)[0], 0, t)

    def test_release_valve_after_max_blocks(self):
        rcs = [self.stop("Prose only, no fields at all.", agent_id="v1")[0] for _ in range(hc.MAX_BLOCKS + 1)]
        self.assertEqual(rcs, [2] * hc.MAX_BLOCKS + [0])

    def test_max_blocks_knob_bounds_the_rewrite_cost_of_a_lane_that_cannot_comply(self):
        rcs = [self.stop("Prose only, no fields at all.", agent_id="v2", HANDBACK_MAX_BLOCKS="1")[0] for _ in range(3)]
        self.assertEqual(rcs, [2, 0, 0])


class Caps(Tmp):
    def test_default_caps_are_pinned_lower_than_the_old_800_and_10(self):
        out = subprocess.run([sys.executable, "-c", "import handback_cap as h; print(h.MAX_CHARS, h.MAX_LINES, h.MAX_BLOCKS)"],
                             capture_output=True, text=True, env=clean_env(PYTHONPATH=str(SC))).stdout.split()
        self.assertEqual(out, ["400", "8", "3"])

    def test_boundaries_chars_and_lines(self):
        ok = "k=" + "v" * 398  # exactly 400 chars
        self.assertEqual(self.stop(ok, agent_id="b1")[0], 0)
        self.assertEqual(self.stop(ok + "v", agent_id="b2")[0], 2)
        self.assertEqual(self.stop("\n".join(["k=v"] * 8), agent_id="b3")[0], 0)
        self.assertEqual(self.stop("\n".join(["k=v"] * 9), agent_id="b4")[0], 2)

    def test_env_knobs_move_the_caps(self):
        msg = "\n".join(["k=" + "v" * 50] * 10)  # 10 lines, 520 chars: over both defaults
        self.assertEqual(self.stop(msg, agent_id="c1")[0], 2)
        self.assertEqual(self.stop(msg, agent_id="c2", HANDBACK_MAX_CHARS="800", HANDBACK_MAX_LINES="10")[0], 0)

    def test_message_names_every_problem_once(self):
        rc, _, err = self.stop("sentence one. " * 40, agent_id="m1")
        self.assertEqual(rc, 2)
        self.assertIn("too long", err)
        self.assertIn("prose on line 1", err)

    def test_review_lane_entry_in_the_template_turns_fields_only_off(self):
        tpl = json.loads((ROOT / ".claude/skills/agentic-delivery/templates/operating-layer.settings.json").read_text())
        cmds = [h["command"] for e in tpl["hooks"]["SubagentStop"] for h in e["hooks"]]
        relaxed = [c for c in cmds if "HANDBACK_MAX_CHARS=2000" in c]
        self.assertEqual(len(relaxed), 1)
        self.assertIn("HANDBACK_FIELDS_ONLY=0", relaxed[0])


class AuditCounts(Tmp):
    def test_text_vs_tool_tokens_from_a_real_shaped_transcript(self):
        got = hc.lane_stats(write(self.d / "t.jsonl", LANE), FINAL)
        self.assertEqual(got[0], {"text_tok": 17, "narr_tok": 10, "final_tok": 7, "tool_tok": 31, "calls": 2})
        self.assertEqual(got[1], FINAL)

    def test_a_transcript_that_lags_the_hook_still_counts_the_final_once(self):
        lag = write(self.d / "lag.jsonl", [*noise(), text(CANARY + "n" * 30), tool("Bash", command="ls")])  # no final yet
        got = hc.lane_stats(lag, FINAL)[0]
        self.assertEqual((got["narr_tok"], got["final_tok"]), (10, 7))

    def test_subagent_handback_tool_message_is_the_final_not_a_tool_call(self):
        t = write(self.d / "hb.jsonl", [text("n" * 8), tool("Bash", command="ls"), tool("SubagentHandback", message=FINAL), text("all done")])
        got = hc.lane_stats(t)
        # 8 + 8 chars of text around the handback = 4 narration tokens; the handback message is the final; Bash is the only call
        self.assertEqual(got[0], {"text_tok": 11, "narr_tok": 4, "final_tok": 7, "tool_tok": 6, "calls": 1})
        self.assertEqual(got[1], FINAL)

    def test_unreadable_or_assistant_free_files_are_none_never_zeros(self):
        junk = self.d / "junk.jsonl"
        junk.write_text("not json at all\n{broken\n")
        users = write(self.d / "u.jsonl", [{"type": "user", "message": {"role": "user", "content": "hi"}}])
        for p in (self.d / "missing.jsonl", junk, users):
            self.assertIsNone(hc.lane_stats(str(p)), p)

    def test_text_tokens_round_up_and_are_additive(self):
        t = write(self.d / "r.jsonl", [text("a" * 5), text("b" * 5), text("status=ok")])  # 5+5 chars narration -> ceil(10/4)=3
        got = hc.lane_stats(t, "status=ok")[0]
        self.assertEqual((got["narr_tok"], got["final_tok"], got["text_tok"]), (3, 3, 6))


class AuditLedger(Tmp):
    def test_one_row_per_lane_with_counts_only(self):
        t = write(self.d / "t.jsonl", LANE)
        rc, out, err = self.stop(FINAL, transcript=t)
        self.assertEqual(rc, 0)
        (row,) = self.rows()
        self.assertEqual({k: row[k] for k in ("agent_id", "type", "exempt", "text_tok", "narr_tok", "final_tok", "tool_tok", "calls", "fields_ok", "blocks", "cpt")},
                         {"agent_id": "a1", "type": "builder", "exempt": False, "text_tok": 17, "narr_tok": 10, "final_tok": 7,
                          "tool_tok": 31, "calls": 2, "fields_ok": True, "blocks": 0, "cpt": 4})
        self.assertRegex(row["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        for surface in (self.ledger.read_text(), out, err):  # privacy: no transcript content anywhere
            self.assertNotIn(CANARY, surface)
            self.assertNotIn("sha=abc123", surface)

    def test_second_stop_of_the_same_lane_is_not_logged_again(self):
        t = write(self.d / "t.jsonl", LANE)
        self.stop(FINAL, transcript=t)
        self.stop(FINAL, transcript=t)
        self.assertEqual(len(self.rows()), 1)
        self.stop(FINAL, agent_id="a2", transcript=t)
        self.assertEqual([r["agent_id"] for r in self.rows()], ["a1", "a2"])

    def test_a_blocked_stop_is_not_logged_the_allowed_one_is_with_its_rewrite_count(self):
        t = write(self.d / "t.jsonl", LANE)
        self.assertEqual(self.stop("Done. I finished everything.", transcript=t)[0], 2)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.stop(FINAL, transcript=t)[0], 0)
        (row,) = self.rows()
        self.assertEqual(row["blocks"], 1)

    def test_an_empty_handback_is_not_counted_as_already_fields_only(self):
        t = write(self.d / "t.jsonl", [tool("Bash", command="ls")])
        self.assertEqual(self.stop("", transcript=t)[0], 0)  # the cap never blocks an empty message
        (row,) = self.rows()
        self.assertEqual((row["final_tok"], row["fields_ok"]), (0, False))

    def test_exempt_type_is_logged_and_flagged(self):
        t = write(self.d / "t.jsonl", LANE)
        self.assertEqual(self.stop("A free-form answer.", agent_type="Explore", transcript=t)[0], 0)
        (row,) = self.rows()
        self.assertEqual((row["type"], row["exempt"], row["fields_ok"]), ("Explore", True, False))

    def test_reads_the_lane_file_never_the_parent_session_file(self):
        parent = write(self.d / "sess.jsonl", [text(CANARY + "P" * 4000)])  # parent session: huge prose
        lane = write(self.d / "sess/subagents/agent-a1.jsonl", LANE)
        p = {"hook_event_name": "SubagentStop", "agent_id": "a1", "agent_type": "builder", "last_assistant_message": FINAL,
             "transcript_path": parent, "agent_transcript_path": lane}
        self.assertEqual(run("handback_cap.py", payload=p, **self.env)[0], 0)
        self.assertEqual(self.rows()[0]["narr_tok"], 10)

    def test_derives_the_documented_nested_path_when_agent_transcript_path_is_absent(self):
        parent = write(self.d / "sess.jsonl", [text("P" * 4000)])
        write(self.d / "sess/subagents/agent-a1.jsonl", LANE)
        p = {"hook_event_name": "SubagentStop", "agent_id": "a1", "agent_type": "builder", "last_assistant_message": FINAL, "transcript_path": parent}
        self.assertEqual(run("handback_cap.py", payload=p, **self.env)[0], 0)
        self.assertEqual(self.rows()[0]["narr_tok"], 10)
        self.assertEqual(hc._lane_transcript({"agent_id": "x"}), None)  # nothing to derive from

    def test_no_transcript_or_unparsable_transcript_logs_nothing_and_never_blocks(self):
        rc, _, err = self.stop(FINAL)  # no transcript path at all
        self.assertEqual((rc, self.rows()), (0, []))
        bad = self.d / "bad.jsonl"
        bad.write_text("garbage\n")
        rc, _, err = self.stop(FINAL, agent_id="a9", transcript=bad)
        self.assertEqual((rc, self.rows()), (0, []))
        self.assertIn("COULD_NOT_CHECK", err)

    def test_ledger_can_be_disabled(self):
        t = write(self.d / "t.jsonl", LANE)
        for off in ("off", ""):
            self.assertEqual(self.stop(FINAL, agent_id="d" + off, transcript=t, HANDBACK_AUDIT_LEDGER=off)[0], 0)
        self.assertFalse(self.ledger.exists())

    def test_an_unwritable_ledger_never_changes_the_exit_code(self):
        t = write(self.d / "t.jsonl", LANE)
        rc, _, err = self.stop(FINAL, transcript=t, HANDBACK_AUDIT_LEDGER=str(self.d))  # a directory, not a file
        self.assertEqual(rc, 0)
        self.assertIn("COULD_NOT_CHECK", err)

    def test_default_ledger_lives_under_xdg_cache_home_perun(self):
        t = write(self.d / "t.jsonl", LANE)
        p = {"hook_event_name": "SubagentStop", "agent_id": "a1", "agent_type": "builder", "last_assistant_message": FINAL, "agent_transcript_path": t}
        env = dict(HANDBACK_STATE_DIR=str(self.state), XDG_CACHE_HOME=str(self.d / "cache"))
        self.assertEqual(run("handback_cap.py", payload=p, **env)[0], 0)
        self.assertEqual(len((self.d / "cache/perun/lane-audit.jsonl").read_text().splitlines()), 1)


class Report(Tmp):
    ROWS = [
        {"type": "a", "exempt": False, "text_tok": 100, "narr_tok": 60, "final_tok": 40, "tool_tok": 1000, "fields_ok": True, "blocks": 0},
        {"type": "a", "exempt": False, "text_tok": 300, "narr_tok": 250, "final_tok": 50, "tool_tok": 3000, "fields_ok": False, "blocks": 1},
        {"type": "a", "exempt": False, "text_tok": 200, "narr_tok": 100, "final_tok": 100, "tool_tok": 2000, "fields_ok": True, "blocks": 0},
        {"type": "Explore", "exempt": True, "text_tok": 9999, "narr_tok": 0, "final_tok": 9999, "tool_tok": 1, "fields_ok": False, "blocks": 0},
    ]

    def test_summary_numbers_exempt_excluded_projection_labelled_estimate(self):
        s = hc.summary(self.ROWS)
        self.assertIn("lanes=3 (+1 exempt-type lanes excluded)", s)
        self.assertRegex(s, r"text_tok\s+median=200 p90=300 total=600")
        self.assertRegex(s, r"narr_tok\s+median=100 ")
        self.assertRegex(s, r"tool_tok\s+median=2000 ")
        self.assertIn("9.1%", s)  # 600 / (600 + 6000)
        self.assertIn("fields_ok: 66.7%", s)
        self.assertIn("needing a rewrite under the current caps: 33.3%", s)
        lim = min(hc.MAX_CHARS // hc.CPT, 70)  # median of today's fields-only handbacks (40, 100) is 70
        after = [min(f, lim) for f in (40, 50, 100)]
        self.assertIn(f"projection (ESTIMATE; assumes every lane complies", s)
        self.assertIn(f"text_tok median={sorted(after)[1]} total={sum(after)}", s)

    def test_empty_summary_does_not_divide_by_zero(self):
        self.assertEqual(hc.summary([]), "lanes=0 (0 exempt-type lanes excluded)")

    def test_scan_audits_existing_transcripts_and_prints_aggregates_only(self):
        lane = write(self.d / "proj/sess/subagents/agent-aaa.jsonl", LANE)
        (self.d / "proj/sess/subagents/agent-aaa.meta.json").write_text(json.dumps({"agentType": "builder", "description": CANARY}))
        rc, out, err = run("handback_cap.py", ["--scan", str(self.d), "--since-days", "1"])
        self.assertEqual(rc, 0, err)
        self.assertIn("lanes=1", out)
        self.assertIn("ESTIMATE", out)
        self.assertNotIn(CANARY, out + err)
        os.utime(lane, (1, 1))  # 1970: outside the window
        self.assertIn("lanes=0", run("handback_cap.py", ["--scan", str(self.d), "--since-days", "1"])[1])

    def test_scan_marks_a_prose_handback_as_needing_a_rewrite(self):
        prose = write(self.d / "p/s/subagents/agent-bbb.jsonl", [text("n" * 8), tool("Bash", command="ls"), tool("SubagentHandback", message="Everything is done and pushed.")])
        out = run("handback_cap.py", ["--scan", prose])[1]
        self.assertIn("fields_ok: 0.0%", out)
        self.assertIn("needing a rewrite under the current caps: 100.0%", out)

    def test_scan_marks_exempt_types_from_the_meta_file(self):
        write(self.d / "p/s/subagents/agent-ccc.jsonl", LANE)
        (self.d / "p/s/subagents/agent-ccc.meta.json").write_text(json.dumps({"agentType": "Explore"}))
        self.assertIn("lanes=0 (1 exempt-type lanes excluded)", run("handback_cap.py", ["--scan", str(self.d)])[1])

    def test_report_reads_the_ledger_and_a_missing_ledger_is_exit_2(self):
        t = write(self.d / "t.jsonl", LANE)
        self.stop(FINAL, transcript=t)
        rc, out, _ = run("handback_cap.py", ["--report", str(self.ledger)])
        self.assertEqual(rc, 0)
        self.assertIn("lanes=1", out)
        self.assertRegex(out, r"narr_tok\s+median=10 ")
        rc, _, err = run("handback_cap.py", ["--report", str(self.d / "nope.jsonl")])
        self.assertEqual(rc, 2)
        self.assertIn("no ledger", err)


class LaneRules(unittest.TestCase):
    def inject(self, agent_type="general-purpose", **env):
        rc, out, err = run("subagent_start_inject.py", payload={"hook_event_name": "SubagentStart", "agent_type": agent_type}, **env)
        self.assertEqual(rc, 0, err)
        return json.loads(out)["hookSpecificOutput"]["additionalContext"]

    def test_injected_without_any_house_file(self):
        ctx = self.inject()
        self.assertIn(si.LANE_RULES, ctx)
        self.assertIn(si.HOST_RULES, ctx)

    def test_injected_alongside_a_house_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "house.md"
            f.write_text("Be terse.\n")
            ctx = self.inject(HOUSE_DEFAULTS_FILE=str(f))
        self.assertTrue(ctx.startswith("Be terse."))
        self.assertIn(si.LANE_RULES, ctx)

    def test_chat_deliverable_types_get_no_lane_rules_and_the_list_matches_the_cap_hook(self):
        self.assertEqual(si.CHAT_TYPES, hc.DEFAULT_EXEMPT_TYPES)
        for t in si.CHAT_TYPES.split(","):
            self.assertNotIn("Lane output", self.inject(t), t)

    def test_exempt_env_var_is_shared_with_the_cap_hook(self):
        self.assertNotIn("Lane output", self.inject("security-reviewer", HANDBACK_EXEMPT_TYPES="security-reviewer"))
        self.assertIn("Lane output", self.inject("Explore", HANDBACK_EXEMPT_TYPES="security-reviewer"))  # the list REPLACES the default

    def test_skip_types_env_drops_the_rule_for_a_relaxed_review_type_only(self):
        env = dict(LANE_RULES_SKIP_TYPES="security-reviewer,other")  # a type that keeps a raised cap, not an exemption
        self.assertNotIn("Lane output", self.inject("security-reviewer", **env))
        self.assertIn("Lane output", self.inject("builder", **env))
        self.assertNotIn("Lane output", self.inject("Explore", **env))  # the built-in chat types stay skipped

    def test_opt_out(self):
        self.assertNotIn("Lane output", self.inject(LANE_RULES="0"))

    def test_rule_text_pins_zero_prose_and_fields_only_and_the_cap_it_states(self):
        r = si.LANE_RULES
        for needle in ("tool calls only", "zero prose", "no narration, plans, recaps", "key=value", "no sentences", "status=VERIFIED|UNVERIFIED", "sha=", "tests=", "blockers=", "report=<path>"):
            self.assertIn(needle, r)
        default_cap = int(subprocess.run([sys.executable, "-c", "import handback_cap as h; print(h.MAX_CHARS)"], capture_output=True, text=True,
                                         env=clean_env(PYTHONPATH=str(SC))).stdout)
        self.assertEqual(int(re.search(r"under (\d+) characters", r).group(1)), default_cap)  # injection and backstop agree

    def test_rule_is_small_next_to_the_plain_caveman_ultra_line(self):
        # The plain caveman-ultra subagent line is ~161 chars (measured 2026-10-16); the lane rules stay under 2.5x of it.
        self.assertLessEqual(len(si.LANE_RULES), 400)

    def test_the_shape_the_rule_teaches_passes_the_backstop_first_try(self):
        saved, hc.STATE_DIR = hc.STATE_DIR, tempfile.mkdtemp()
        self.addCleanup(setattr, hc, "STATE_DIR", saved)
        self.addCleanup(shutil.rmtree, hc.STATE_DIR, True)
        msg = "status=VERIFIED\nsha=1a2b3c4d5e6f\nresult=lane rules shipped\ntests=57/57\nblockers=none\nreport=/work/details.md"
        self.assertEqual(hc.check({"agent_id": "ok1", "last_assistant_message": msg}), 0)


class Docs(unittest.TestCase):
    def read(self, rel):
        return (ROOT / rel).read_text()

    def test_preamble_states_zero_chat_and_the_fields_shape_and_keeps_its_older_rules(self):
        lp = self.read(".claude/skills/agentic-delivery/templates/lane-preamble.md")
        for needle in ("Zero chat between tool calls", "now I will", "`key=value` fields only", "400 characters and 8 lines", "`status=VERIFIED|UNVERIFIED`", "`handback_cap.py` rejects"):
            self.assertIn(needle, lp)
        self.assertNotIn("`status | evidence | next`", lp)
        self.assertIn("never `git add -A`", lp)
        self.assertIn("hand back its path", lp)

    def test_docs_state_the_new_defaults_not_the_old_ones(self):
        for rel in ("docs/for-fleets.md", "docs/technical-overview.md", ".claude/skills/agentic-delivery/references/host-enforcement.md"):
            t = self.read(rel)
            self.assertNotIn("800 char", t, rel)
            self.assertNotIn("10 lines", t, rel)
            self.assertRegex(t, r"400 char", rel)
            self.assertRegex(t, r"8 lines", rel)

    def test_host_enforcement_explains_why_the_review_lane_entry_needs_a_scoped_default_entry(self):
        he = self.read(".claude/skills/agentic-delivery/references/host-enforcement.md")
        self.assertIn("run in parallel and any block wins", he.replace("\n", " "))
        self.assertIn("^(?!security-reviewer$).*", he)
        self.assertIn("LANE_RULES_SKIP_TYPES", he)  # a relaxed type must also be skipped by the injected rule

    def test_standards_index_logs_the_fetched_sources_dated(self):
        text = self.read("docs/standards-index.md")
        heading = next(ln for ln in text.splitlines() if "SubagentStop transcript fields and transcript format" in ln)
        self.assertIn("2026-10-16", heading)
        section = text.split(heading, 1)[1]
        for url in ("https://code.claude.com/docs/en/hooks", "https://code.claude.com/docs/en/sessions.md",
                    "https://code.claude.com/docs/en/agent-sdk/session-storage.md"):
            self.assertIn(url, section)
        self.assertIn("agent_transcript_path", section)
        self.assertIn("internal to Claude Code and changes between versions", section)

    def test_ci_runs_the_selftests_and_this_file(self):
        ci = self.read(".github/workflows/ci.yml")
        for needle in ("handback_cap.py --selftest", "subagent_start_inject.py --selftest", "scripts/test_zero_chat_lanes.py"):
            self.assertIn(needle, ci)

    def test_install_default_house_file_no_longer_carries_a_second_copy_of_the_handback_rule(self):
        self.assertNotIn("Hand-back:", self.read("install.sh"))


if __name__ == "__main__":
    unittest.main()
