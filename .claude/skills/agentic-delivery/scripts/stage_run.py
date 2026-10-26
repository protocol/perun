#!/usr/bin/env python3
"""stage_run.py — run one train/pregate/hook stage under the machine-wide heavy lease with a wall-clock timeout.

  stage_run.py [--name NAME] [--timeout MIN] [--wait SECS] -- CMD...

WHY: heavy_gate.py only gates the agent's own Bash calls. A train, a pregate or a git hook starts its tests from a
subprocess, so nothing capped them (load1 124 on 44 cores) and nothing bounded them (one train held the heavy slot over 5h).

What it does: (1) first reaps leases left by a stage_run that was SIGKILLed (see below). (2) takes the same non-exclusive
lease heavy_gate.py counts (perun_policy.heavy_acquire, the slot cap from perun_policy.heavy_slots), retrying every second
for up to --wait SECS (default $PERUN_HEAVY_WAIT_SECS or 600); a slot still full then is a DEFER: CMD never runs, it prints
"DEFER: stage ..." and exits 75. (3) runs CMD in its own process group. (4) past the timeout it kills the group (TERM, then
KILL after 5s), prints "stage-timeout: NAME ..." to stderr and exits 124. The lease is released on every exit, including SIGTERM
and SIGHUP (handled from before the slot wait; the stage's group is killed, exit 128+signal) and the death of the parent process
(noticed within 2s: the stage's group is killed, exit 129). A timeout or wait that is nan, inf or negative exits 2 (fail closed).
--probe runs no command: it waits for a free slot, gives it straight back and exits 0 (75 when none freed in --wait).
Exit codes: 75 = deferred and 124 = timed out are infrastructure results, never a verdict on CMD, so callers must not read
them as RED. To keep them unambiguous, a CMD that itself exits 75 or 124 is reported as 1. Any other exit is CMD's.
--hook (git hooks): no heavy lease; past the timeout it exits 124 with "COULD-NOT-CHECK: hook exceeded Ns; index.lock holder:
<pid cmd | unknown>" (the holder is only reported, never signalled; the commit is not allowed through).
The timeout is stretched by max(1, load1/cores) (capped 3x) measured when the stage starts, so a busy host does not kill a healthy
stage; --hook is never stretched. Timeout minutes: --timeout, else $PERUN_STAGE_TIMEOUT_MIN, else policy key `stage_timeout_min` (default 120); 0 = no limit.
A malformed policy fails closed (exit 2). Side effects: one lease file under the heavy dir, refreshed every 10 minutes.

Lease file: `<pid> <start epoch> heavy <pid start time> <child pgid> <child start time> <host>`
(a lease from another host is ignored: its pids mean nothing here). If stage_run is SIGKILLed its child
keeps running and the pid may be reused: perun_policy._leases ignores a lease whose recorded pid start time no longer matches,
and the next stage_run kills the group of such a dead lease when the child (same pgid and start time) is still alive, then
removes the lease. ponytail: a group whose leader already exited but whose grandchildren live on is not found; add a
`ps -g` sweep if that is measured.
"""
import argparse
import math
import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import host_probe  # noqa: E402
import perun_policy as pp  # noqa: E402

DEFER, TIMEOUT = 75, 124


def kill_group(pgid: int, p: subprocess.Popen | None = None) -> bool:
    """TERM the process group, KILL it after a 5s grace; True once the group is gone (`p` is our child, reaped here).
    A PermissionError on the first signal (a group we may not signal) skips the kill with a warning and returns False; it never
    propagates. One after we already signalled the group is macOS answering EPERM for a group of only zombies: that is gone."""
    sent = False
    try:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            os.killpg(pgid, sig)
            sent = True
            for _ in range(50):
                if p is not None:
                    p.poll()
                os.killpg(pgid, 0)
                time.sleep(0.1)
    except ProcessLookupError:
        return True
    except PermissionError as e:
        if sent:
            return True
        print(f"WARN: stage_run: cannot signal process group {pgid} ({e}); not killed", file=sys.stderr)
    return False


