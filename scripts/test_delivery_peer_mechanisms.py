#!/usr/bin/env python3
"""Tests for host_installer.py (+ watchdog alarm, auto-update wiring), peer_ack.py (on the board ACK), the P0-recurrence WIP exemption and pregate_parity.py.
Synthetic fixtures only; reuses the throwaway origin and fake `gh` of test_landing_watchdog.py."""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_landing_watchdog as base  # noqa: E402

SC = base.SC
sys.path.insert(0, str(SC))
import board_common as bc  # noqa: E402
import board_post as bpost  # noqa: E402
import host_installer as hi  # noqa: E402
import peer_ack as pa  # noqa: E402
import pregate_parity as pg  # noqa: E402

lw, pp = base.lw, base.pp
HOUR = 3600


class Installer(base.Base):
    def setUp(self):
        super().setUp()
        os.environ["PERUN_LANDING_DIR"] = str(self.tmp / "state")
        self.addCleanup(os.environ.pop, "PERUN_LANDING_DIR", None)
        self.addCleanup(os.environ.pop, "PERUN_POLICY", None)

    def test_announce_prints_owner_line_and_keeps_first_time(self):
        self.assertEqual(hi.announce("global-rules", "/opt/my repo", now=1000), "! bash '/opt/my repo/install.sh' --global-rules")
        hi.announce("global-rules", "/other", now=9999)
        self.assertEqual(hi.read()["global-rules"]["utc"], "1970-01-01T00:16:40Z")

    def test_only_fixed_installers(self):
        with self.assertRaises(KeyError):
            hi.announce("rm -rf x", "/r")
        self.assertEqual(hi.main(["x", "announce", "evil", "/r"]), 2)

    def test_alarm_after_limit_only(self):
        hi.announce("global-rules", "/r", now=time.time() - 5 * HOUR)
        self.assertIsNone(hi.alarm(0))
        self.assertIsNone(hi.alarm(6))
        line = hi.alarm(4)
        self.assertIn("Installer unapplied: global-rules merged 5.0 h ago (limit 4 h)", line)
        self.assertTrue(line.endswith("! bash /r/install.sh --global-rules"))

    def test_applied_clears_alarm_and_reannounce_restarts(self):
        hi.announce("global-rules", "/r", now=time.time() - 9 * HOUR)
        self.assertTrue(hi.applied("global-rules"))
        self.assertIsNone(hi.alarm(1))
        hi.announce("global-rules", "/r")
        self.assertIsNone(hi.alarm(1))
        self.assertFalse(hi.applied("nope"))

    def test_corrupt_state_alarms_and_is_quarantined(self):
        Path(hi.path()).write_text("{torn")
        self.assertIn("Installer state unreadable", hi.alarm(1))
        self.assertIsNone(hi.alarm(0))
        hi.announce("global-rules", "/r", now=1234)
        self.assertEqual(Path(hi.path() + ".corrupt.1234").read_text(), "{torn")
        self.assertIn("global-rules", hi.read())
        self.assertEqual(hi.main(["x", "list"]), 0)
        Path(hi.path()).write_text("[1]")
        self.assertEqual(hi.main(["x", "list"]), 1)

    def test_watchdog_emits_installer_line_from_policy(self):
        hi.announce("global-rules", "/r", now=time.time() - 9 * HOUR)
        pol = self.tmp / "policy.json"
        pol.write_text(json.dumps({"installer_unapplied_h": 2}))
        os.environ["PERUN_POLICY"] = str(pol)
        self.assertIn("Installer unapplied: global-rules", lw._installer(str(self.repo)))
        pol.write_text("{}")
        self.assertIsNone(lw._installer(str(self.repo)))

    def test_policy_key_validates(self):
        self.assertEqual(pp.validate({})["installer_unapplied_h"], 0)
        self.assertEqual(pp.validate({"installer_unapplied_h": 6})["installer_unapplied_h"], 6)
        for bad in (True, "6", -1):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pp.validate({"installer_unapplied_h": bad})

    def test_auto_update_announces_when_rules_differ(self):
        import perun_auto_update as au
        home, src = self.tmp / "home", self.tmp / "src"
        rules, scripts = home / ".claude/perun-rules", src / ".claude/skills/agentic-delivery/scripts"
        rules.mkdir(parents=True)
        scripts.mkdir(parents=True)
        (rules / "reply_cap.py").write_text("old")
        (scripts / "reply_cap.py").write_text("new")
        with mock.patch.object(Path, "home", return_value=home), mock.patch.object(au, "log") as log:
            au.announce_rules(src, self.tmp)
            self.assertIn("owner runs: ! bash ", log.call_args[0][1])
            self.assertIn("global-rules", hi.read())
            (rules / "reply_cap.py").write_text("new")
            hi.applied("global-rules")
            log.reset_mock()
            au.announce_rules(src, self.tmp)
            log.assert_not_called()


