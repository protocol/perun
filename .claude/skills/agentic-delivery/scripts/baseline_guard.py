#!/usr/bin/env python3
"""baseline_guard.py — store a test baseline only when it is not poisoned by load.

WHY: a baseline taken on a loaded host holds failures that are load, not code; every later PR is then compared to a wrong
baseline. Before a baseline is stored: re-run its failures one at a time, record the host load at start, and refuse a run
whose failure count is far above normal.

  baseline_guard.py --fails FILE --rerun 'CMD {id}' --out BASELINE.json [--normal N] [--max-factor F] [--max-load L] [--force]

  --fails FILE    failing test ids of the candidate baseline run, one per line (blank lines ignored).
  --rerun CMD     solo re-run command (shlex-split, no shell); `{id}` is replaced by the test id; exit 0 = passes solo.
  --normal N      the usual failure count of a healthy run (default 5). More than F x max(N, 1) failures (F default 3) REFUSES.
  --max-load L    refuse when the 1-minute load average at start is above L (default: 2 x cores, `PERUN_GATE_CORES` overrides
                  the core count; the value is always recorded).
  --force         skip both refusals (a deliberate, visible override); the solo re-run still happens.
Writes BASELINE.json {"fails": [ids that still fail solo], "flaky": [ids that passed solo], "load1": X, "stored_at": epoch} and
exits 0. REFUSE (exit 1, one `REFUSE baseline: <reason>` line, nothing written): too many failures, or load above --max-load.
Exit 2 on usage error or unreadable FILE. A solo re-run that cannot start counts as still failing. Side effects: the one
output file, written only on acceptance.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time


def solo_passes(cmd, tid):
    try:
        argv = [a.replace("{id}", tid) for a in shlex.split(cmd)]
        return subprocess.run(argv, capture_output=True, timeout=1800).returncode == 0
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(prog="baseline_guard.py")
    ap.add_argument("--fails", required=True)
    ap.add_argument("--rerun", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--normal", type=int, default=5)
    ap.add_argument("--max-factor", type=float, default=3.0)
    ap.add_argument("--max-load", type=float)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if a.max_load is None:
        a.max_load = 2.0 * int(os.environ.get("PERUN_GATE_CORES") or os.cpu_count() or 1)
    try:
        ids = sorted({ln.strip() for ln in open(a.fails, errors="replace") if ln.strip()})
    except OSError as e:
        print(f"baseline_guard: {e}", file=sys.stderr)
        return 2
    load1 = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
    if a.force:
        pass
    elif load1 > a.max_load:
        print(f"REFUSE baseline: load1 {load1:.1f} above --max-load {a.max_load}; re-take it on a quiet host")
        return 1
    if not a.force and len(ids) > a.max_factor * max(a.normal, 1):
        print(f"REFUSE baseline: {len(ids)} failures, far above normal ({a.normal} x {a.max_factor:g}); the run is suspect")
        return 1
    flaky = [t for t in ids if solo_passes(a.rerun, t)]
    out = {"fails": [t for t in ids if t not in flaky], "flaky": flaky, "load1": round(load1, 2), "stored_at": int(time.time())}
    with open(a.out, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"stored baseline: {len(out['fails'])} real, {len(flaky)} passed solo (dropped), load1={out['load1']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
