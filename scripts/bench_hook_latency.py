#!/usr/bin/env python3
"""Interleaved before/after wall-time harness for a hook script (stdlib only).

Usage: bench_hook_latency.py BEFORE.py AFTER.py [--runs 25] [--payload JSON]
Each arm is warmed once (so bytecode caches are populated), then the two are run alternately RUNS times so both see the
same machine load, in a throwaway PYTHONPYCACHEPREFIX. Prints min / median / max in ms per arm and the load average.
Load only adds time: compare the minimums first, then the medians, and read nothing into a gap smaller than the spread.
Get a "before" copy with `git show <base>:<path> > /tmp/before/hook.py`.
"""
import argparse
import os
import statistics
import subprocess
import sys
import tempfile
import time

PAYLOAD = '{"tool_name":"Bash","tool_input":{"command":"git status && ls -la"}}'


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--runs", type=int, default=25)
    ap.add_argument("--payload", default=PAYLOAD)
    a = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="perun-bench-") as pfx:
        env = {**os.environ, "PYTHONPYCACHEPREFIX": pfx}

        def run(path: str) -> float:
            t = time.perf_counter()
            subprocess.run([sys.executable, path], input=a.payload.encode(), capture_output=True, env=env)
            return (time.perf_counter() - t) * 1000
        run(a.before), run(a.after)
        ts = ([], [])
        for _ in range(a.runs):
            ts[0].append(run(a.before))
            ts[1].append(run(a.after))
    for name, v in zip(("before", "after"), ts):
        print(f"{name}: min {min(v):.0f} ms, median {statistics.median(v):.0f} ms, max {max(v):.0f} ms ({a.runs} runs)")
    print("load average", os.getloadavg() if hasattr(os, "getloadavg") else "n/a")
    return 0


if __name__ == "__main__":
    sys.exit(main())
