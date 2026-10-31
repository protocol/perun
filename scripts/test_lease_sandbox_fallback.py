#!/usr/bin/env python3
"""Heavy-lease sandbox fallback (macOS only: these cases skip elsewhere; test_lease_sandbox_hardening.py covers the rest). A Claude Code
sandbox writes only cwd and /tmp/claude-<uid>, so `~/.cache/perun/heavy` is read-only there: writers (heavy-acquire, heavy-exclusive,
stage_run) fall back to `<root>/perun/heavy`, and every reader (slot count, exclusive gate, the unsandboxed heavy_gate hook) checks both
dirs. Hermetic: the cache dir, the fallback root (PERUN_HEAVY_FALLBACK_ROOT) and the policy are fixtures, so the real /tmp/claude-<uid>
is never touched. `Fixture` holds the setup and helpers; test_lease_sandbox_hardening.py reuses it."""
import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
AD = ROOT / ".claude/skills/agentic-delivery/scripts"
PP, HG, SR = AD / "perun_policy.py", AD / "heavy_gate.py", AD / "stage_run.py"
sys.path.insert(0, str(AD))
import perun_policy as pp  # noqa: E402


class Fixture(unittest.TestCase):
    """No cases of its own: the hermetic primary + fallback dirs and the helpers the case classes use."""

    def setUp(self):
        td = tempfile.TemporaryDirectory(prefix="dcr-ls.")
        self.addCleanup(td.cleanup)
        self.t = Path(td.name).resolve()
        self.cache, self.fb = self.t / "cache", self.t / "fb"  # primary <cache>/perun/heavy, fallback <fb>/perun/heavy
        self.primary, self.fbdir = self.cache / "perun" / "heavy", self.fb / "perun" / "heavy"
        self.fb.mkdir()
        os.chmod(self.fb, 0o700)  # mkdir honours the umask; the fallback root must be exactly 0700
        (self.t / "p.json").write_text("{}")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("PERUN_", "XDG_"))}
        self.env.update(XDG_CACHE_HOME=str(self.cache), PERUN_HEAVY_FALLBACK_ROOT=str(self.fb), PERUN_POLICY=str(self.t / "p.json"))
        patch = mock.patch.dict(os.environ, self.env, clear=True)
        patch.start()
        self.addCleanup(patch.stop)
        self.sleepers = []
        self.addCleanup(self._kill_sleepers)

    def _kill_sleepers(self):
        for p in self.sleepers:
            p.kill()
            p.wait()

    def sleeper(self) -> int:
        """Pid of a live process of ours: a lease holder that stays alive for the test."""
        p = subprocess.Popen(["sleep", "60"])
        self.sleepers.append(p)
        return p.pid

    def plant(self, root: Path, pid: int, kind: str = "heavy") -> Path:
        """A live lease for `pid` in `<root>/perun/heavy`."""
        d = root / "perun" / "heavy"
        d.mkdir(parents=True, exist_ok=True)
        (d / str(pid)).write_text(f"{pid} {int(time.time())} {kind}")
        return d / str(pid)

    def plant_exclusive(self, root: Path, pid: int) -> Path:
        f = root / "perun" / "heavy.exclusive"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"{pid} {int(time.time())}")
        return f

    def lock_primary(self):
        """Make the primary lease dir refuse new files while it still exists, as a sandbox does (chmod 500). As root chmod does not bind,
        so a regular file in place of the cache dir stands in."""
        if os.geteuid() == 0:
            self.cache.write_text("not a dir")
            return
        self.primary.mkdir(parents=True)
        dirs = (self.primary, self.primary.parent)
        for d in dirs:
            os.chmod(d, 0o500)
        self.addCleanup(lambda: [os.chmod(d, 0o700) for d in dirs])

    def cli(self, *args, env=None):
        """`perun_policy.py ARGS` as a child of this process (so its caller shell, the lease holder, is us): (rc, stdout)."""
        r = subprocess.run([sys.executable, str(PP), *args], env=env or self.env, cwd=self.t, capture_output=True, text=True, timeout=30)
        return r.returncode, r.stdout.strip()

    def hook(self, n: int, env=None) -> str:
        """The heavy_gate PreToolUse deny reason for a heavy command on an idle injected host ("" = allowed). `n` makes each command
        distinct: the same one denied three times is let through by the retry ledger."""
        e = dict(env or self.env, PERUN_GATE_LOAD1="0", PERUN_GATE_CORES="1", PERUN_GATE_FREE_RAM_PCT="60", PERUN_HEAVY_HOOK_WAIT_SECS="0")
        r = subprocess.run([sys.executable, str(HG)], input=json.dumps({"tool_input": {"command": f"pytest tests/t{n}"}, "cwd": "/x"}),
                           env=e, cwd=self.t, capture_output=True, text=True, timeout=30)
        return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"] if r.stdout.strip() else ""