def comment(cid, agent, kind, tok, ts, extra=""):
    return bc.make_comment(cid, f"[agent:{agent}] {kind} refs:#1{extra} token:{tok}\nbody\n", ts)


class PeerAck(unittest.TestCase):
    T0, NOW = "2026-01-01T00:00:00Z", bc.parse_ts("2026-01-01T00:20:00Z").timestamp()

    def late(self, comments, after=600):
        return pa.undelivered(comments, after, self.NOW)

    def test_unacked_old_directive_is_undelivered(self):
        d = comment(1, "lead", "HANDOFF", "aaaa1111", self.T0, " to:lane-b")
        self.assertEqual([p["fields"]["token"] for p in self.late([d])], ["aaaa1111"])
        self.assertEqual(self.late([d], after=1800), [])

    def test_ack_by_recipient_delivers(self):
        d = comment(1, "lead", "HANDOFF", "aaaa1111", self.T0, " to:lane-b")
        self.assertEqual(self.late([d, comment(2, "lane-b", "ACK", "aaaa1111", self.T0)]), [])

    def test_ack_by_someone_else_or_wrong_token_does_not(self):
        d = comment(1, "lead", "HANDOFF", "aaaa1111", self.T0, " to:lane-b")
        self.assertEqual(len(self.late([d, comment(2, "lead", "ACK", "aaaa1111", self.T0)])), 1)
        self.assertEqual(len(self.late([d, comment(2, "lane-b", "ACK", "bbbb2222", self.T0)])), 1)

    def test_broadcast_directive_any_ack(self):
        d = comment(1, "lead", "DECISION", "aaaa1111", self.T0)
        self.assertEqual(self.late([d, comment(2, "lane-c", "ACK", "aaaa1111", self.T0)]), [])

    def test_ack_grammar(self):
        self.assertTrue(bc.validate_post("ACK", "-", {}))  # no token: still chatter
        self.assertEqual(bc.validate_post("ACK", "-", {"token": "aaaa1111"}), [])
        self.assertTrue(bc.validate_post("ACK", "-", {"token": "zz"}))
        self.assertTrue(bc.validate_post("CLAIM", "#1", {"token": "aaaa1111"}))

    def test_board_post_accepts_token_ack(self):
        body = Path(os.environ.get("TMPDIR", "/tmp")) / f"ack-{os.getpid()}.txt"
        body.write_text("Directive received.")
        self.addCleanup(lambda: [os.path.exists(f) and os.remove(f) for f in (body, f"{body}.post")])
        args = ["--repo", "o/r", "--issue", "1", "--agent", "lane-b", "--type", "ACK", "--token", "aaaa1111", "--body-file", str(body)]
        out = type("O", (), {"write": lambda *_: None})()
        self.assertEqual(bpost.run(args, bc.FakeGh(), out), 0)
        self.assertEqual(bpost.run(args[:-4] + ["--body-file", str(body)], bc.FakeGh(), out), 1)  # no token: rejected as chatter

    def run_cli(self, fake, *a):
        return pa.main(["undelivered", "--repo", "o/r", "--issue", "1", *a], fake, self.NOW)

    def test_cli_fails_closed(self):
        fake = bc.FakeGh([comment(1, "lead", "DECISION", "aaaa1111", self.T0)])
        self.assertEqual(self.run_cli(fake), 1)
        fake.comments.append(comment(2, "lane-c", "ACK", "aaaa1111", self.T0))
        self.assertEqual(self.run_cli(fake), 0)
        fake.fail = True
        self.assertEqual(self.run_cli(fake), 1)  # outage = undelivered
        self.assertEqual(pa.main(["undelivered", "--repo", "o/r", "--issue", "1"], lambda a, cwd=None: (0, "[{torn", ""), self.NOW), 1)
        self.assertEqual(pa.main(["undelivered", "--repo", "o/r", "--issue", "1"], lambda a, cwd=None: (0, '[{"x": 1}]', ""), self.NOW), 1)

    def test_new_token_is_valid(self):
        with mock.patch("builtins.print") as pr:
            self.assertEqual(pa.main(["new"]), 0)
        self.assertRegex(pr.call_args[0][0], bc.FIELD_RULES["token"].pattern)

    def test_bad_args_exit_2(self):
        for argv in ([], ["undelivered"], ["undelivered", "--repo", "bad", "--issue", "1"], ["undelivered", "--repo", "o/r", "--issue", "0"], ["nope"]):
            with self.subTest(argv=argv), mock.patch("sys.stderr"):
                self.assertEqual(pa.main(argv, bc.FakeGh(), self.NOW), 2)


