#!/usr/bin/env python3
"""lkg.py — last-known-good (LKG) pointer: the newest commit on which the full ci-tests suite passed.

`record [sha]` (run after the suite is green; sha defaults to HEAD) writes {"sha", "utc"} to `<landing cache>/<repo>.lkg.json`
(the landing watchdog's state dir, PERUN_LANDING_DIR or $XDG_CACHE_HOME/perun/landing-watchdog), keyed on the git common dir so
worktrees share one pointer. Written atomically; it survives the watchdog's stamp pruning (ends in `.lkg.json`). `check <sha>` exits 0 only when <sha> IS the LKG, else 1 with the
untested gap (commits since the LKG; also 1 when none is recorded). `age` prints the LKG age in hours. Side effects: `record` overwrites the pointer.
Policy: `lkg_gate` shadow|enforce|off (land-release.sh, default shadow), `lkg_stale_h` (hours >= 0, 0 = off) for the watchdog alarm.
"""
import hashlib
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import landing_watchdog as lw  # noqa: E402


def path(cwd="."):
    base = os.path.dirname(lw.cache_file(cwd))
    common = os.path.realpath(os.path.join(cwd, lw._run(["git", "rev-parse", "--git-common-dir"], cwd).strip()))
    return os.path.join(base, hashlib.sha1(common.encode()).hexdigest()[:16] + ".lkg.json")


def record(cwd=".", sha=None, now=None):
    """Write the pointer for `sha` (default HEAD) and return it."""
    sha = lw._run(["git", "rev-parse", "--verify", (sha or "HEAD") + "^{commit}"], cwd).strip()
    rec = {"sha": sha, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now or time.time()))}
    tmp = f"{path(cwd)}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, path(cwd))
    return rec


def read(cwd="."):
    """The recorded pointer, or None when absent or unreadable."""
    try:
        with open(path(cwd)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def age_h(cwd=".", now=None):
    """Hours since the LKG was recorded, or None when there is none."""
    rec = read(cwd)
    return None if not rec else ((now or time.time()) - lw._ts(rec["utc"])) / 3600


def check(sha, cwd="."):
    """(ok, message): ok only when `sha` is the LKG; otherwise the message names the untested gap."""
    rec = read(cwd)
    if not rec:
        return False, "no last-known-good recorded"
    if rec["sha"] == sha:
        return True, f"{sha[:12]} is the last-known-good ({rec['utc']})"
    r = subprocess.run(["git", "rev-list", "--count", f"{rec['sha']}..{sha}"], cwd=cwd, capture_output=True, text=True)
    anc = subprocess.run(["git", "merge-base", "--is-ancestor", rec["sha"], sha], cwd=cwd, capture_output=True).returncode == 0
    gap = f"{r.stdout.strip()} untested commits since" if anc else "not a descendant of"
    return False, f"{sha[:12]} is not the last-known-good: {gap} {rec['sha'][:12]} ({rec['utc']})"


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "record":
        print(json.dumps(record(sha=argv[2] if len(argv) > 2 else None)))
    elif cmd == "check" and len(argv) > 2:
        ok, msg = check(argv[2])
        print(msg)
        return 0 if ok else 1
    elif cmd == "age":
        a = age_h()
        print("none" if a is None else f"{a:.1f}")
    else:
        print("usage: lkg.py record [sha] | check <sha> | age", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
