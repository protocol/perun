#!/usr/bin/env python3
"""Tests for lane weighting in the heavy-lease registry (perun_policy.py) and the gates that read it
(heavy_gate.py, host_probe.py): a light lane (read-only or doc) holds a fraction of a slot, a heavy test lane
holds a whole one, and anything that cannot be classified counts as heavy.

Leases are real files owned by real live child processes (terminated in cleanup, own PIDs only); the process
table is injected, never read from `ps`. Run: python3 scripts/test_lane_weight.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SC = ROOT / ".claude/skills/agentic-delivery/scripts"
sys.dont_write_bytecode = True
sys.path.insert(0, str(SC))
import heavy_gate  # noqa: E402
import host_probe  # noqa: E402
import perun_policy as pp  # noqa: E402


class Fleet(unittest.TestCase):
    """A lease dir plus live child processes to own leases."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name) / "heavy"
        self.d.mkdir()
        self.kids = []
        self.addCleanup(self.reap)
        self.now = time.time()

    def reap(self):
        for k in self.kids:
            k.terminate()
            k.wait()

    def proc(self):
        """A live pid with no lease."""
        k = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        self.kids.append(k)
        return k.pid

    def lane(self, kind=None, age=0):
        """A live pid holding a lease `age` seconds old, declaring `kind` when given."""
        pid = self.proc()
        (self.d / str(pid)).write_text(f"{pid} {int(self.now - age)}" + (f" {kind}" if kind else ""))
        return pid


class Weights(unittest.TestCase):
    def test_declared_light_kinds_are_a_fraction_and_case_insensitive(self):
        for kind in ("light", "Light", "doc", "docs", "read-only", "readonly"):
            self.assertEqual(pp.lane_weight(kind, 0, None), pp.LIGHT_WEIGHT, kind)
        self.assertLess(pp.LIGHT_WEIGHT, 1)

    def test_any_other_declared_kind_is_heavy(self):
        for kind in ("heavy", "test", "cpu", "mystery"):
            self.assertEqual(pp.lane_weight(kind, 9999, 0.0), 1.0, kind)  # idle CPU never overrides a declaration

    def test_undeclared_lane_is_light_only_when_measured_idle_and_past_warmup(self):
        old = pp.WARMUP + 1
        self.assertEqual(pp.lane_weight(None, old, 3.0), pp.LIGHT_WEIGHT)
        self.assertEqual(pp.lane_weight(None, old, 90.0), 1.0)
        self.assertEqual(pp.lane_weight(None, old, pp.LIGHT_CPU_PCT), 1.0)  # the threshold itself is not light
        self.assertEqual(pp.lane_weight(None, pp.WARMUP - 1, 0.0), 1.0)  # a fresh lease: CPU has not ramped up yet

    def test_unmeasurable_lane_counts_as_heavy(self):
        self.assertEqual(pp.lane_weight(None, 9999, None), 1.0)

    def test_tree_cpu_sums_the_process_subtree_only(self):
        table = {1: (0, 0.0), 2: (1, 50.0), 3: (2, 25.0), 4: (1, 5.0), 9: (0, 99.0)}
        self.assertEqual(pp.tree_cpu(table, 1), 80.0)
        self.assertEqual(pp.tree_cpu(table, 2), 75.0)
        self.assertIsNone(pp.tree_cpu(table, 77))
        self.assertIsNone(pp.tree_cpu(None, 1))
        self.assertIsNone(pp.tree_cpu({}, 1))
        self.assertEqual(pp.tree_cpu({1: (2, 1.0), 2: (1, 1.0)}, 1), 2.0)  # a ppid cycle cannot loop forever


