#!/usr/bin/env python3
"""Tests for spend_hub.py: ccusage when installed, token_report fallback, savings levers and the tier exposure.

Hermetic: the frozen synthetic fixture under docs/bench/token-levers is copied into a temp projects dir (lane requestIds made unique,
as real ones are), extra sessions are generated synthetic lines, and `ccusage` is a shell shim that prints the documented JSON shape.
No real transcript, real settings file or real ccusage is read.
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ".claude/skills/agentic-ceo/scripts"))
import spend_hub as hub  # noqa: E402
import token_report as tr  # noqa: E402

FIX = ROOT / "docs/bench/token-levers"
SINCE = datetime(2000, 1, 1, tzinfo=timezone.utc)
NO_SETTINGS = ({}, {}, set(), [])
UNPRICED = "acme-unpriced-1"  # a model id with no rate row
DAILY = {"daily": [{"date": "2026-01-01", "totalCost": 7.5, "modelBreakdowns": [{"modelName": "claude-opus-5-5", "cost": 7.5}]}],
         "totals": {"totalCost": 7.5}}
SHIM = """#!/bin/sh
case "$*" in
  *--instances*) echo '{"projects": {"acme-app": [{"date": "2026-01-01", "totalCost": 7.5}]}, "totals": {"totalCost": 7.5}}' ;;
  *) echo '%s' ;;