@unittest.skipUnless(sys.platform == "darwin", "the sandbox fallback is macOS only")
class FallbackCase(Fixture):
    # -- writers ----------------------------------------------------------------------------------------------------

    def test_acquire_and_release_use_fallback_when_primary_unwritable(self):
        self.lock_primary()
        rc, out = self.cli("heavy-acquire")
        self.assertEqual((rc, out), (0, str(os.getpid())))
        self.assertTrue((self.fbdir / str(os.getpid())).is_file(), "lease must land in the fallback dir")
        self.assertEqual(list(self.primary.glob("*")) if self.primary.is_dir() else [], [], "nothing may be written to the primary")
        self.assertEqual(self.cli("heavy-load"), (0, "1"))
        self.assertEqual(self.cli("heavy-release")[0], 0)
        self.assertFalse((self.fbdir / str(os.getpid())).exists(), "release must clear the fallback lease")
        self.assertEqual(self.cli("heavy-load"), (0, "0"))

    def test_exclusive_acquire_renew_release_use_fallback_when_primary_unwritable(self):
        self.lock_primary()
        f = self.fb / "perun" / "heavy.exclusive"
        self.assertEqual(self.cli("heavy-exclusive"), (0, str(os.getpid())))
        self.assertTrue(f.is_file())
        self.assertEqual(pp.exclusive_holder(pp.lease_dir()), os.getpid(), "a reader of the primary must see the fallback holder")
        old = time.time() - 3600
        os.utime(f, (old, old))
        self.assertEqual(self.cli("heavy-exclusive-renew")[0], 0)
        self.assertGreater(f.stat().st_mtime, old + 3000, "renew must refresh the fallback lease")
        self.assertEqual(self.cli("heavy-exclusive-release")[0], 0)
        self.assertFalse(f.exists())
        self.assertIsNone(pp.exclusive_holder(pp.lease_dir()))

    def test_missing_fallback_root_is_created_0700_by_a_writer_only(self):
        new = self.t / "fb-new"
        env = dict(self.env, PERUN_HEAVY_FALLBACK_ROOT=str(new))
        self.assertEqual(self.cli("heavy-load", env=env), (0, "0"))
        self.assertFalse(new.exists(), "a reader must never create the fallback root")
        self.lock_primary()
        self.assertEqual(self.cli("heavy-acquire", env=env), (0, str(os.getpid())))
        self.assertEqual(stat.S_IMODE(new.lstat().st_mode), 0o700)
        self.assertTrue((new / "perun" / "heavy" / str(os.getpid())).is_file())

    def test_stage_run_leases_in_fallback_and_a_hook_takes_none(self):
        self.lock_primary()
        p = subprocess.Popen([sys.executable, str(SR), "--name", "lsfb", "--", "sleep", "8"], env=self.env, cwd=self.t,
                             stderr=subprocess.PIPE, text=True)
        lease = self.fbdir / str(p.pid)
        try:
            for _ in range(300):
                if lease.exists() or p.poll() is not None:
                    break
                time.sleep(0.05)
            seen = lease.exists()
            p.terminate()  # stage_run kills its stage group and releases the lease
            err = p.communicate(timeout=30)[1]
        finally:
            p.kill()
        self.assertTrue(seen, f"stage_run must lease in the fallback dir; stderr: {err}")
        self.assertNotIn("heavy lease unavailable", err)
        self.assertFalse(lease.exists(), "stage_run must release its fallback lease on exit")
        hook_fb = self.t / "hook-fb"  # a commit hook takes no lease: it must not even create the fallback root
        r = subprocess.run([sys.executable, str(SR), "--hook", "--name", "h", "--", "true"], env=dict(self.env, PERUN_HEAVY_FALLBACK_ROOT=str(hook_fb)),
                           cwd=self.t, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(hook_fb.exists())

    # -- readers ----------------------------------------------------------------------------------------------------

    def test_fallback_holder_counts_against_slots_for_a_writable_primary(self):
        other, mine = self.sleeper(), os.getpid()
        lease = self.plant(self.fb, other)
        self.assertEqual(pp.lease_load(pp.lease_dir()), 1)
        self.assertEqual(pp.active_leases(pp.lease_dir()), [other])
        self.assertEqual(self.cli("heavy-load"), (0, "1"))
        self.assertEqual(pp.lease_load(self.t / "elsewhere"), 0, "a dir a caller names explicitly stays isolated")
        self.assertFalse(pp.heavy_acquire(pp.lease_dir(), 1, mine), "1 slot, held by a fallback lease: must refuse")
        self.assertFalse((self.primary / str(mine)).exists())
        lease.unlink()
        self.assertTrue(pp.heavy_acquire(pp.lease_dir(), 1, mine), "control: same call with the holder gone must succeed")
        self.assertTrue((self.primary / str(mine)).is_file(), "a writable primary stays the write target")

    def test_fallback_exclusive_holder_blocks_acquire(self):
        other = self.sleeper()
        f = self.plant_exclusive(self.fb, other)
        self.assertEqual(self.cli("heavy-exclusive"), (1, "HELD"))
        self.assertFalse((self.cache / "perun" / "heavy.exclusive").exists())
        self.assertEqual(pp.exclusive_holder(pp.lease_dir()), other)
        f.unlink()
        self.assertEqual(self.cli("heavy-exclusive"), (0, str(os.getpid())), "control: same call with the holder gone must succeed")
        self.assertTrue((self.cache / "perun" / "heavy.exclusive").is_file())
        self.assertEqual(self.cli("heavy-exclusive-release")[0], 0)
        self.assertFalse((self.cache / "perun" / "heavy.exclusive").exists())

    def test_heavy_gate_hook_sees_fallback_holders(self):
        other = self.sleeper()
        self.assertEqual(self.hook(0), "", "control: no holder, idle host: allowed")
        ex = self.plant_exclusive(self.fb, other)
        self.assertIn("gate running: wait", self.hook(1))
        self.assertIn(f"train gate pid {other}", self.hook(2))
        ex.unlink()
        why = self.hook(3)
        self.assertEqual(why, "", "control: exclusive gone, no leases: allowed")
        self.plant(self.fb, other)
        why = self.hook(4)
        self.assertIn("heavy-lease-full 1/1", why)
        self.assertIn(f"pid {other} (heavy, 0m)", why)

    def test_realpath_dedupe_counts_one_dir_once(self):
        a, b = self.sleeper(), self.sleeper()
        self.plant(self.cache, a)
        self.plant(self.fb, b)
        self.assertEqual(pp.lease_load(pp.lease_dir()), 2, "distinct primary and fallback add up")
        link = self.t / "link"  # primary that is the fallback under another name
        link.symlink_to(self.fb)
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(link)}):
            self.assertEqual(pp.lease_dirs(), [link / "perun" / "heavy"])
            self.assertEqual(pp.lease_load(pp.lease_dir()), 1, "one dir reached by two names must count once")

    def test_pinned_dir_is_exactly_one_dir(self):
        self.plant(self.fb, self.sleeper())
        self.assertEqual(self.cli("heavy-load"), (0, "1"), "control: unpinned, the fallback lease counts")
        pin = self.t / "pin"
        env = dict(self.env, PERUN_HEAVY_DIR=str(pin))
        self.assertEqual(self.cli("heavy-load", env=env), (0, "0"))
        pin.write_text("a file, not a dir")  # unusable pinned dir: fail as before, never fall back
        rc, _ = self.cli("heavy-acquire", env=env)
        self.assertEqual(rc, 2)
        self.assertFalse((self.fbdir / str(os.getpid())).exists(), "a pinned dir that fails must not fall back")

    # -- the fallback root must be trustworthy ----------------------------------------------------------------------

    def test_symlinked_fallback_root_is_refused(self):
        real = self.t / "real"
        real.mkdir(mode=0o700)
        os.chmod(real, 0o700)
        self.plant(real, self.sleeper())
        with mock.patch.dict(os.environ, {"PERUN_HEAVY_FALLBACK_ROOT": str(real)}):
            self.assertEqual(pp.lease_load(pp.lease_dir()), 1, "control: the same root, not a symlink, is read")
        link = self.t / "link"
        link.symlink_to(real)
        self.lock_primary()
        with mock.patch.dict(os.environ, {"PERUN_HEAVY_FALLBACK_ROOT": str(link)}):
            self.assertIsNone(pp._fallback())
            self.assertEqual(pp.lease_load(pp.lease_dir()), 0)
            self.assertEqual(pp.writable_lease_dir(), pp.lease_dir(), "no safe fallback: fail as before, never write through the link")
            rc, _ = self.cli("heavy-acquire", env=dict(self.env, PERUN_HEAVY_FALLBACK_ROOT=str(link)))
        self.assertEqual(rc, 2)
        self.assertFalse((real / "perun" / "heavy" / str(os.getpid())).exists(), "nothing may be written through the symlink")

    def test_foreign_owned_or_loose_fallback_root_is_refused(self):
        self.plant(self.fb, self.sleeper())
        self.lock_primary()
        self.assertEqual(pp.lease_load(pp.lease_dir()), 1, "control: a 0700 root we own is read")
        self.assertEqual(pp.writable_lease_dir(), self.fbdir)
        with mock.patch.object(os, "getuid", return_value=os.getuid() + 1):  # the root now belongs to someone else
            self.assertIsNone(pp._fallback())
            self.assertEqual(pp.lease_load(pp.lease_dir()), 0)
            self.assertEqual(pp.writable_lease_dir(), pp.lease_dir())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(pp.main(["heavy-load"]), 0)
            self.assertEqual(out.getvalue().strip(), "0")
        for mode in (0o755, 0o770, 0o750):
            os.chmod(self.fb, mode)
            self.assertIsNone(pp._fallback(), oct(mode))
            self.assertEqual(pp.lease_load(pp.lease_dir()), 0, oct(mode))
            self.assertEqual(pp.writable_lease_dir(), pp.lease_dir(), oct(mode))
        os.chmod(self.fb, 0o700)
        self.assertEqual(pp.lease_load(pp.lease_dir()), 1)


if __name__ == "__main__":
    unittest.main()
