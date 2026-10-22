#!/usr/bin/env python3
"""Tests for `token_report.py --nudge` and its SessionStart wiring in session_brief.py.

Covers: the line fires on the top --advise lever, stays silent on a healthy session and on a lever the settings already set,
the did-it-work receipt (before/after input-eq per turn, `unknown` under the turn floor, quiet after 14 days), the opt-out
policy key `spend_nudge=off`, and the hook's cache (hit, miss, stale-after-settings-change, 14-day expiry, one refresh per lock
window, the size gate, line order and cap). Fixtures are synthetic usage rows with a fictional model; a secret-looking message
body or lane description must never reach the output or the cache.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / ".claude/skills/agentic-ceo/scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / ".claude/skills/agentic-delivery/scripts"))
import session_brief as sb  # noqa: E402
import token_report as tr  # noqa: E402

T0 = datetime(2026, 10, 21, 9, 0, 0, tzinfo=timezone.utc)
APPLY_AT = T0 + timedelta(seconds=750)  # 25 turns (0..720s) before, the rest after


def turn(i, at, read, write=500, model="claude-sonnet-5"):
    usage = {"input_tokens": 10, "cache_read_input_tokens": read, "cache_creation_input_tokens": write,
             "cache_creation": {"ephemeral_5m_input_tokens": write, "ephemeral_1h_input_tokens": 0}, "output_tokens": 50}
    return {"type": "assistant", "requestId": f"r{i}", "timestamp": (T0 + timedelta(seconds=at)).isoformat().replace("+00:00", "Z"),
            "message": {"model": model, "usage": usage, "content": [{"type": "text", "text": "SECRET-BODY"}]}}


def healthy(n=3):
    return [turn(i, i * 30, 20_000) for i in range(n)]


def firing():  # peak main context over 400k with no auto-compact window: the ctx-window rule, UNPRICED
    return [turn(0, 0, 450_000, 0)]


def split(before, after, read_before=100_000, read_after=50_000):
    return ([turn(i, i * 30, read_before) for i in range(before)]
            + [turn(100 + i, 780 + i * 30, read_after) for i in range(after)])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.proj = self.dir / "proj"
        (self.proj / ".claude").mkdir(parents=True)
        self.home = self.dir / "home"
        env = {k: v for k, v in os.environ.items() if k not in ("PERUN_POLICY", "XDG_CACHE_HOME", "CLAUDE_CODE_SUBAGENT_MODEL")}
        env.update(CLAUDE_CONFIG_DIR=str(self.home), XDG_CACHE_HOME=str(self.dir / "cache"))
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def transcript(self, rows, name="s1", mtime=None):
        d = self.home / "projects" / tr.re.sub(r"[^A-Za-z0-9]", "-", str(self.proj.resolve()))
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{name}.jsonl"
        p.write_text("".join(json.dumps(r) + "\n" for r in rows))
        if mtime:
            os.utime(p, (mtime, mtime))
        return str(p)

    def settings(self, obj, bak=None):
        f = self.proj / ".claude" / "settings.json"
        f.write_text(json.dumps(obj))
        if bak is not None:
            b = Path(str(f) + ".bak")
            b.write_text(json.dumps(bak))
            Path(str(f) + tr.APPLIED_SUFFIX).touch()  # the marker apply_plan leaves beside its backup
            os.utime(b, (APPLY_AT.timestamp(),) * 2)

    def line(self, session, **kw):
        return tr.nudge(session, str(self.proj), now=APPLY_AT + timedelta(hours=1), **kw)


class Nudge(Base):
    def test_fires_with_top_lever_usd_and_command(self):
        got = self.line(self.transcript(firing()))
        self.assertTrue(got.startswith("spend: [ctx-window] "), got)
        self.assertIn("at stake UNPRICED", got)
        self.assertIn(f"token_report.py --session {self.home}", got)
        self.assertIn("--fix-plan --project", got)  # the compact lever maps to autoCompactWindow, so a patch exists
        self.assertNotIn("\n", got)
        self.assertNotIn("SECRET-BODY", got)

    def test_command_falls_back_to_advise_when_no_settings_patch_exists(self):
        rows = [turn(i, i * 30, 150_000 if i % 2 == 0 else 10_000, 0) for i in range(6)]  # two halvings: the ctx-drops rule, no settings key
        got = self.line(self.transcript(rows))
        self.assertTrue(got.startswith("spend: [ctx-drops] "), got)
        self.assertIn("--advise --project", got)

    def test_silent_when_nothing_fires(self):
        self.assertEqual(self.line(self.transcript(healthy())), "")

    def test_silent_when_the_lever_is_already_set(self):
        self.settings({"autoCompactWindow": 200000})
        self.assertEqual(self.line(self.transcript(firing())), "")

    def test_oversize_transcript_is_skipped_unread(self):
        self.assertEqual(self.line(self.transcript(firing()), max_bytes=10), "")

    def test_evidence_names_lane_file_stems_never_the_free_text_description(self):
        secret = "sk-live-0123456789abcdef jane@example.com"
        s = self.transcript(healthy())
        lane = Path(s[:-6]) / "subagents"
        lane.mkdir(parents=True)
        row = {"type": "assistant", "isSidechain": True, "requestId": "l0", "timestamp": T0.isoformat().replace("+00:00", "Z"),
               "message": {"model": "claude-opus-5", "usage": {"input_tokens": 10, "output_tokens": 1}, "content": [{"type": "tool_use", "id": "t1", "name": "Bash"}]}}
        (lane / "agent-1.jsonl").write_text(json.dumps(row) + "\n")
        (lane / "agent-1.meta.json").write_text(json.dumps({"description": secret, "agentType": "x"}))
        got = self.line(s)
        self.assertTrue(got.startswith("spend: [tier] "), got)
        self.assertIn("agent-1", got)
        cache = str(self.dir / "c.json")
        tr.write_nudge_cache(cache, tr.nudge_key(s, str(self.proj)), got)
        for text in (got, Path(cache).read_text()):
            self.assertNotIn("sk-live", text)
            self.assertNotIn("jane@example.com", text)

    def test_cli_writes_the_cache_and_clears_the_lock(self):
        s = self.transcript(firing())
        cache = self.dir / "cache" / "perun" / "c.json"
        cache.parent.mkdir(parents=True)
        Path(str(cache) + ".lock").write_text("1 1")
        r = subprocess.run([sys.executable, str(SCRIPTS / "token_report.py"), "--nudge", "--session", s, "--project", str(self.proj), "--nudge-cache", str(cache)],
                           capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(r.returncode, 0, r)
        got = json.loads(cache.read_text())
        self.assertTrue(got["line"].startswith("spend: [ctx-window]"), got)
        self.assertEqual(got["key"], json.loads(json.dumps(tr.nudge_key(s, str(self.proj)))))
        self.assertFalse(Path(str(cache) + ".lock").exists())

    def test_failure_and_timeout_cache_an_empty_line_for_the_same_key(self):
        s = self.transcript(firing())
        cache = self.dir / "c.json"
        argv = ["--nudge", "--session", s, "--project", str(self.proj), "--nudge-cache", str(cache)]
        with mock.patch.object(tr, "nudge", side_effect=RuntimeError("boom")):
            self.assertEqual(tr.main(argv), 0)
        self.assertEqual(json.loads(cache.read_text())["line"], "")

    def watchdog(self, src):
        """Run `token_report.main(--nudge ...)` in a child whose nudge() is `fake` from `src`, with a 1 s watchdog; return (rc, seconds, cache, session)."""
        s = self.transcript(firing())
        cache, lock = self.dir / "w.json", self.dir / "w.json.lock"
        lock.write_text("1 1")
        code = ("import sys, time; sys.path.insert(0, sys.argv[1]); import token_report as tr\n"
                f"tr.NUDGE_TIMEOUT_S = 1\n{src}\ntr.nudge = fake\n"
                "sys.exit(tr.main(['--nudge', '--session', sys.argv[2], '--project', sys.argv[3], '--nudge-cache', sys.argv[4]]))")
        started = time.monotonic()
        r = subprocess.run([sys.executable, "-c", code, str(SCRIPTS), s, str(self.proj), str(cache)], capture_output=True, text=True,
                           env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=30)
        self.assertFalse(lock.exists())
        return r.returncode, time.monotonic() - started, json.loads(cache.read_text()), s

    def test_a_hung_refresh_is_cut_off_and_caches_an_empty_line_for_the_same_key(self):
        rc, took, got, s = self.watchdog("def fake(*a, **k):\n    time.sleep(20)")
        self.assertEqual((rc, got["line"], got["key"]["s"][0]), (0, "", s))
        self.assertLess(took, 10)

    def test_the_watchdog_cannot_be_swallowed_by_an_except_oserror(self):
        loop = "def fake(*a, **k):\n    while True:\n        try:\n            time.sleep(0.1)\n        except OSError:\n            pass"  # TimeoutError is an OSError
        rc, took, got, _ = self.watchdog(loop)
        self.assertEqual((rc, got["line"]), (0, ""))
        self.assertLess(took, 10)

    def test_cli_prints_one_line_or_nothing_and_exits_zero(self):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        run = lambda *a: subprocess.run([sys.executable, str(SCRIPTS / "token_report.py"), "--nudge", "--project", str(self.proj), *a],  # noqa: E731
                                        capture_output=True, text=True, env=env)
        r = run("--session", self.transcript(firing()))
        self.assertEqual((r.returncode, r.stdout.count("\n")), (0, 1))
        self.assertTrue(r.stdout.startswith("spend: [ctx-window]"))
        r = run("--session", str(self.dir / "missing.jsonl"))
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        r = run()  # no --session: the newest transcript of the project (the firing one written above)
        self.assertTrue(r.stdout.startswith("spend: [ctx-window]"), r)


class Receipt(Base):
    def apply(self):
        self.settings({"autoCompactWindow": 200000}, bak={})

    def test_before_after_percent_with_counts(self):
        self.apply()
        got = tr.receipt(self.transcript(split(25, 25)), str(self.proj), APPLY_AT + timedelta(hours=1))
        # per turn: 10 + 500*1.25 + read*0.1 -> 10635 before, 5635 after
        self.assertEqual(got, "since applying autoCompactWindow: input-eq/turn -47% (25 turns before, 25 after)")

    def test_unknown_under_the_floor(self):
        self.apply()
        got = tr.receipt(self.transcript(split(25, 5)), str(self.proj), APPLY_AT + timedelta(hours=1))
        self.assertEqual(got, "since applying autoCompactWindow: input-eq/turn unknown (25 turns before, 5 after; need 20 each)")
        self.assertIn("unknown (3 turns before", tr.receipt(self.transcript(split(3, 25)), str(self.proj), APPLY_AT + timedelta(hours=1)))

    def test_floor_is_inclusive(self):
        self.apply()
        got = tr.receipt(self.transcript(split(20, 20)), str(self.proj), APPLY_AT + timedelta(hours=1))
        self.assertIn("%", got)
        self.assertNotIn("unknown", got)

    def test_none_without_a_backup_or_after_14_days(self):
        s = self.transcript(split(25, 25))
        self.settings({"autoCompactWindow": 200000})
        self.assertIsNone(tr.receipt(s, str(self.proj), APPLY_AT))
        self.apply()
        self.assertIsNone(tr.receipt(s, str(self.proj), APPLY_AT + timedelta(days=15)))

    def earlier_session(self, rows, age=3600, pad=0):
        rows = rows + ([{"type": "summary", "x": "y" * pad}] if pad else [])
        return self.transcript(rows, name="s0", mtime=APPLY_AT.timestamp() - age)

    def test_apply_in_an_earlier_session_still_reports(self):
        self.apply()
        self.earlier_session(split(25, 0))
        got = tr.receipt(self.transcript(split(0, 25)), str(self.proj), APPLY_AT + timedelta(hours=1))
        self.assertEqual(got, "since applying autoCompactWindow: input-eq/turn -47% (25 turns before, 25 after)")

    def test_a_resumed_sessions_copied_turns_count_once(self):
        self.apply()
        self.earlier_session(split(25, 0))
        got = tr.receipt(self.transcript(split(25, 25)), str(self.proj), APPLY_AT + timedelta(hours=1))
        self.assertIn("(25 turns before, 25 after)", got)

    def test_transcripts_over_the_cap_or_older_than_the_window_are_not_read(self):
        self.apply()
        now = APPLY_AT + timedelta(hours=1)
        s = self.transcript(split(0, 25))
        self.earlier_session(split(25, 0), pad=100_000)
        cap = os.path.getsize(s) + 1
        self.assertIn("unknown (0 turns before, 25 after", tr.receipt(s, str(self.proj), now, max_bytes=cap))
        self.assertIn("(25 turns before, 25 after)", tr.receipt(s, str(self.proj), now))
        self.earlier_session(split(25, 0), age=20 * 86400)
        self.assertIn("unknown (0 turns before", tr.receipt(s, str(self.proj), now))

    def test_a_symlinked_project_path_finds_the_backup(self):
        self.apply()
        link = self.dir / "link"
        link.symlink_to(self.proj)
        self.assertIn("-47%", tr.receipt(self.transcript(split(25, 25)), str(link), APPLY_AT + timedelta(hours=1)))

    def test_nudge_line_carries_receipt_with_and_without_a_lever(self):
        self.apply()
        got = self.line(self.transcript(split(25, 25)))
        self.assertEqual(got, "spend: since applying autoCompactWindow: input-eq/turn -47% (25 turns before, 25 after)")
        self.settings({"env": {"X": "1"}}, bak={})
        got = self.line(self.transcript([turn(999, 5, 450_000, 0)] + split(25, 25)))
        self.assertTrue(got.startswith("spend: [ctx-window] ") and " | since applying env.X: " in got, got)
        self.assertEqual(got.count("\n"), 0)


class Hardening(Base):
    """The receipt can fail or be dropped without taking the advise line with it; only an `--apply` backup counts; evidence stays name-free."""

    def both(self):
        """A session with a firing rule AND a receipt-worthy apply; returns its path."""
        self.settings({"env": {"X": "1"}}, bak={})
        return self.transcript([turn(999, 5, 450_000, 0)] + split(25, 25))

    def test_receipt_over_the_byte_budget_leaves_the_advise_line(self):
        s = self.both()
        self.assertIn(" | since applying env.X: ", self.line(s, max_bytes=tr.NUDGE_MAX_BYTES))
        with mock.patch.object(tr, "NUDGE_RECEIPT_BYTES", 10):
            self.assertIsNone(tr.receipt(s, str(self.proj), APPLY_AT + timedelta(hours=1), tr.NUDGE_MAX_BYTES))
            got = self.line(s, max_bytes=tr.NUDGE_MAX_BYTES)
        self.assertTrue(got.startswith("spend: [ctx-window] ") and "since applying" not in got, got)

    def test_receipt_past_its_deadline_is_dropped_and_the_budget_applies_only_to_the_hook(self):
        s = self.both()
        with mock.patch.object(tr, "NUDGE_RECEIPT_DEADLINE_S", -1), mock.patch.object(tr, "NUDGE_RECEIPT_BYTES", 10):
            self.assertIsNone(tr.receipt(s, str(self.proj), APPLY_AT + timedelta(hours=1), tr.NUDGE_MAX_BYTES))
            self.assertIn("(26 turns before, 25 after)", tr.receipt(s, str(self.proj), APPLY_AT + timedelta(hours=1)))  # a manual run has no budget

    def test_a_receipt_error_leaves_the_advise_line(self):
        s = self.both()
        with mock.patch.object(tr, "receipt", side_effect=RuntimeError("boom")):
            got = self.line(s)
        self.assertTrue(got.startswith("spend: [ctx-window] ") and "since applying" not in got, got)

    def test_a_backup_without_the_apply_marker_is_not_a_receipt(self):
        s = self.both()
        Path(str(self.proj / ".claude" / "settings.json") + tr.APPLIED_SUFFIX).unlink()
        self.assertIsNone(tr.receipt(s, str(self.proj), APPLY_AT + timedelta(hours=1)))

    def test_apply_plan_marks_only_a_backup_it_wrote(self):
        f = self.proj / ".claude" / "settings.json"
        f.write_text("{}")
        tr.apply_plan(str(f), {"autoCompactWindow": 200000})
        self.assertTrue(Path(str(f) + ".bak").is_file() and Path(str(f) + tr.APPLIED_SUFFIX).is_file())
        g = self.proj / ".claude" / "settings.local.json"
        g.write_text("{}")
        Path(str(g) + ".bak").write_text("{}")  # a backup some other tool left first
        tr.apply_plan(str(g), {"autoCompactWindow": 200000})
        self.assertFalse(Path(str(g) + tr.APPLIED_SUFFIX).exists())

    def test_the_marker_is_part_of_the_cache_key(self):
        s = self.transcript(healthy())
        before = tr.nudge_key(s, str(self.proj))
        self.settings({"autoCompactWindow": 1}, bak={})
        self.assertNotEqual(before["c"], tr.nudge_key(s, str(self.proj))["c"])

    def test_unused_mcp_evidence_is_a_count_not_server_names(self):
        names = ["acme-crm-prod", "jane-private-db", "billing-live"]
        f = {"bad": False, "cfg": {}, "mcp": names, "used": set()}
        ev = tr._r_mcp_unused(f)[0]
        self.assertTrue(ev.startswith("3 of 3 MCP servers"), ev)
        for n in names:
            self.assertNotIn(n, ev)


class Hook(Base):
    def setUp(self):
        super().setUp()
        self.spawned = []
        patcher = mock.patch.object(sb, "_spawn_refresh", self.spawned.append)
        patcher.start()
        self.addCleanup(patcher.stop)
        sb._SESSION[0] = None
        self.addCleanup(lambda: sb._SESSION.__setitem__(0, None))

    def cache(self):
        return Path(os.environ["XDG_CACHE_HOME"]) / "perun" / f"spend-nudge-{hashlib.sha1(os.path.realpath(self.proj).encode()).hexdigest()[:16]}.json"

    def fill(self, line="spend: [ctx-window] x", key_edit=None):
        s = self.transcript(firing())
        self.cache().parent.mkdir(parents=True, exist_ok=True)
        key = {**tr.nudge_key(s, str(self.proj)), **(key_edit or {})}
        self.cache().write_text(json.dumps({"key": key, "line": line}))
        return s

    def stub_sections(self, **lines):
        """Replace every brief() section with a fixed line (None when not named)."""
        for name in ("merge_line", "version_line", "committed_line", "hygiene_line", "priority_line", "spend_line", "drift_line"):
            p = mock.patch.object(sb, name, lambda repo, v=lines.get(name): v)
            p.start()
            self.addCleanup(p.stop)

    def test_miss_spawns_a_detached_refresh_and_prints_nothing(self):
        s = self.transcript(firing())
        self.assertIsNone(sb.spend_line(self.proj))
        self.assertEqual(len(self.spawned), 1)
        cmd = self.spawned[0]
        self.assertEqual(cmd[2:5], ["--nudge", "--session", s])
        self.assertIn("--nudge-cache", cmd)

    def test_hit_prints_the_cached_line_and_spawns_nothing(self):
        self.fill()
        self.assertEqual(sb.spend_line(self.proj), "spend: [ctx-window] x")
        self.assertEqual(self.spawned, [])

    def test_newer_transcript_refreshes_but_keeps_the_line_while_settings_are_unchanged(self):
        self.fill()
        self.transcript(firing() + healthy(), name="s2", mtime=datetime.now().timestamp() + 60)
        self.assertEqual(sb.spend_line(self.proj), "spend: [ctx-window] x")
        self.assertEqual(len(self.spawned), 1)

    def test_settings_change_drops_the_stale_line_at_once(self):
        self.fill()
        self.settings({"autoCompactWindow": 200000})
        self.assertIsNone(sb.spend_line(self.proj))
        self.assertEqual(len(self.spawned), 1)

    def test_the_current_session_transcript_is_not_the_prior_one(self):
        old = self.transcript(firing(), name="old", mtime=1_700_000_000)
        self.transcript(healthy(), name="current")
        sb._SESSION[0] = "current"
        sb.spend_line(self.proj)
        self.assertEqual(self.spawned[0][4], old)

    def test_opt_out_policy_key(self):
        self.fill()
        (self.proj / ".perun").mkdir()
        (self.proj / ".perun" / "policy.json").write_text('{"spend_nudge": "off"}')
        self.assertIsNone(sb.spend_line(self.proj))
        self.assertEqual(self.spawned, [])
        (self.proj / ".perun" / "policy.json").write_text('{"spend_nudge": "on"}')
        self.assertEqual(sb.spend_line(self.proj), "spend: [ctx-window] x")

    def test_a_second_miss_inside_the_lock_window_does_not_spawn(self):
        self.transcript(firing())
        sb.spend_line(self.proj)
        sb.spend_line(self.proj)
        self.assertEqual(len(self.spawned), 1)
        lock = Path(str(self.cache()) + ".lock")
        pid, at = lock.read_text().split()
        self.assertEqual((int(pid), abs(int(at) - time.time()) < 5), (os.getpid(), True))
        self.assertGreater(tr.NUDGE_LOCK_TTL_S, tr.NUDGE_TIMEOUT_S)
        os.utime(lock, (time.time() - tr.NUDGE_LOCK_TTL_S - 1,) * 2)  # a dead refresh: the lock goes stale
        sb.spend_line(self.proj)
        self.assertEqual(len(self.spawned), 2)

    def test_size_gate_skips_a_transcript_over_the_cap(self):
        self.assertEqual(tr.NUDGE_MAX_BYTES, 128_000_000)
        s = self.transcript(firing())
        with mock.patch.object(tr, "NUDGE_MAX_BYTES", os.path.getsize(s) - 1):
            self.assertIsNone(sb.spend_line(self.proj))
        self.assertEqual(self.spawned, [])
        self.assertFalse(Path(str(self.cache()) + ".lock").exists())
        sb.spend_line(self.proj)  # at the cap: allowed
        self.assertEqual(len(self.spawned), 1)

    def test_cached_line_expires_after_14_days(self):
        self.fill()
        for days, want in ((13, "spend: [ctx-window] x"), (15, None)):
            t = time.time() - days * 86400
            os.utime(self.cache(), (t, t))
            self.assertEqual(sb.spend_line(self.proj), want, days)
        self.assertEqual(self.spawned, [])  # same key: the expiry alone mutes it

    def test_a_new_day_refreshes_but_keeps_the_line_while_settings_are_unchanged(self):
        self.fill(key_edit={"d": "2000-01-01"})
        self.assertEqual(sb.spend_line(self.proj), "spend: [ctx-window] x")
        self.assertEqual(len(self.spawned), 1)

    def test_a_negative_cache_hit_prints_nothing_and_spawns_nothing(self):
        self.fill(line="")
        self.assertIsNone(sb.spend_line(self.proj))
        self.assertEqual(self.spawned, [])

    def test_brief_is_empty_when_the_policy_is_off(self):
        self.fill()
        for name in ("merge_line", "version_line", "committed_line", "hygiene_line", "priority_line", "drift_line"):
            p = mock.patch.object(sb, name, lambda repo: None)
            p.start()
            self.addCleanup(p.stop)
        self.assertEqual(sb.brief(self.proj), ["spend: [ctx-window] x"])
        (self.proj / ".perun").mkdir()
        (self.proj / ".perun" / "policy.json").write_text('{"spend_nudge": "off"}')
        self.assertEqual(sb.brief(self.proj), [])

    def test_spend_line_follows_priority_and_yields_to_the_cap(self):
        self.stub_sections(hygiene_line="hyg", priority_line="pri", spend_line="spend", drift_line="Perun copies differ: d")
        self.assertEqual(sb.brief(self.proj), ["hyg", "pri", "Perun copies differ: d"])  # drift keeps its slot, spend is cut first
        self.stub_sections(priority_line="pri", spend_line="spend")
        self.assertEqual(sb.brief(self.proj), ["pri", "spend"])
        self.stub_sections(merge_line="m", version_line="v", priority_line="pri", spend_line="spend")
        self.assertEqual(sb.brief(self.proj), ["m", "v", "pri"])

    def test_bad_policy_value_is_rejected(self):
        import perun_policy
        with self.assertRaises(ValueError):
            perun_policy.validate({"spend_nudge": "maybe"})
        self.assertEqual(perun_policy.validate({})["spend_nudge"], "on")

    def test_no_transcript_no_line(self):
        self.assertIsNone(sb.spend_line(self.proj))
        self.assertEqual(self.spawned, [])

    def test_refresh_writes_the_cache_the_hook_then_reads(self):
        s = self.transcript(firing())
        key = tr.nudge_key(s, str(self.proj))
        tr.write_nudge_cache(str(self.dir / "cache" / "perun" / "c.json"), key, tr.nudge(s, str(self.proj)))
        got = json.loads((self.dir / "cache" / "perun" / "c.json").read_text())
        self.assertEqual(got["key"], json.loads(json.dumps(key)))
        self.assertTrue(got["line"].startswith("spend: [ctx-window]"))


if __name__ == "__main__":
    unittest.main()