class ProcessTable(Fleet):
    """`_proc_table()` against a stub `ps` first on PATH, so the exact argv and column parsing are pinned
    without depending on the host's `ps` (which a sandbox may forbid)."""

    def with_ps(self, body):
        stub = Path(self.tmp.name) / "bin"
        stub.mkdir(exist_ok=True)
        (stub / "ps").write_text("#!/bin/sh\n" + body)
        (stub / "ps").chmod(0o755)
        old = os.environ["PATH"]
        os.environ["PATH"] = f"{stub}{os.pathsep}{old}"
        self.addCleanup(os.environ.__setitem__, "PATH", old)

    def test_parses_pid_ppid_pcpu_and_asks_for_exactly_those_columns(self):
        self.with_ps('[ "$*" = "-A -o pid=,ppid=,pcpu=" ] || exit 9\nprintf "    1     0   0.0\\n  100     1  12.5\\n  101   100  80.0\\n"\n')
        self.assertEqual(pp._proc_table(), {1: (0, 0.0), 100: (1, 12.5), 101: (100, 80.0)})

    def test_unparseable_or_failing_ps_is_none(self):
        self.with_ps('echo "garbage here"\n')
        self.assertIsNone(pp._proc_table())
        self.with_ps("exit 1\n")
        self.assertIsNone(pp._proc_table())  # a non-zero exit prints nothing parseable
        self.with_ps("")
        self.assertIsNone(pp._proc_table())

    def test_missing_ps_is_none(self):
        os.environ["PATH"], old = self.tmp.name, os.environ["PATH"]  # a PATH with no ps at all
        self.addCleanup(os.environ.__setitem__, "PATH", old)
        self.assertIsNone(pp._proc_table())

    def test_old_undeclared_leases_are_weighed_through_the_real_reader(self):
        busy, idle = self.lane(age=600), self.lane(age=600)
        self.with_ps(f'printf "{busy} 1 90.0\\n{idle} 1 2.0\\n"\n')
        self.assertEqual(pp.lease_load(self.d), 1.0 + pp.LIGHT_WEIGHT)

    def test_ps_is_not_called_when_no_lease_needs_measuring(self):
        self.lane("light")
        self.lane()  # undeclared but fresh: counts as heavy without a measurement
        marker = Path(self.tmp.name) / "ps-was-called"
        self.with_ps(f'touch "{marker}"\n')
        self.assertEqual(pp.lease_load(self.d), pp.LIGHT_WEIGHT + 1.0)
        self.assertFalse(marker.exists())
        self.lane(age=600)  # now one lease is old and undeclared: ps is read, once
        pp.lease_load(self.d)
        self.assertTrue(marker.exists())


class LeaseLoad(Fleet):
    def test_three_light_plus_one_heavy_weigh_one_and_three_quarters(self):
        for _ in range(3):
            self.lane("light")
        self.lane("heavy")
        self.assertEqual(len(pp.active_leases(self.d)), 4)  # the old count
        self.assertEqual(pp.lease_load(self.d), 1.75)

    def test_undeclared_fresh_leases_still_count_one_each(self):
        for _ in range(4):
            self.lane()
        self.assertEqual(pp.lease_load(self.d, table={}), 4.0)

    def test_old_undeclared_lease_is_weighed_by_measured_cpu(self):
        busy, idle, unknown = self.lane(age=600), self.lane(age=600), self.lane(age=600)
        table = {busy: (1, 80.0), idle: (1, 1.0)}
        self.assertEqual(pp.lease_load(self.d, table=table), 1.0 + pp.LIGHT_WEIGHT + 1.0)  # unknown pid: heavy
        self.assertIn(unknown, pp.active_leases(self.d))

    def test_unreadable_process_table_fails_closed(self):
        for _ in range(3):
            self.lane(age=600)
        real, pp._proc_table = pp._proc_table, lambda: None
        try:
            self.assertEqual(pp.lease_load(self.d), 3.0)
        finally:
            pp._proc_table = real

    def test_dead_expired_and_malformed_leases_weigh_nothing(self):
        self.lane("light")
        (self.d / "4194301").write_text(f"4194301 {int(self.now)} light")  # dead pid
        pid = self.proc()
        (self.d / str(pid)).write_text(f"{pid} {int(self.now - pp.LEASE_TTL - 5)} light")  # expired
        (self.d / "junk").write_text("not a lease")
        (self.d / "many").write_text(f"{os.getpid()} {int(self.now)} light extra")
        self.assertEqual(pp.lease_load(self.d), pp.LIGHT_WEIGHT)

    def test_exclude_drops_the_callers_own_lease(self):
        mine = self.lane("heavy")
        self.lane("light")
        self.assertEqual(pp.lease_load(self.d, exclude=mine), pp.LIGHT_WEIGHT)


class Acquire(Fleet):
    def test_light_lanes_fit_where_the_old_count_would_have_filled_the_slots(self):
        for _ in range(7):  # seven light lanes: 1.75 of 2 slots. Counted as heavy they would be 7 against 2.
            self.assertTrue(pp.heavy_acquire(self.d, 2, self.proc(), "light"))
        self.assertEqual(pp.lease_load(self.d), 1.75)
        self.assertFalse(pp.heavy_acquire(self.d, 1, self.proc()))  # a one-slot cap is full at 1.75
        self.assertTrue(pp.heavy_acquire(self.d, 2, self.proc()))  # 1.75 < 2: a heavy lane is admitted
        self.assertFalse(pp.heavy_acquire(self.d, 2, self.proc()))  # now 2.75 >= 2

    def test_heavy_lanes_fill_whole_slots_exactly_as_before(self):
        self.assertTrue(pp.heavy_acquire(self.d, 2, self.proc()))
        self.assertTrue(pp.heavy_acquire(self.d, 2, self.proc()))
        self.assertFalse(pp.heavy_acquire(self.d, 2, self.proc()))

    def test_lease_file_records_the_declared_kind(self):
        pp.heavy_acquire(self.d, 4, os.getpid(), "light")
        self.assertEqual((self.d / str(os.getpid())).read_text().split()[2], "light")

    def test_bad_kind_is_refused(self):
        for bad in ("li ght", "../x", "", "9", "a" * 17):
            with self.assertRaises(ValueError, msg=bad):
                pp.heavy_acquire(self.d, 4, os.getpid(), bad)


