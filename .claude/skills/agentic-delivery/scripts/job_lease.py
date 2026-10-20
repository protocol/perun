#!/usr/bin/env python3
"""job_lease.py — per-repo lease for long jobs (ship and QA scripts) + a unique per-run resource suffix.

WHY: heavy_gate.py admits short heavy commands against machine load, but a long job (a merge train, a QA run that
creates a database) is not a hook-sized command. Two of them in one repo, one started by the owner and one by an agent,
collided on the same database name and fought for the same ports and CPU. The lease makes them take turns; the suffix
makes their resources differ even when something bypasses the lease.

  job_lease.py run [--name NAME] [--timeout SECS] -- CMD...
      Hold the repo's lease NAME (default "long") while CMD runs. The lease is a kernel flock (serial_gate.py run) on
      <git-common-dir>/perun-job-lease/NAME/lock, so every worktree of the repo shares it and the kernel frees it when
      the holder dies, however it dies. A waiter prints a "queued Ns" line to stderr every 120s (PERUN_QUEUE_NOTE_SECS).
      The child gets PERUN_RUN_SUFFIX and PERUN_JOB_LEASE (the held names) in its environment, so a nested
      `job_lease.py run` of the same name just runs its command under the holder's lease (reentrant, no deadlock).
      The lease belongs to the wrapper: if the wrapper dies the lease frees even when the child lives on. Exit: CMD's code; 124 lease still held after --timeout
      (default 1800), CMD never ran; 2 usage or not a git repo (fails closed, CMD never runs).
  job_lease.py suffix
      Print a fresh suffix (<pid>_<6 hex>): letters, digits, underscore only, so it is safe in a database, container or
      directory name. Name per-run resources `qa_db_$(job_lease.py suffix)` or `qa_db_$PERUN_RUN_SUFFIX`.

Owner and agents honour the same lease by starting the long job through `job_lease.py run`. Side effects: creates the
lease directory under the git common dir; deletes nothing.
"""
from __future__ import annotations

import argparse
import os
import re
import secrets
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serial_gate  # noqa: E402


def suffix() -> str:
    return f"{os.getpid()}_{secrets.token_hex(3)}"


def lease_dir(name: str, cwd: str = ".") -> str | None:
    """`<git-common-dir>/perun-job-lease/<name>`, or None when cwd is not in a git repo or the name is unsafe."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name) or name in (".", ".."):
        return None
    r = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return os.path.join(os.path.abspath(os.path.join(cwd, r.stdout.strip())), "perun-job-lease", name)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["suffix"]:
        print(suffix())
        return 0
    cmd: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog="job_lease.py")
    ap.add_argument("action", choices=["run"])
    ap.add_argument("--name", default="long")
    ap.add_argument("--timeout", type=float, default=1800.0)
    try:
        a = ap.parse_args(argv)
    except SystemExit:
        return 2
    d = lease_dir(a.name)
    if not cmd or d is None:
        print("job_lease: need a command after '--', a safe --name, and a git repo", file=sys.stderr)
        return 2
    held = [n for n in os.environ.get("PERUN_JOB_LEASE", "").split(":") if n]
    if a.name in held:  # a child of the holder (same lease name): re-taking the flock would wait on ourselves
        try:
            os.execvp(cmd[0], cmd)
        except OSError as e:
            print(f"job_lease: cannot run {cmd[0]}: {e}", file=sys.stderr)
            return 127
    os.environ["PERUN_JOB_LEASE"] = ":".join(held + [a.name])
    os.environ["PERUN_RUN_SUFFIX"] = suffix()
    return serial_gate.run_locked(d, a.timeout, cmd)


if __name__ == "__main__":
    sys.exit(main())
