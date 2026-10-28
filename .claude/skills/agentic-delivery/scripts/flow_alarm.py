#!/usr/bin/env python3
"""flow_alarm.py — three flow checks that read the delivery queue, not the code.

  flow_alarm.py                      PreToolUse(Bash) hook (stdin JSON): STOP STARTING. Denies (exit 2) `gh pr create` while
                                     ready-but-unmerged PRs >= PERUN_STOP_STARTING_READY (default 5): waiting work is queue, and
                                     a new PR only lengthens it. Override for priority work: `# priority: <reason>` in the command.
                                     Non-PR commands, a failed `gh`, unparseable input -> allow (fail open).
  flow_alarm.py symptom [--hours H] [--red-since TS]
                                     ONE alarm instead of a monitor per invariant. Prints `ALARM flow: N ready PR(s) and nothing
                                     merged in Xh` when ready PRs exist and the last merge is older than H (default 2), and
                                     `ALARM flow: trunk red for Xh` when --red-since (ISO-8601 or epoch) is older than 1h. Exit 1
                                     on any ALARM, 0 healthy, 2 when `gh` fails (fail closed: an unread queue is not healthy).
  flow_alarm.py split FILE.json      value-stream split BEFORE optimizing agents. FILE is a list of {"queuedAt","startedAt",
                                     "readyAt","mergedAt"} (ISO-8601, from the tracker/PR export). Prints median hours for
                                     `waiting-to-start`, `coding`, `ready-to-merged` (queued->started, started->ready, ready->
                                     merged) and the largest stage; rows missing a timestamp are skipped. Exit 2 on bad input.

Ready = open, not draft, at least one check and every check SUCCESS/NEUTRAL/SKIPPED. `PERUN_GH` overrides the gh binary (tests).
`--now EPOCH` pins the clock. Side effects: none (read-only).
"""
import json
import os
import re
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

OK = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def ts(v):
    s = str(v)
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()


def gh_json(*a, timeout=60):
    r = subprocess.run([os.environ.get("PERUN_GH", "gh"), *a], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "gh failed")
    return json.loads(r.stdout or "[]")


def ready(pr):
    ch = pr.get("statusCheckRollup") or []
    return (not pr.get("isDraft") and bool(ch)
            and all((c.get("conclusion") or c.get("state") or "").upper() in OK for c in ch))


def open_ready(timeout=60):
    return sum(ready(p) for p in gh_json("pr", "list", "--state", "open", "--limit", "100", "--json", "isDraft,statusCheckRollup",
                                         timeout=timeout))


def hook():
    try:
        data = json.load(sys.stdin)
        cmd = (data.get("tool_input") or {}).get("command") or ""
        if data.get("tool_name", "Bash") != "Bash" or not re.search(r"\bgh\s+pr\s+create\b", cmd) or "# priority:" in cmd:
            return 0
        n, cap = open_ready(10), int(os.environ.get("PERUN_STOP_STARTING_READY", "5"))
    except subprocess.TimeoutExpired:
        print("flow_alarm: gh timed out (10s); stop-starting check skipped this call", file=sys.stderr)
        return 0
    except Exception:
        return 0
    if n >= cap:
        print(f"Blocked `gh pr create`: {n} ready-but-unmerged PRs (cap {cap}). Waiting work is queue; help it land "
              "(review, merge, unblock) before starting more. Priority work: add `# priority: <reason>` to the command.",
              file=sys.stderr)
        return 2
    return 0


def symptom(argv, now):
    hrs = float(argv[argv.index("--hours") + 1]) if "--hours" in argv else 2.0
    try:
        n = open_ready()
        last = gh_json("pr", "list", "--state", "merged", "--limit", "1", "--json", "mergedAt")
        red = ts(argv[argv.index("--red-since") + 1]) if "--red-since" in argv else None
    except (RuntimeError, OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
        print(f"flow_alarm: could not read the queue: {e}", file=sys.stderr)
        return 2
    age = (now - ts(last[0]["mergedAt"])) / 3600 if last else float("inf")
    bad = 0
    if n and age > hrs:
        print(f"ALARM flow: {n} ready PR(s) and nothing merged in {'ever' if age == float('inf') else f'{age:.1f}h'}")
        bad = 1
    if red is not None and now - red > 3600:
        print(f"ALARM flow: trunk red for {(now - red) / 3600:.1f}h")
        bad = 1
    return bad


def split(path):
    try:
        rows = json.load(open(path))
        names = (("waiting-to-start", "queuedAt", "startedAt"), ("coding", "startedAt", "readyAt"),
                 ("ready-to-merged", "readyAt", "mergedAt"))
        med = {n: [] for n, _, _ in names}
        for r in rows:
            if all(r.get(k) for k in ("queuedAt", "startedAt", "readyAt", "mergedAt")):
                for n, a, b in names:
                    med[n].append((ts(r[b]) - ts(r[a])) / 3600)
        if not med["coding"]:
            raise ValueError("no row has all four timestamps")
    except (OSError, ValueError, TypeError, AttributeError) as e:
        print(f"flow_alarm: {e}", file=sys.stderr)
        return 2
    m = {n: statistics.median(v) for n, v in med.items()}
    for n, v in m.items():
        print(f"{n}\tmedian_h={v:.1f}")
    print(f"largest\t{max(m, key=m.get)}\trows={len(med['coding'])}")
    return 0


def main(argv):
    now = float(argv[argv.index("--now") + 1]) if "--now" in argv else time.time()
    if not argv or argv[0] == "--now":
        return hook()
    if argv[0] == "symptom":
        return symptom(argv, now)
    if argv[0] == "split" and len(argv) >= 2:
        return split(argv[1])
    print(__doc__.split("\n\n")[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
