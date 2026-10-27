#!/usr/bin/env python3
"""Tests for perun_policy.py, host_probe policy wiring, and share_learning.py (gh is a stub). Offline."""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AD = ROOT / ".claude/skills/agentic-delivery/scripts"
CT = ROOT / ".claude/skills/contribution/scripts"
sys.path.insert(0, str(AD))
import perun_policy  # noqa: E402


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


class PolicyCli(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.pol = self.d / "p.json"
        self.env = {**os.environ, "PERUN_POLICY": str(self.pol)}

    def get(self, dim):
        return run([sys.executable, str(AD / "perun_policy.py"), "get", dim], env=self.env)

    def test_defaults_without_file(self):
        self.pol.write_text("{}")
        self.assertEqual(self.get("github_actions").stdout.strip(), "efficient")
        self.assertEqual(self.get("share_learnings").stdout.strip(), "ask")

    def test_example_policy(self):
        self.pol.write_text('{"local_cpu": "maximize", "github_actions": "off"}')
        self.assertEqual(self.get("github_actions").stdout.strip(), "off")
        self.assertEqual(self.get("local_cpu").stdout.strip(), "maximize")
        self.assertEqual(self.get("tokens").stdout.strip(), "efficient")

    def test_explicit_missing_policy_fails_closed(self):
        self.assertEqual(self.get("github_actions").returncode, 2)  # PERUN_POLICY points at an absent file

    def test_host_probe_notes_default_lane_cap(self):
        self.pol.write_text("{}")
        r = run([sys.executable, str(AD / "host_probe.py"), "--live-lanes", "0", "--sample-interval", "0"], env=self.env)
        self.assertIn("lane cap", r.stderr)
        self.assertNotIn("lane cap", r.stdout)

    def test_malformed_fails_closed(self):
        self.pol.write_text('{"tokens": "lots"}')
        r = self.get("tokens")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.get("nonsense").returncode, 2)

    def test_lanes(self):
        self.assertEqual(perun_policy.lanes("maximize", 10, 4.0), 6)
        self.assertEqual(perun_policy.lanes("maximize", 10, 50.0), 1)  # never past the load ceiling
        self.assertEqual(perun_policy.lanes("efficient", 10), 5)
        self.assertEqual(perun_policy.lanes(3, 10), 3)
        self.assertEqual(perun_policy.lanes("off", 10), 1)

    def test_heavy_slots_injected_load(self):
        self.assertEqual(perun_policy.heavy_slots(10, 4.0), 6)
        self.assertEqual(perun_policy.heavy_slots(10, 50.0), 2)  # floor of 2, never starves
        self.assertEqual(perun_policy.heavy_slots(1), 1)  # floor never exceeds the core count

    def test_heavy_admission_injected_load(self):
        import host_probe
        kw = dict(swap_samples=(1, 1), free_ram_pct=50, lane_type="heavy", cores=4)
        self.assertEqual(host_probe.decide(load1=5.0, **kw), "HOLD load-high")
        self.assertEqual(host_probe.decide(load1=1.0, **kw), "SPAWN")

    def test_host_probe_bad_policy_cannot_check(self):
        self.pol.write_text("{")
        r = run([sys.executable, str(AD / "host_probe.py")], env=self.env)
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stdout.startswith("COULD_NOT_CHECK policy"))


