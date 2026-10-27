#!/usr/bin/env python3
"""host_installer.py — track merged host installers that the owner has not applied yet.

A merged change that needs a host-side install (hooks, settings, a launcher) is inactive until someone runs the installer on
the host. `announce <name> <repo-root>` (name from the fixed KNOWN table, e.g. `global-rules`; the command is built here, never passed in) records the merge time (first call wins) and prints one line, `! <cmd>`, for the owner
to paste; `applied <name>` marks it done. `list` prints the pending ones. The landing watchdog adds "Installer unapplied: ..."
when a pending installer is older than policy `installer_unapplied_h` (hours >= 0, 0 = off, default).
Never runs the command and never edits permissions: the owner runs it; a classifier or permission prompt is not bypassed.
State: `<landing cache>/installers.json` (machine-wide, written atomically). Corrupt or unreadable state fires the alarm instead of reading as empty, and announce copies it to `installers.json.corrupt.<time>` before replacing it.
Wired: perun_auto_update.py announces `global-rules` after an update that changed the rules scripts; `install.sh --global-rules` marks it applied.
"""
import json
import os
import shlex
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import landing_watchdog as lw  # noqa: E402

LINE = "Installer unapplied: {n} merged {h:.1f} h ago (limit {t} h), inactive until the owner runs: ! {c}"
BAD = "Installer state unreadable ({e}): treat every merged installer as unapplied and re-run its announce."
# Fixed commands only: a caller names an installer, never supplies the command text.
KNOWN = {"global-rules": lambda root: ["bash", os.path.join(root, "install.sh"), "--global-rules"]}


def path():
    base = os.environ.get("PERUN_LANDING_DIR") or os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "perun", "landing-watchdog")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "installers.json")


def read():
    """Pending-state dict ({} when no file). Raises ValueError on a corrupt or unreadable file: the caller must not treat that as empty."""
    try:
        with open(path()) as f:
            d = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        raise ValueError(str(e)[:80])
    if not isinstance(d, dict):
        raise ValueError("not an object")
    return d


def _write(d):
    tmp = f"{path()}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, path())


def announce(name, root, now=None):
    """Record installer `name` (a KNOWN key) as merged-and-pending (an existing pending entry keeps its first time); return the owner line.
    A corrupt state file is copied to `installers.json.corrupt.<time>` before it is replaced."""
    cmd = shlex.join(KNOWN[name](str(root)))
    try:
        d = read()
    except ValueError:
        if os.path.exists(path()):
            shutil.copy2(path(), f"{path()}.corrupt.{int(now or time.time())}")
        d = {}
    if name not in d or d[name].get("applied"):
        d[name] = {"cmd": cmd, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now or time.time())), "applied": False}
        _write(d)
    return "! " + d[name]["cmd"]


def applied(name):
    try:
        d = read()
    except ValueError:
        return False
    if name in d:
        d[name]["applied"] = True
        _write(d)
    return name in d


def alarm(limit=0, now=None):
    """Alarm line for the oldest pending installer past `limit` hours, or None (limit 0 = off). Unreadable state alarms, never reads as empty."""
    if not limit:
        return None
    try:
        d = read()
    except ValueError as e:
        return BAD.format(e=e)
    t = now or time.time()
    old = [x for x in (((t - lw._ts(v["utc"])) / 3600, n) for n, v in d.items() if not v.get("applied")) if x[0] > limit]
    if not old:
        return None
    a, n = max(old)
    return LINE.format(n=n, h=a, t=limit, c=d[n]["cmd"])


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "announce" and len(argv) == 4 and argv[2] in KNOWN:
        print(announce(argv[2], argv[3]))
    elif cmd == "applied" and len(argv) == 3:
        return 0 if applied(argv[2]) else 1
    elif cmd == "list":
        try:
            for n, v in read().items():
                if not v.get("applied"):
                    print(f"{n}\t{v['utc']}\t! {v['cmd']}")
        except ValueError as e:
            print(BAD.format(e=e))
            return 1
    else:
        print("usage: host_installer.py announce <name> <repo-root> | applied <name> | list", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
