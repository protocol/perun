#!/usr/bin/env python3
"""Pins the load-tolerant waits in test_destructive_guard_w21.py: its wall-clock case waits up to a 60 s ceiling (a 20 s one
failed once at load average ~13, passing alone) and a real hang still fails, at that ceiling. The guard's own watchdog
(TIMEOUT in destructive_guard_core.py) is the thing waited for, so it is pinned at 20 s or less too.
Offline and instant: a stub stands in for the guard process, so nothing here waits on a clock."""
import importlib.util
import io
import pathlib
import re
import subprocess
import unittest
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parent / "test_destructive_guard_w21.py"
spec = importlib.util.spec_from_file_location("guard_w21", SRC)
w21 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w21)
CORE = w21.GUARD.with_name("destructive_guard_core.py")  # the guard's own watchdog lives here


class StubGuard:
    """Stands in for the guard Popen: records the wait ceiling, then answers like the guard (exit 2) or hangs."""

    def __init__(self, hang):
        self.hang, self.ceiling = hang, None
        self.stdin, self.stderr = io.BytesIO(), io.BytesIO(b"Blocked: destructive guard did not finish within 10s")

    def wait(self, timeout=None):
        self.ceiling = timeout
        if self.hang:
            raise subprocess.TimeoutExpired("guard", timeout)
        return 2

    def kill(self):
        pass


def wall_clock(hang):
    """(stub, error): the wall-clock case run against a stub guard that answers promptly or hangs."""
    stub = StubGuard(hang)
    try:
        with mock.patch.object(subprocess, "Popen", lambda *a, **k: stub):
            w21.test_wall_clock_cap()
    except Exception as e:  # the case's own failure, returned for the assertions
        return stub, e
    return stub, None


class WaitCeiling(unittest.TestCase):
    def test_wall_clock_ceiling_tolerates_load(self):
        stub, err = wall_clock(hang=False)
        self.assertIsNone(err)
        self.assertGreaterEqual(stub.ceiling, 60)  # the old 20 s ceiling is what a loaded runner beat

    def test_real_hang_still_fails_at_a_finite_ceiling(self):
        stub, err = wall_clock(hang=True)
        self.assertIsInstance(err, subprocess.TimeoutExpired)
        self.assertLessEqual(stub.ceiling, 120)  # a ceiling and not a switch-off

    def test_guards_watchdog_is_at_most_20_s(self):
        timeout = int(re.search(r"^TIMEOUT = (\d+)\b", CORE.read_text(), re.M).group(1))
        self.assertLessEqual(timeout, 20)  # the wall-clock case waits for this watchdog: raising it past 20 s must fail here

    def test_every_wait_uses_the_ceiling(self):
        self.assertEqual(set(re.findall(r"\btimeout=(\w+)", SRC.read_text())), {"WAIT"})  # no literal a loaded runner can beat


if __name__ == "__main__":
    unittest.main()