class Gate(Fleet):
    """The report fixture: 3 light lanes plus 1 heavy lane against a 4-slot host (load 4 of 8 cores)."""

    env = {"PERUN_GATE_LOAD1": "4", "PERUN_GATE_CORES": "8", "PERUN_GATE_FREE_RAM_PCT": "60"}

    def verdict(self):
        keys = (*self.env, "PERUN_HEAVY_DIR")
        old = {k: os.environ.get(k) for k in keys}
        os.environ.update(self.env, PERUN_HEAVY_DIR=str(self.d))
        try:
            return heavy_gate.verdict()[0]
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_three_light_plus_one_heavy_are_admitted(self):
        for _ in range(3):
            self.lane("light")
        self.lane("heavy")
        self.assertIsNone(self.verdict())  # 1.75 of 4 slots; counted one each it was 4 of 4: HOLD

    def test_four_heavy_lanes_still_hold_at_four_of_four(self):
        for _ in range(4):
            self.lane("heavy")
        self.assertEqual(self.verdict(), "HOLD heavy-lease-full 4/4")

    def test_hold_message_shows_the_fractional_load(self):
        for _ in range(3):
            self.lane("heavy")
        for _ in range(4):
            self.lane("light")
        self.assertEqual(self.verdict(), "HOLD heavy-lease-full 4/4")  # 3 + 4 * 0.25
        self.lane("light")
        self.assertEqual(self.verdict(), "HOLD heavy-lease-full 4.25/4")

    def test_hook_end_to_end_denies_only_when_the_weighted_load_is_full(self):
        for _ in range(3):
            self.lane("light")
        self.lane("heavy")
        (Path(self.tmp.name) / "p.json").write_text("{}")

        def hook():
            p = subprocess.run([sys.executable, str(SC / "heavy_gate.py")], input=json.dumps({"tool_input": {"command": "pytest -q"}}),
                               env={**os.environ, **self.env, "PERUN_HEAVY_DIR": str(self.d), "HOME": self.tmp.name,
                                    "XDG_CACHE_HOME": self.tmp.name, "PERUN_POLICY": str(Path(self.tmp.name) / "p.json")},
                               capture_output=True, text=True)
            return p.stdout
        self.assertEqual(hook(), "")
        for _ in range(3):
            self.lane("heavy")  # 3 light + 4 heavy = 4.75 >= 4
        out = json.loads(hook())["hookSpecificOutput"]
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("heavy-lease-full 4.75/4", out["permissionDecisionReason"])


class Cli(Fleet):
    def run_cli(self, *args):
        (Path(self.tmp.name) / "p.json").write_text("{}")
        env = {**os.environ, "PERUN_HEAVY_DIR": str(self.d), "PERUN_POLICY": str(Path(self.tmp.name) / "p.json"),
               "HOME": self.tmp.name, "XDG_CACHE_HOME": self.tmp.name}
        return subprocess.run([sys.executable, str(SC / "perun_policy.py"), *args], env=env, capture_output=True, text=True)

    def test_acquire_kind_light_then_heavy_load_prints_the_weighted_count(self):
        p = self.run_cli("heavy-acquire", "--kind", "light")
        self.assertEqual((p.returncode, p.stdout.strip()), (0, str(os.getpid())))
        self.assertEqual((self.d / str(os.getpid())).read_text().split()[2], "light")
        self.assertEqual(self.run_cli("heavy-load").stdout.strip(), "0.25")

    def test_bad_kind_and_bad_usage_exit_two(self):
        self.assertEqual(self.run_cli("heavy-acquire", "--kind", "no good").returncode, 2)
        self.assertEqual(self.run_cli("heavy-acquire", "--kind").returncode, 2)
        self.assertEqual(self.run_cli("heavy-acquire", "light").returncode, 2)


class LaneCap(unittest.TestCase):
    """host_probe's `--live-lanes` takes the weighted count, so light lanes stop filling the lane cap."""

    def decide(self, live):
        return host_probe.decide(swap_samples=(1, 1), free_ram_pct=50, lane_type="light", live_lanes=live, max_lanes=2)

    def test_fractional_live_lanes(self):
        self.assertEqual(self.decide(1.75), "SPAWN")
        self.assertEqual(self.decide(2.0), "HOLD lane-cap")
        self.assertEqual(self.decide(4), "HOLD lane-cap")  # four unweighted lanes: the old, inflated hold


if __name__ == "__main__":
    unittest.main()