class WipExemption(base.Base):
    NOW = time.time()

    def probe_n(self, prs, reopened=None):
        self.commit(minutes_ago=10)
        self.push()
        self.set_prs(prs)
        with mock.patch.object(lw, "reopened_at", side_effect=reopened or (lambda cwd, n: time.time() - HOUR)) as m:
            self.calls = m.call_args_list
            return lw.probe(str(self.repo), 60)[3]

    def p0(self, n=42, **kw):
        return {**base.GREEN, "labels": [{"name": "p0-recurrence"}], "body": f"Fix.\n\nFixes: #{n}", **kw}

    def test_one_verified_recurrence_is_exempt(self):
        self.assertEqual(self.probe_n([base.GREEN, base.GREEN, self.p0()]), 2)
        self.assertEqual(self.calls[0][0][1], 42)

    def test_at_most_one_extra(self):
        self.assertEqual(self.probe_n([base.GREEN, self.p0(1), self.p0(2), self.p0(3)]), 3)

    def test_needs_label_and_numeric_trailer(self):
        for bad in (self.p0(labels=[]), self.p0(body="Fixes #42"), self.p0(body="no trailer"), self.p0(body="Fixes: #abc"), self.p0(body="Fixes: #")):
            with self.subTest(bad=bad):
                self.assertEqual(self.probe_n([bad]), 1)
                self.assertEqual(self.calls, [])  # never even asks gh
        self.assertEqual(self.probe_n([self.p0(isDraft=True)]), 0)

    def test_unverified_or_expired_or_gh_down_counts_normally(self):
        self.assertEqual(self.probe_n([self.p0()], lambda c, n: None), 1)  # not reopened
        self.assertEqual(self.probe_n([self.p0()], lambda c, n: time.time() - 25 * HOUR), 1)  # reopen older than 24 h
        def boom(c, n):
            raise RuntimeError("gh down")
        self.assertEqual(self.probe_n([self.p0()], boom), 1)  # fail closed

    def test_reopened_at_reads_events(self):
        ev = lambda *e: json.dumps([{"event": k, "created_at": t} for k, t in e])
        for events, want in ((ev(("closed", "2026-01-01T00:00:00Z"), ("reopened", "2026-01-02T00:00:00Z")), lw._ts("2026-01-02T00:00:00Z")),
                             (ev(("reopened", "2026-01-02T00:00:00Z"), ("closed", "2026-01-03T00:00:00Z")), None), (ev(), None)):
            with mock.patch.object(lw, "_run", return_value=events):
                self.assertEqual(lw.reopened_at(".", 7), want)


class Pregate(unittest.TestCase):
    def rows(self, n, fast=True):
        return [{"sha": f"c{i}", "gate_failed": True, "fast_failed": fast} for i in range(n)]

    def test_five_matches_allow(self):
        self.assertTrue(pg.verdict(self.rows(5))[0])

    def test_four_unproven(self):
        ok, why = pg.verdict(self.rows(4))
        self.assertFalse(ok)
        self.assertIn("4 of 5", why)

    def test_one_miss_blocks_even_if_a_later_row_agrees(self):
        miss = {"sha": "bad", "gate_failed": True, "fast_failed": False}
        self.assertFalse(pg.verdict(self.rows(6) + [miss])[0])
        self.assertFalse(pg.verdict(self.rows(6) + [miss, {"sha": "bad", "gate_failed": True, "fast_failed": True}])[0])
        self.assertFalse(pg.verdict([miss, {"sha": "bad", "gate_failed": False, "fast_failed": False}] + self.rows(6))[0])

    def test_passing_commits_and_duplicates_do_not_count(self):
        rows = self.rows(4) + [{"sha": "g", "gate_failed": False, "fast_failed": False}] + self.rows(4)
        self.assertFalse(pg.verdict(rows)[0])

    def test_record_and_cli(self):
        led = os.path.join(os.environ.get("TMPDIR", "/tmp"), f"pg-{os.getpid()}.jsonl")
        self.addCleanup(lambda: os.path.exists(led) and os.remove(led))
        for i in range(5):
            self.assertEqual(pg.main(["x", "record", led, f"c{i}", "1", "1"]), 0)
        run = lambda *a: subprocess.run([sys.executable, str(SC / "pregate_parity.py"), *a], capture_output=True, text=True)
        r = run("check", led)
        self.assertEqual((r.returncode, "authoritative gate still runs" in r.stdout), (0, True))
        self.assertEqual(run("check", led, "--min", "6").returncode, 1)
        self.assertEqual(run("check", "/nonexistent").returncode, 2)
        self.assertEqual(pg.main(["x", "record", led, "bad", "1", "0"]), 0)
        self.assertEqual(run("check", led).returncode, 1)
        self.assertEqual(run("record", led, "x", "2", "1").returncode, 2)


if __name__ == "__main__":
    unittest.main()