LOAD_SCALE_CAP = 3.0


def load_scale(load1, cores) -> float:
    """Timeout multiplier: max(1, load1 / cores), capped at LOAD_SCALE_CAP; 1 when either reading is unknown."""
    return min(LOAD_SCALE_CAP, max(1.0, load1 / cores)) if load1 is not None and cores else 1.0


def lock_holder() -> str:
    """`<pid> <command>` of the process holding this repo's index.lock (lsof), else "unknown". Read-only; never signals it."""
    try:
        gd = subprocess.run(["git", "rev-parse", "--absolute-git-dir"], capture_output=True, text=True, timeout=5).stdout.strip()
        h = subprocess.run(["lsof", "-t", os.path.join(gd, "index.lock")], capture_output=True, text=True, timeout=5).stdout.split()[0]
        return f"{h} {subprocess.run(['ps', '-o', 'command=', '-p', h], capture_output=True, text=True, timeout=5).stdout.strip()}".strip()
    except (OSError, IndexError, subprocess.SubprocessError):
        return "unknown"


def stamp(d, pid: int, own: str, pgid: int = 0, child: str = "-") -> None:
    """(Re)write our lease with the process start times; a write error is ignored (the lease already exists or the dir is unusable)."""
    try:
        (d / str(pid)).write_text(f"{pid} {int(time.time())} heavy {own} {pgid} {child} {pp.HOST}")
    except OSError:
        pass