esac
"""


def projects_dir(tmp: Path) -> Path:
    """projects/p1/s1.jsonl plus s1/subagents/*: the fixture with each lane's requestIds prefixed by its file name."""
    p = tmp / "projects" / "p1"
    p.mkdir(parents=True)
    shutil.copy(FIX / "session.jsonl", p / "s1.jsonl")
    (p / "s1/subagents").mkdir(parents=True)
    for f in (FIX / "session/subagents").iterdir():
        text = f.read_text().replace('"requestId": "', f'"requestId": "{f.stem}-')
        (p / "s1/subagents" / f.name).write_text(text)
    return tmp / "projects"


def synth(model: str, n: int, tag: str) -> str:
    """n synthetic assistant lines on `model` with unique requestIds (the fixture's line shape, placeholder text only)."""
    usage = {"input_tokens": 1000, "output_tokens": 1000, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    return "".join(json.dumps({"type": "assistant", "isSidechain": False, "requestId": f"{tag}{i}", "timestamp": f"2026-01-01T00:0{i}:00Z",
                               "message": {"model": model, "stop_reason": "end_turn", "content": [{"type": "text", "text": "synthetic"}],
                                           "usage": usage}}) + "\n" for i in range(n))


def add(projects, rel: str, text: str) -> None:
    """Write `text` to <projects>/<rel> (for example p2/s2.jsonl), creating the project dir."""
    f = Path(projects) / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)


def shim(tmp: Path, body: str = SHIM % json.dumps(DAILY)) -> Path:
    bindir = tmp / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / "ccusage"
    exe.write_text(body)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe


def report(projects, settings=NO_SETTINGS, top=5, limit=20, exe=None, **kw) -> dict:
    """hub.build with the settings layer and the home dir pinned, so no real settings file or environment decides a lever's state."""
    with mock.patch.object(tr, "load_settings", return_value=settings), mock.patch.object(tr, "user_config_dir", return_value="/nowhere"):
        return hub.build(str(projects), SINCE, top, limit, exe, **kw)


class TmpCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class Waste(TmpCase):
    def setUp(self):
        super().setUp()
        self.projects = str(projects_dir(self.tmp))

    def test_fixture_levers_ranked_with_share_and_change(self):
        w = report(self.projects)["waste"]
        self.assertEqual([r["lever"] for r in w["levers"]], ["pin main cache", "lower LANE_TOOL_CAP", "auto-compact"])
        self.assertEqual([round(r["share"], 3) for r in w["levers"]], [0.353, 0.131, 0.060])
        self.assertIn('"promptCacheTtl": "1h"', w["levers"][0]["change"])
        self.assertIn("LANE_TOOL_CAP", w["levers"][1]["change"])
        self.assertEqual({r["state"] for r in w["levers"]}, {"unset"})
        self.assertEqual((w["measured"], w["skipped_over_cap"], w["spend_coverage"]), (1, 0, 1.0))
        self.assertGreater(w["subagent_share"], 0.0)

    def test_tier_is_an_exposure_apart_from_the_savings(self):
        r = report(self.projects)
        e = r["waste"]["exposure"]
        self.assertEqual((e["kind"], e["lever"]), ("exposure (not a saving, not additive)", "orchestrator tier"))
        self.assertAlmostEqual(e["share"], 0.6955, places=3)
        self.assertNotIn("orchestrator tier", [x["lever"] for x in r["waste"]["levers"]])
        lines = hub.render(r).splitlines()
        self.assertEqual([x for x in lines if "orchestrator tier" in x], [lines[-1]])  # one line, after the savings, never numbered
        self.assertTrue(lines[-1].startswith("exposure (not a saving, not additive): 69."))
        self.assertIn("they overlap, so do not add them", "\n".join(lines))

    def test_set_lever_is_skipped_and_named(self):
        w = report(self.projects, settings=({"promptCacheTtl": "1h"}, {}, set(), []))["waste"]
        self.assertNotIn("pin main cache", [r["lever"] for r in w["levers"]])
        self.assertEqual(w["already_set"], ["pin main cache"])

    def test_oversize_transcript_is_counted_not_measured(self):
        w = report(self.projects, max_bytes=1)["waste"]
        self.assertEqual((w["measured"], w["skipped_over_cap"], w["levers"], w["exposure"], w["spend_coverage"]), (0, 1, [], None, 0.0))

    def test_lane_bytes_count_toward_the_cap(self):
        main = Path(self.projects) / "p1/s1.jsonl"
        total = main.stat().st_size + sum(f.stat().st_size for f in (Path(self.projects) / "p1/s1/subagents").glob("*.jsonl"))
        self.assertGreater(total, main.stat().st_size)
        self.assertEqual(hub.transcript_bytes(str(main)), total)
        for cap, measured in ((total, 1), (total - 1, 0), (main.stat().st_size + 1, 0)):  # a cap on the main file alone would measure the last two
            self.assertEqual(report(self.projects, max_bytes=cap)["waste"]["measured"], measured, cap)

    def test_top_limits_levers(self):
        self.assertEqual(len(report(self.projects, top=2)["waste"]["levers"]), 2)

    def test_fallback_spend_by_day_project_model_session(self):
        r = report(self.projects)
        sp = r["spend"]
        self.assertEqual(sp["source"], "token_report.py")
        self.assertEqual([k for k, *_ in sp["projects"]], ["p1"])
        self.assertEqual(sorted(k for k, *_ in sp["models"]), ["claude-opus-5-5", "claude-sonnet-5-5"])
        self.assertEqual([k for k, *_ in sp["days"]], ["2026-01-01"])
        self.assertAlmostEqual(sp["days"][0][1], sp["total_usd"], places=3)  # day buckets stay unrounded, the total is 4 dp
        self.assertAlmostEqual(sp["total_usd"], 11.13, places=2)  # the fixture's documented total (docs/bench/token-levers/README.md)
        self.assertEqual(r["sessions"][0]["session"], "s1")
        out = hub.render(r)
        self.assertIn("by session (USD, unpriced last): s1 $", out)
        self.assertFalse(r["lower_bound"])
        for note in ("unpriced:", "unreadable:", "lower bound"):  # a clean corpus carries no caveat
            self.assertNotIn(note, out)


class Mixed(TmpCase):
    """The fixture session plus p2 (a model with no rate row, more raw tokens than p3), p3 (small, priced) and p4 (not JSON)."""

    def setUp(self):
        super().setUp()
        self.projects = str(projects_dir(self.tmp))
        add(self.projects, "p2/s2.jsonl", synth(UNPRICED, 3, "u"))
        add(self.projects, "p3/s3.jsonl", synth("claude-sonnet-5-5", 2, "v"))
        add(self.projects, "p4/s4.jsonl", "not json\n")
        self.rep = report(self.projects)

    def test_unpriced_model_stays_none_and_the_total_is_a_lower_bound(self):
        r, sp = self.rep, self.rep["spend"]
        self.assertEqual(r["unpriced"], [UNPRICED])
        self.assertIsNone({k: u for k, u, _ in sp["models"]}[UNPRICED])
        self.assertEqual({k: (u, miss) for k, u, miss in sp["projects"]}["p2"], (None, [UNPRICED]))
        priced = sum(s["usd"] for s in r["sessions"] if s["usd"] is not None)
        self.assertAlmostEqual(sp["total_usd"], priced, places=3)  # the total prices the rest only, the gap is not summed as 0
        self.assertTrue(r["lower_bound"])
        out = hub.render(r)
        for want in (f"unpriced: {UNPRICED}", "total is a lower bound", f"{UNPRICED} UNPRICED", "p2 UNPRICED", f"+ UNPRICED ({UNPRICED})"):
            self.assertIn(want, out)
        self.assertNotIn("$0.00", out)

    def test_unreadable_session_is_counted_and_flagged(self):
        self.assertEqual(self.rep["unreadable"], {"sessions": 1, "lanes": 0})
        self.assertIn("unreadable: 1 sessions", hub.render(self.rep))
        only = projects_dir(self.tmp / "only")  # nothing unpriced: the unreadable transcript alone makes the total a lower bound
        add(only, "p4/s4.jsonl", "not json\n")
        r = report(only)
        out = hub.render(r)
        self.assertEqual((r["unpriced"], r["unreadable"]["sessions"], r["lower_bound"]), ([], 1, True))
        self.assertIn("unreadable: 1 sessions", out)
        self.assertIn("total is a lower bound", out)
        self.assertNotIn("unpriced:", out)

    def test_sessions_ranked_by_usd_unpriced_last_and_flagged(self):
        s = self.rep["sessions"]
        self.assertEqual([x["session"] for x in s], ["s1", "s3", "s2"])  # by raw tokens s2 would beat s3
        self.assertGreater(s[0]["usd"], s[1]["usd"])
        self.assertEqual((s[2]["usd"], s[2]["unpriced"]), (None, [UNPRICED]))
        line = next(x for x in hub.render(self.rep).splitlines() if x.startswith("by session"))
        self.assertTrue(line.endswith("s2 UNPRICED"), line)

    def test_waste_scan_takes_the_biggest_sessions_by_usd(self):
        w = self.rep["waste"]
        self.assertEqual((w["measured"], w["skipped_over_cap"]), (3, 0))
        # two sessions: s1 and s3 by USD (all the priced spend); by raw tokens it would be s1 and the unpriced s2
        self.assertEqual(report(self.projects, limit=2)["waste"]["spend_coverage"], 1.0)

    def test_transcripts_stay_read_only(self):
        def snapshot():
            return [(str(f), f.stat().st_size, f.stat().st_mtime_ns, hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() else "")
                    for f in sorted(Path(self.projects).rglob("*"))]
        before = snapshot()
        report(self.projects)
        with mock.patch.object(tr, "load_settings", return_value=NO_SETTINGS), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(hub.main(["--projects", self.projects, "--since", "2000-01-01", "--json"]), 0)
        self.assertEqual(snapshot(), before)


class UserSettings(TmpCase):
    """Lever state comes from the user layer and env through the real tr.load_settings (CLAUDE_CONFIG_DIR is a temp dir)."""

    def setUp(self):
        super().setUp()
        self.projects = str(projects_dir(self.tmp))
        self.cfg = self.tmp / "cfg"
        self.cfg.mkdir()
        env = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.cfg)})
        env.start()
        self.addCleanup(env.stop)
        for names in tr.LEVER_KEYS.values():
            for n in names:
                os.environ.pop(n, None)

    def rep(self) -> dict:
        return hub.build(self.projects, SINCE, 5, 20, None)

    def test_user_settings_key_or_env_skips_the_lever(self):
        (self.cfg / "settings.json").write_text('{"promptCacheTtl": "1h"}')
        os.environ["LANE_TOOL_CAP"] = "40"
        w = self.rep()["waste"]
        self.assertEqual([r["lever"] for r in w["levers"]], ["auto-compact"])
        self.assertEqual(w["already_set"], ["lower LANE_TOOL_CAP", "pin main cache"])

    def test_project_settings_in_the_cwd_do_not_mute_levers(self):
        cwd = self.tmp / "cwd"
        (cwd / ".claude").mkdir(parents=True)
        (cwd / ".claude/settings.json").write_text('{"promptCacheTtl": "1h"}')
        old = os.getcwd()
        os.chdir(cwd)
        try:
            w = self.rep()["waste"]
        finally:
            os.chdir(old)
        self.assertEqual(w["already_set"], [])
        self.assertIn("pin main cache", [r["lever"] for r in w["levers"]])
        self.assertEqual({r["state"] for r in w["levers"]}, {"unset"})

    def test_unreadable_user_settings_are_unknown_not_set(self):
        (self.cfg / "settings.json").write_text("{not json")
        r = self.rep()
        self.assertEqual(r["waste"]["already_set"], [])
        self.assertEqual([x["state"] for x in r["waste"]["levers"]], ["unknown"] * 3)
        out = hub.render(r)
        self.assertEqual(out.count("[state unknown: user settings unreadable]"), 3)
        self.assertNotIn("already set", out)


class Ccusage(TmpCase):
    def test_documented_shape_is_parsed(self):
        cc = hub.ccusage_spend(str(shim(self.tmp)), SINCE)
        self.assertEqual((cc["source"], cc["total_usd"], cc["projects"], cc["models"]),
                         ("ccusage", 7.5, [["acme-app", 7.5, []]], [["claude-opus-5-5", 7.5, []]]))
        self.assertEqual(cc["days"], [["2026-01-01", 7.5, []]])

    def test_wrong_shape_or_failure_gives_none(self):
        self.assertIsNone(hub.ccusage_spend(str(shim(self.tmp, "#!/bin/sh\necho '{\"x\": 1}'\n")), SINCE))
        self.assertIsNone(hub.ccusage_spend(str(shim(self.tmp, "#!/bin/sh\necho 'not json'\n")), SINCE))
        self.assertIsNone(hub.ccusage_spend(str(shim(self.tmp, "#!/bin/sh\nexit 3\n")), SINCE))
        self.assertIsNone(hub.ccusage_spend(str(self.tmp / "missing"), SINCE))

    def test_build_prefers_ccusage_and_reports_drift_else_note(self):
        projects = projects_dir(self.tmp)
        ok = report(projects, exe=str(shim(self.tmp)))
        bad = report(projects, exe=str(shim(self.tmp, "#!/bin/sh\nexit 3\n")))
        self.assertEqual(ok["spend"]["source"], "ccusage")
        self.assertIn("drift_pct", ok)
        self.assertIn("parity: ccusage vs token_report.py", hub.render(ok))
        self.assertEqual(bad["spend"]["source"], "token_report.py")
        self.assertIn("used token_report.py", bad["note"])

    def test_lower_bound_own_total_skips_the_parity_line(self):
        projects = projects_dir(self.tmp)
        add(projects, "p2/s2.jsonl", synth(UNPRICED, 1, "u"))
        r = report(projects, exe=str(shim(self.tmp)))
        out = hub.render(r)
        self.assertEqual(r["spend"]["source"], "ccusage")
        self.assertNotIn("drift_pct", r)
        self.assertNotIn("parity: ccusage vs token_report.py", out)
        self.assertIn("parity: not comparable", out)
        self.assertIn(f"unpriced: {UNPRICED}", out)

    def test_cli_uses_path_ccusage_only_on_default_dir(self):
        home = self.tmp / "home"
        projects_dir(home / ".claude")  # the default projects dir: <home>/.claude/projects
        shim(self.tmp)
        env = {"HOME": str(home), "PATH": f"{self.tmp / 'bin'}{os.pathsep}{os.environ['PATH']}"}
        argv = ["--since", "2000-01-01"]
        with mock.patch.dict(os.environ, env), mock.patch.object(tr, "load_settings", return_value=NO_SETTINGS):
            os.environ.pop("CLAUDE_CONFIG_DIR", None)
            run = lambda *a: self._run([*argv, *a])  # noqa: E731
            self.assertIn("source: ccusage", run()[1])
            self.assertIn("source: token_report.py", run("--no-ccusage")[1])
            self.assertIn("source: token_report.py", run("--projects", str(home / ".claude" / "projects"))[1])
            self.assertEqual(json.loads(run("--json")[1])["spend"]["source"], "ccusage")

    def test_cli_usage_errors(self):
        for argv in (["--projects", str(self.tmp / "none")], ["--since", "garbage", "--projects", str(self.tmp)],
                     ["--top", "0", "--projects", str(self.tmp)]):
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(self._run(argv)[0], 2)

    @staticmethod
    def _run(argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = hub.main(argv)
        return rc, out.getvalue()


if __name__ == "__main__":
    unittest.main()