class ShareLearning(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / ".banlist.txt").write_text("Acme Capital\n")
        self.pol = self.d / "p.json"
        self.pol.write_text("{}")
        self.ledger = self.d / "ledger.jsonl"
        self.calls = self.d / "calls.log"
        gh = self.d / "gh"
        gh.write_text(f'#!/usr/bin/env bash\necho "$*" >>"{self.calls}"\n'
                      f'case "$2" in list) cat "{self.d}/existing.json";; create) echo https://example.com/i/9;; esac\n')
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR)
        (self.d / ".banlist.local.txt").write_text("# local\nZzzUnlikelyTerm\n")
        (self.d / "existing.json").write_text("[]")
        self.env = {**os.environ, "PERUN_POLICY": str(self.pol), "GH": str(gh), "BANLIST_DIR": str(self.d),
                    "PERUN_LEDGER": str(self.ledger), "PERUN_RATE_FILE": str(self.d / "rate")}

    def share(self, text, *extra):
        return run([sys.executable, str(CT / "share_learning.py"), "--text", text, *extra], env=self.env)

    def created(self):
        return self.calls.exists() and "issue create" in self.calls.read_text()

    def test_ask_default_holds_draft(self):
        r = self.share("Retry loops hide flaky gates")
        self.assertEqual(r.returncode, 3)
        self.assertFalse(self.calls.exists())

    def test_off_does_nothing(self):
        self.pol.write_text('{"share_learnings": "off"}')
        self.assertEqual(self.share("x lesson").returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_auto_generalizes_and_files(self):
        self.pol.write_text('{"share_learnings": "auto"}')
        r = self.share("Acme Capital repo foo/bar at /Users/jane/x mailed jane@example.com: gates drift", "--title", "Gates drift", "--send")
        self.assertEqual(r.returncode, 0, r.stderr)
        sent = self.calls.read_text()
        for leak in ("Acme", "foo/bar", "/Users/jane", "jane@example.com"):
            self.assertNotIn(leak, sent)
        self.assertIn("--repo protocol/perun", sent)
        rec = json.loads(self.ledger.read_text().splitlines()[-1])
        self.assertEqual((rec["status"], rec["url"]), ("created", "https://example.com/i/9"))
        self.assertNotIn("pr create", sent)

    def test_approve_without_tty_refused(self):
        self.assertEqual(self.share("Gates drift under load", "--approve").returncode, 3)
        self.assertFalse(self.created())

    def _approve_on_tty(self, answer):
        import pty
        master, slave = pty.openpty()
        os.write(master, answer.encode())
        p = subprocess.run([sys.executable, str(CT / "share_learning.py"), "--text", "Gates drift under load",
                            "--approve"], stdin=slave, capture_output=True, text=True, env=self.env)
        os.close(master)
        os.close(slave)
        return p

    def test_approve_on_tty_with_typed_yes_files(self):
        self.assertEqual(self._approve_on_tty("yes\n").returncode, 0)
        self.assertTrue(self.created())

    def test_approve_on_tty_wrong_answer_refused(self):
        self.assertEqual(self._approve_on_tty("no\n").returncode, 3)
        self.assertFalse(self.created())

    def test_other_repo_needs_allow_flag(self):
        self.pol.write_text('{"share_learnings": "auto"}')
        self.assertEqual(self.share("Gates drift", "--send", "--repo", "other/repo").returncode, 2)
        self.assertFalse(self.calls.exists())
        self.assertEqual(self.share("Gates drift", "--send", "--repo", "other/repo", "--allow-repo", "other/repo").returncode, 0)
        self.assertIn("--repo other/repo", self.calls.read_text())

    def test_auto_refused_without_local_banlist(self):
        self.pol.write_text('{"share_learnings": "auto"}')
        (self.d / ".banlist.local.txt").unlink()
        self.assertEqual(self.share("Gates drift", "--send").returncode, 2)
        self.assertFalse(self.calls.exists())

    def test_auto_is_dry_run_without_send(self):
        self.pol.write_text('{"share_learnings": "auto"}')
        r = self.share("Gates drift")
        self.assertEqual(r.returncode, 0)
        self.assertIn("dry run", r.stdout)
        self.assertFalse(self.calls.exists())

    def test_auto_rate_limited_to_three_per_day(self):
        self.pol.write_text('{"share_learnings": "auto"}')
        for i in range(3):
            self.assertEqual(self.share(f"Distinct lesson number {i} alpha{i * 7} beta{i * 3}", "--send").returncode, 0)
        r = self.share("Fourth lesson entirely different wording zeta", "--send")
        self.assertEqual(r.returncode, 2)
        self.assertIn("rate limit", r.stderr)
        self.assertEqual(self.calls.read_text().count("issue create"), 3)

    def test_footer_has_version_and_mode(self):
        self.pol.write_text('{"share_learnings": "auto"}')
        self.share("Gates drift", "--send")
        sent = self.calls.read_text()
        self.assertIn("Provenance: Perun", sent)
        self.assertIn("share_learnings=auto", sent)

    def test_paths_urls_and_long_code_stripped(self):
        self.pol.write_text('{"share_learnings": "auto"}')
        code = "\n".join(f"line{i}" for i in range(25))
        text = (f"See ./src/app/main.py and https://evil.test/x and /opt/srv/data plus\n```\n{code}\n```\n"
                "and short:\n```\na = 1\n```")
        r = self.share(text, "--title", "Stripping", "--send")
        self.assertEqual(r.returncode, 0, r.stderr)
        sent = self.calls.read_text()
        for leak in ("src/app", "evil.test", "/opt/srv", "line24"):
            self.assertNotIn(leak, sent)
        self.assertIn("a = 1", sent)

    def test_duplicate_open_or_closed_not_filed(self):
        self.pol.write_text('{"share_learnings": "auto"}')
        (self.d / "existing.json").write_text('[{"number": 4, "title": "Gates drift under load", "state": "CLOSED"}]')
        r = self.share("Gates drift under load now", "--send")
        self.assertEqual(r.returncode, 0)
        self.assertIn("duplicate of #4", r.stdout)
        self.assertFalse(self.created())
        self.assertEqual(json.loads(self.ledger.read_text().splitlines()[-1])["status"], "duplicate")

    def test_missing_banlist_fails_closed(self):
        self.pol.write_text('{"share_learnings": "auto"}')
        (self.d / ".banlist.txt").unlink()
        self.assertEqual(self.share("Gates drift", "--send").returncode, 2)
        self.assertFalse(self.created())

    def test_gh_list_failure_does_not_file(self):
        self.pol.write_text('{"share_learnings": "auto"}')
        (self.d / "existing.json").unlink()  # stub's `cat` fails
        self.assertEqual(self.share("Gates drift", "--send").returncode, 2)
        self.assertFalse(self.created())


class HeavyLease(unittest.TestCase):
    DEAD = 4194301  # fake pid, no such process

    def setUp(self):
        self.d = Path(tempfile.mkdtemp()) / "heavy"

    def put(self, pid, age=0):
        self.d.mkdir(parents=True, exist_ok=True)
        (self.d / str(pid)).write_text(f"{pid} {int(__import__('time').time()) - age}")

    def test_full_blocks_and_stale_ignored_not_deleted(self):
        self.put(os.getpid())
        self.put(self.DEAD)
        self.put(os.getppid(), age=3 * 3600)
        self.assertEqual(perun_policy.active_leases(self.d), [os.getpid()])
        self.assertFalse(perun_policy.heavy_acquire(self.d, 1, 999999))
        self.assertTrue(perun_policy.heavy_acquire(self.d, 2, 999999))
        self.assertTrue((self.d / str(self.DEAD)).exists())

    def test_release_idempotent(self):
        self.assertTrue(perun_policy.heavy_acquire(self.d, 1, os.getpid()))
        perun_policy.heavy_release(self.d, os.getpid())
        perun_policy.heavy_release(self.d, os.getpid())
        self.assertEqual(perun_policy.active_leases(self.d), [])

    def test_cli_acquire_release(self):
        (self.d.parent / "p.json").write_text("{}")
        env = {**os.environ, "PERUN_HEAVY_DIR": str(self.d), "PERUN_POLICY": str(self.d.parent / "p.json")}
        for _ in range(2):  # two CLI calls from this process share one parent pid: same lease
            r = run([sys.executable, str(AD / "perun_policy.py"), "heavy-acquire"], env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(list(self.d.iterdir())), 1)
        self.assertEqual(run([sys.executable, str(AD / "perun_policy.py"), "heavy-release"], env=env).returncode, 0)
        self.assertEqual(list(self.d.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