def reap(d) -> None:
    """Kill the stage child of every lease whose stage_run is dead (or its pid reused), then drop that lease."""
    for f in d.glob("*") if d.is_dir() else []:
        try:
            t = f.read_text().split()
            pid, pgid = int(t[0]), int(t[4])
        except (OSError, ValueError, IndexError):
            continue
        if len(t) not in (6, 7) or (len(t) == 7 and t[6] != pp.HOST) or (pp._alive(pid) and (t[3] == "-" or pp.pstart(pid) in ("", t[3]))):
            continue
        if pgid > 1 and t[5] != "-" and pp.pstart(pgid) == t[5]:
            print(f"stage_run: reaping orphaned stage group {pgid} of dead stage_run {pid}", file=sys.stderr)
            if not kill_group(pgid):
                continue  # not signalable: keep the lease so the next run retries
        f.unlink(missing_ok=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="stage_run.py")
    ap.add_argument("--name", default="stage")
    ap.add_argument("--timeout", type=float, help="minutes; 0 = none")
    ap.add_argument("--hook", action="store_true", help="git hook mode: no heavy lease; a timeout reports COULD-NOT-CHECK with the index.lock holder")
    ap.add_argument("--wait", type=float)
    ap.add_argument("--probe", action="store_true", help="only wait for a free heavy slot, then release it and exit 0 (75 = still full); runs no command")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not cmd and not a.probe:
        ap.error("no command")
    try:
        pol = pp.load()
    except ValueError as e:
        print(f"stage_run: {e}", file=sys.stderr)
        return 2
    try:
        wait = a.wait if a.wait is not None else float(os.environ.get("PERUN_HEAVY_WAIT_SECS", 600))
        tmo = a.timeout if a.timeout is not None else float(os.environ.get("PERUN_STAGE_TIMEOUT_MIN", pol["stage_timeout_min"]))
    except ValueError as e:  # fail closed on a malformed env value, like a malformed policy
        print(f"stage_run: bad PERUN_HEAVY_WAIT_SECS / PERUN_STAGE_TIMEOUT_MIN ({e})", file=sys.stderr)
        return 2
    if not all(math.isfinite(v) and v >= 0 for v in (wait, tmo)):  # nan/inf/negative would disable the cap or the wait
        print(f"stage_run: timeout and wait must be finite and >= 0 (timeout {tmo:g}m, wait {wait:g}s)", file=sys.stderr)
        return 2
    pid, d, t0, ppid0 = os.getpid(), pp.lease_dir(), time.time(), os.getppid()
    leased = not a.hook  # a commit hook is a fast check, not a heavy job: no lease, no slot wait
    kid = [None]

    def stop(sig, _frame):  # SIGTERM/SIGHUP, also during the slot wait: kill our stage group, drop a lease not yet owned by `finally`
        if kid[0] is not None:
            kill_group(kid[0].pid, kid[0])
        else:
            pp.heavy_release(d, pid)
        sys.exit(128 + sig)

    for sg in (signal.SIGTERM, signal.SIGHUP):  # installed before the slot wait: a stage_run waiting for a slot must not leave its lease behind
        signal.signal(sg, stop)
    while leased:
        if os.getppid() != ppid0:  # parent died (reparented): nobody is waiting for this stage any more
            print(f"stage_run: stage {a.name}: parent exited during the slot wait; not run", file=sys.stderr)
            return 129
        try:
            reap(d)
            load1, cores = host_probe.read_load1_and_cores()
            slots = pp.heavy_slots(cores or os.cpu_count() or 1, load1, pol["tokens"], host_probe.read_cpu_idle_pct())
            if pp.heavy_acquire(d, slots, pid):
                break
        except OSError as e:  # lease dir unwritable: run unleased, still timed (same stance as train_land's exclusive lease)
            print(f"WARN: stage {a.name}: heavy lease unavailable ({e}); running without it", file=sys.stderr)
            leased = False
            break
        if time.time() - t0 >= wait:
            print(f"DEFER: stage {a.name}: heavy slots full after {wait:g}s; not run (exit {DEFER}, not a RED)", file=sys.stderr)
            return DEFER
        time.sleep(1)
    if a.probe:  # a slot was free: report that and give it back (the caller retakes it with its own stage_run)
        if leased:
            pp.heavy_release(d, pid)
        return 0
    if tmo > 0 and not a.hook:  # a loaded host runs the same stage slower: stretch the budget instead of killing a healthy stage
        scale = load_scale(*host_probe.read_load1_and_cores())
        if scale > 1:
            tmo *= scale
            print(f"stage_run: stage {a.name}: load {scale:.2f}x cores; timeout stretched to {tmo:g}m", file=sys.stderr)
    own = pp.pstart(pid) or "-"
    if leased:
        stamp(d, pid, own)
    try:
        p = subprocess.Popen(cmd, start_new_session=True)
        kid[0] = p
        child = pp.pstart(p.pid) or "-"
        if leased:
            stamp(d, pid, own, p.pid, child)
        deadline = time.time() + tmo * 60 if tmo > 0 else None
        beat = time.time()
        try:
            while True:
                left = deadline - time.time() if deadline else 600
                if left <= 0:
                    holder = lock_holder() if a.hook else ""  # read before the kill; only our own stage group is ever signalled
                    if not kill_group(p.pid, p):
                        leased = False  # could not kill: keep the lease file (it records the group) so the next run retries the reap
                    if a.hook:
                        print(f"COULD-NOT-CHECK: hook exceeded {tmo * 60:g}s; index.lock holder: {holder}", file=sys.stderr)
                        return TIMEOUT
                    print(f"stage-timeout: {a.name} killed after {tmo:g}m (process group {p.pid}; exit {TIMEOUT}, not a RED)", file=sys.stderr)
                    return TIMEOUT
                if os.getppid() != ppid0:  # parent died: kill our stage group (the finally releases the lease)
                    print(f"stage_run: stage {a.name}: parent exited; killing the stage's process group", file=sys.stderr)
                    kill_group(p.pid, p)
                    return 129
                try:
                    rc = p.wait(min(left, 2))
                    return 1 if rc in (DEFER, TIMEOUT) else rc
                except subprocess.TimeoutExpired:
                    if leased and time.time() - beat >= 600:
                        beat = time.time()
                        stamp(d, pid, own, p.pid, child)  # keep the lease inside LEASE_TTL on a long stage
        except KeyboardInterrupt:
            kill_group(p.pid, p)
            return 130
    finally:
        if leased:
            try:
                pp.heavy_release(d, pid)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main())
