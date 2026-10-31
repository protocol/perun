#!/usr/bin/env python3
"""Hardening of the heavy-lease sandbox fallback (the base cases and the shared `Fixture` live in test_lease_sandbox_fallback.py). Pins: lease
and holder reads never block on a FIFO and skip anything that is not a regular file; the fallback exists on macOS only; the `perun` and
`heavy` components of the fallback must be real directories we own; stage_run's orphan reap never signals a group named by a lease outside
the primary dir; the parent-dir probe of `_writable`; and the accepted limit that a forged holder in the shared fallback can delay or deny
heavy commands. Hermetic like the base file (fixture cache dir, fallback root and policy). Every subprocess has a timeout, so a regression
that blocks fails its case instead of hanging the run."""
import contextlib
import io
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from test_lease_sandbox_fallback import SR, Fixture, pp  # noqa: E402  (also puts the skill scripts on sys.path)

import stage_run as sr  # noqa: E402

mac = unittest.skipUnless(sys.platform == "darwin", "the sandbox fallback is macOS only")


class Hardening(Fixture):
    def platform(self, name: str):
        """Run the rest of this test as platform `name`. In-process only: a child process keeps the real one."""
        p = mock.patch.object(sys, "platform", name)
        p.start()
        self.addCleanup(p.stop)

    # -- a non-regular file never blocks a reader or feeds it ---------------------------------------------------------

    def test_read_lease_takes_regular_files_only(self):
        f = self.t / "lease"
        f.write_text("12 34")
        self.assertEqual(pp.read_lease(f), "12 34")
        f.write_text("x" * 10000)
        self.assertEqual(len(pp.read_lease(f)), 4096, "a lease is under 400 characters: a huge file is never read whole")
        link = self.t / "link"
        link.symlink_to(f)
        fifo = self.t / "fifo"
        os.mkfifo(fifo)
        wfd = os.open(fifo, os.O_RDWR)  # a FIFO with a writer and a lease-looking line waiting is still no lease
        self.addCleanup(os.close, wfd)
        os.write(wfd, b"4242 1")
        fds = len(os.listdir("/dev/fd"))
        for bad in (link, self.t, self.t / "missing", fifo):  # a symlink, a directory, nothing, a FIFO
            for _ in range(20):
                with self.assertRaises(OSError):
                    pp.read_lease(bad)
        self.assertEqual(len(os.listdir("/dev/fd")), fds, "a rejected file must not leak its descriptor")

    def test_fifo_in_a_pinned_dir_never_blocks_any_reader(self):
        pin = self.t / "pin" / "heavy"  # a FIFO named like a lease, one like the holder file, one like the queue marker
        pin.mkdir(parents=True)
        for f in (pin / "4242", pin.parent / "heavy.exclusive", pin / ".waiting"):
            os.mkfifo(f)
        env = dict(self.env, PERUN_HEAVY_DIR=str(pin))
        self.assertEqual(self.cli("heavy-load", env=env), (0, "0"), "_leases skips the FIFO")
        self.assertEqual(self.hook(0, env), "", "the hook reads the holder file and the leases")
        self.assertEqual(self.cli("heavy-acquire", env=env), (0, str(os.getpid())), "heavy_acquire reads the queue marker")
        self.assertEqual(self.cli("heavy-release", env=env)[0], 0)
        r = subprocess.run([sys.executable, str(SR), "--name", "fifo", "--", "true"], env=env, cwd=self.t, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)  # reap reads every lease in the dir
        self.assertNotIn("heavy lease unavailable", r.stderr)

    @mac
    def test_fifo_in_the_fallback_never_blocks_the_hook_or_the_train_gate(self):
        """What confined code can plant for the unsandboxed readers: a FIFO named like a lease and one named like the holder file."""
        other = self.sleeper()
        self.plant(self.fb, other)
        os.mkfifo(self.fbdir / "4242")
        os.mkfifo(self.fb / "perun" / "heavy.exclusive")
        self.assertEqual(self.cli("heavy-load"), (0, "1"), "the FIFO is skipped, the real lease beside it still counts")
        why = self.hook(0)
        self.assertIn("heavy-lease-full 1/1", why)
        self.assertIn(f"pid {other} (heavy, 0m)", why)
        self.assertEqual(self.cli("heavy-exclusive"), (0, str(os.getpid())), "a FIFO is no holder: the train gate takes the lease")
        self.assertEqual(self.cli("heavy-exclusive-release")[0], 0)

    # -- macOS only -------------------------------------------------------------------------------------------------

    def test_off_macos_the_fallback_is_neither_read_nor_written(self):
        self.platform("linux")
        other = self.sleeper()
        self.plant(self.fb, other)
        self.plant_exclusive(self.fb, other)
        self.assertIsNone(pp._fallback())
        self.assertEqual(pp.lease_dirs(), [pp.lease_dir()])
        self.assertEqual(pp.lease_load(pp.lease_dir()), 0, "a lease in the fallback means nothing off macOS")
        self.assertIsNone(pp.exclusive_holder(pp.lease_dir()))
        self.assertEqual(pp.writable_lease_dir(), pp.lease_dir())
        self.assertFalse(self.cache.exists(), "no probe: nothing is created just to pick the dir")
        self.lock_primary()
        new = self.t / "fb-new"
        with mock.patch.dict(os.environ, {"PERUN_HEAVY_FALLBACK_ROOT": str(new)}):
            self.assertEqual(pp.writable_lease_dir(), pp.lease_dir(), "a read-only lease dir is not worked around off macOS")
            with self.assertRaises(OSError):
                pp.heavy_acquire(pp.writable_lease_dir(), 1, os.getpid())
        self.assertFalse(new.exists(), "the fallback root is not created either")
        self.assertEqual([f.name for f in self.fbdir.iterdir()], [str(other)], "nothing was written to the existing fallback")

    # -- the fallback's own path components -----------------------------------------------------------------------------

    def test_symlinked_or_foreign_perun_and_heavy_components_are_refused(self):
        self.platform("darwin")
        elsewhere = self.t / "elsewhere"
        planted = self.plant(elsewhere, self.sleeper())  # a live lease that a followed symlink would expose
        self.lock_primary()

        def refused(why):
            self.assertIsNone(pp._fallback(), why)
            self.assertEqual(pp.lease_load(pp.lease_dir()), 0, why)
            self.assertEqual(pp.writable_lease_dir(), pp.lease_dir(), why)
            self.assertEqual([f.name for f in planted.parent.iterdir()], [planted.name], f"{why}: nothing may be written through it")

        (self.fb / "perun").symlink_to(elsewhere / "perun")
        refused("perun is a symlink")
        (self.fb / "perun").unlink()
        (self.fb / "perun").mkdir()
        self.fbdir.symlink_to(elsewhere / "perun" / "heavy")
        refused("heavy is a symlink")
        self.fbdir.unlink()
        self.plant(self.fb, self.sleeper())
        self.assertEqual(pp.lease_load(pp.lease_dir()), 1, "control: real directories are read")
        lstat = Path.lstat
        for name in ("perun", "heavy"):
            def as_foreign(p, name=name):  # the same directory, seen as owned by someone else
                st = lstat(p)
                return os.stat_result((*st[:4], st.st_uid + 1, *st[5:10])) if p.name == name else st
            with mock.patch.object(Path, "lstat", as_foreign):
                refused(f"{name} is owned by another user")

    @unittest.skipIf(os.geteuid() == 0, "chmod does not bind root")
    def test_a_writable_heavy_dir_under_a_read_only_parent_falls_back(self):
        self.platform("darwin")
        self.primary.mkdir(parents=True)  # write_lease puts its temp file beside the lease dir, so this primary is unusable
        os.chmod(self.primary.parent, 0o555)
        self.addCleanup(os.chmod, self.primary.parent, 0o700)
        self.assertFalse(pp._writable(self.primary))
        self.assertEqual(pp.writable_lease_dir(), self.fbdir)

    # -- what confined code can still do, and what it cannot ------------------------------------------------------------

    @mac
    def test_a_forged_holder_in_the_fallback_is_an_accepted_denial_of_service(self):
        """Every sandboxed session of the user writes the fallback, so one can name a live pid (1 here) as the train gate or a lease
        holder. The hook then denies heavy commands and heavy-exclusive reports HELD: same-user delay, accepted (see perun_policy._fallback)."""
        self.plant_exclusive(self.fb, 1)
        self.assertIn("gate running: wait", self.hook(0))
        self.assertEqual(self.cli("heavy-exclusive"), (1, "HELD"))
        (self.fb / "perun" / "heavy.exclusive").unlink()
        self.plant(self.fb, 1)
        self.assertEqual(self.cli("heavy-load"), (0, "1"), "a forged lease holds a slot until it expires")

    def test_reap_outside_the_primary_dir_unlinks_without_signalling(self):
        """A lease in the shared fallback can name any process group: stage_run drops a stale one but never signals what it names."""
        sent = []
        text = f"4242 {int(time.time())} heavy S 4321 S {pp.HOST}"  # stage_run pid, start, kind, its start, child pgid, child start, host
        with mock.patch.object(pp, "_alive", return_value=False), mock.patch.object(pp, "pstart", return_value="S"), \
                mock.patch.object(sr, "kill_group", side_effect=lambda g, p=None: sent.append(g) or True):
            for d, signalled in ((self.fbdir, []), (pp.lease_dir(), [4321])):  # the fallback, then the primary as the control
                d.mkdir(parents=True, exist_ok=True)
                (d / "4242").write_text(text)
                sent.clear()
                with contextlib.redirect_stderr(io.StringIO()):  # reap says which group it kills
                    sr.reap(d)
                self.assertEqual(sent, signalled, str(d))
                self.assertFalse((d / "4242").exists(), f"a stale lease is dropped from {d}")


if __name__ == "__main__":
    unittest.main()
