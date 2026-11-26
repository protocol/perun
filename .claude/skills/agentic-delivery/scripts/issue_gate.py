#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=agent sessions file issues faster than they close them; gate filing at intake, review=2027-01-30
"""L1 issue-intake gate: the one way an agent files a GitHub issue.

  issue_gate.py file --title T --body-file F --priority P0..P3 --area A [--severity critical|high|medium|low|nit]
  issue_gate.py queue          # print how many capped issues wait, then one title per line

`file` runs `gh issue create` (labels: the priority and `area:A`) only after these checks, in order:
  1. --area must match ^[A-Za-z0-9_.-]+$ (exit 2); severity low or nit is refused: "fold into the next PR" (exit 1).
  2. dedupe: `file_finding.py` (next to this file) on the title, which searches open AND closed issues and recent PRs, so a
     closed issue is a regression to reopen, not a new filing. A match is refused (exit 1); a failed search fails closed (exit 2).
  3. cap, under an flock on `<state>/lock`: 3 agent-filed issues per UTC day; critical/high is exempt. An over-cap issue is
     appended to the queue (title, body, priority, area, severity) instead of filed (exit 3). Otherwise a reservation row is
     written, then the issue is created; if create fails (gh missing, timeout, error) the row is marked failed, so it is not
     counted, and the exit is 2 with a one-line reason. A missing label retries once with no labels and the priority and area
     put in the body (zero setup in a repo without those labels).
Exit 0 = filed (URL printed). No --severity counts as medium.

State dir: $PERUN_DIR, else `<git-common-dir>/perun-issue-gate` (shared by every worktree of a clone), else `.perun` outside git.
Files: issue-filed.jsonl (reservations), issue-queue.jsonl, lock; corrupt lines are skipped.
Side effects: runs file_finding.py and `gh issue create` with env PERUN_ISSUE_GATE=1, the marker finding_guard.py (the PreToolUse
hook that blocks a raw `gh issue create`) accepts; writes the state files.
"""
import argparse
import datetime
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CAP = 3
EXEMPT = ("critical", "high")
HERE = Path(__file__).resolve().parent


def _state():
    if os.environ.get("PERUN_DIR"):
        return Path(os.environ["PERUN_DIR"])
    try:
        r = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return (Path.cwd() / r.stdout.strip()).resolve() / "perun-issue-gate"  # relative output is against the cwd
    except (OSError, subprocess.TimeoutExpired):
        pass
    return Path(".perun")


def _append(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _lines(path):
    out = []
    try:
        for x in path.read_text().splitlines():
            try:
                out.append(json.loads(x))
            except ValueError:
                pass  # corrupt line: skip, never crash the gate
    except OSError:
        pass
    return out


def _create(a, body_file, labels):
    cmd = ["gh", "issue", "create", "--title", a.title, "--body-file", body_file]
    for lb in labels:
        cmd += ["--label", lb]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, env={**os.environ, "PERUN_ISSUE_GATE": "1"})


def file_issue(a):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", a.area):
        print("issue_gate: --area must match ^[A-Za-z0-9_.-]+$; nothing filed.", file=sys.stderr)
        return 2
    if a.severity in ("low", "nit"):
        print(f"refused: severity {a.severity} is not worth an issue; fold into the next PR.", file=sys.stderr)
        return 1
    try:
        body = Path(a.body_file).read_text()
        r = subprocess.run([sys.executable, str(HERE / "file_finding.py"), a.title], capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"issue_gate: cannot check ({e}); nothing filed.", file=sys.stderr)
        return 2
    if r.returncode == 1:
        print("refused: a matching issue or PR exists; comment on or reopen it instead.\n" + r.stdout.strip(), file=sys.stderr)
        return 1
    if r.returncode != 0:
        print("issue_gate: duplicate search failed; nothing filed.", file=sys.stderr)
        return 2
    row = {"title": a.title, "body": body, "priority": a.priority, "area": a.area, "severity": a.severity}
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    exempt = a.severity in EXEMPT
    sd = _state()
    sd.mkdir(parents=True, exist_ok=True)
    filed, rid = sd / "issue-filed.jsonl", time.time_ns()
    with open(sd / "lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        rows = _lines(filed)
        failed = {x.get("id") for x in rows if x.get("failed")}
        n = sum(1 for x in rows if x.get("day") == today and not x.get("exempt") and x.get("id") not in failed)
        if not exempt and n >= CAP:
            _append(sd / "issue-queue.jsonl", row)
            print(f"queued: {CAP} agent-filed issues already today (UTC); see `issue_gate.py queue`.", file=sys.stderr)
            return 3
        _append(filed, {"id": rid, "day": today, "title": a.title, "exempt": exempt})
        tmp = None
        try:
            r = _create(a, a.body_file, [a.priority, f"area:{a.area}"])
            if r.returncode != 0 and "label" in r.stderr.lower():
                with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as t:
                    t.write(f"Priority: {a.priority}\nArea: {a.area}\n\n{body}")
                tmp = t.name
                r = _create(a, tmp, [])
            err = "" if r.returncode == 0 else (r.stderr.strip().splitlines() or ["gh failed"])[-1]
        except (OSError, subprocess.TimeoutExpired) as e:
            r, err = None, str(e).splitlines()[0]
        finally:
            if tmp:
                os.unlink(tmp)
        if err:
            _append(filed, {"id": rid, "failed": True})
            print(f"issue_gate: `gh issue create` failed ({err}); nothing filed.", file=sys.stderr)
            return 2
    print(r.stdout.strip())
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("file")
    f.add_argument("--title", required=True)
    f.add_argument("--body-file", required=True)
    f.add_argument("--priority", required=True, choices=("P0", "P1", "P2", "P3"))
    f.add_argument("--area", required=True)
    f.add_argument("--severity", default="medium", choices=("critical", "high", "medium", "low", "nit"))
    sub.add_parser("queue")
    a = p.parse_args(argv)
    if a.cmd == "queue":
        q = _lines(_state() / "issue-queue.jsonl")
        print(len(q))
        for x in q:
            print(x.get("title", ""))
        return 0
    try:
        return file_issue(a)
    except OSError as e:
        print(f"issue_gate: cannot use the state dir ({str(e).splitlines()[0]}); nothing filed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
