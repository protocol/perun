#!/usr/bin/env python3
"""train_yield.py — train landing yield and per-PR re-ride count, from a small JSONL ledger.

WHY: merges per hour hides a train that keeps starting and landing nothing. One measured fleet ran 17 trains that carried
PRs which stayed open; 3 landed (about 15%), and one PR rode 22 trains. That points at infra (a timebox, host load),
not at the PR, and only the yield and the re-ride count show it.

  train_yield.py record TAG "PR PR ..." "LANDED_PR ..." [red]   append one started train (train_land.sh calls this on exit)
  train_yield.py report                                   print yield and the PRs that re-rode, then the alarm if any

Ledger: env PERUN_TRAIN_LEDGER, else <git-common-dir>/train-yield.jsonl, one {"tag","prs","landed","outcome"} per started train.
Only the last WINDOW records count; a record with outcome "red" (BASE RED or a CULPRIT: the base or a PR failed, not infra) is
skipped. yield = trains with at least one PR landed / trains started. A PR's re-rides = trains it rode minus one, for PRs that
never landed in the window. alarm() returns one line when at least MIN_TRAINS trains ran and yield < YIELD_FLOOR, or any PR
re-rode >= RERIDE_AT, else None;
zero trains, a missing ledger and unreadable lines give None (never a divide by zero). Side effects: record appends one line.
"""
import json
import os
import subprocess
import sys

WINDOW, YIELD_FLOOR, RERIDE_AT, MIN_TRAINS = 50, 0.5, 5, 4


def ledger_path(cwd=None):
    """Ledger file: env PERUN_TRAIN_LEDGER, else under the git common dir of cwd."""
    p = os.environ.get("PERUN_TRAIN_LEDGER")
    if p:
        return p
    top = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd, capture_output=True, text=True, check=True)
    return os.path.join(top.stdout.strip(), "train-yield.jsonl")


def record(path, tag, prs, landed, outcome=""):
    """Append one started train."""
    with open(path, "a") as f:
        f.write(json.dumps({"tag": tag, "prs": [str(p) for p in prs], "landed": [str(p) for p in landed], "outcome": outcome}) + "\n")


def stats(path):
    """(started, landed_trains, {pr: re-rides}) over the last WINDOW records; (0, 0, {}) when the ledger is missing."""
    try:
        with open(path) as f:
            lines = f.read().splitlines()[-WINDOW:]
    except OSError:
        return 0, 0, {}
    recs = []
    for ln in lines:
        try:
            r = json.loads(ln)
            if r.get("outcome") != "red":
                recs.append((list(map(str, r["prs"])), list(map(str, r["landed"]))))
        except (ValueError, KeyError, TypeError):
            continue
    done = {p for _, landed in recs for p in landed}
    rides = {}
    for prs, _ in recs:
        for p in set(prs) - done:
            rides[p] = rides.get(p, 0) + 1
    return len(recs), sum(bool(landed) for _, landed in recs), {p: n - 1 for p, n in rides.items() if n > 1}


def alarm(path):
    """One warning line, or None."""
    started, landed, rr = stats(path)
    if not started:
        return None
    worst = max(rr, key=rr.get) if rr else None
    low, ridden = started >= MIN_TRAINS and landed / started < YIELD_FLOOR, worst is not None and rr[worst] >= RERIDE_AT
    if not (low or ridden):
        return None
    return (f"Train landing yield: {landed} of {started} trains landed a PR ({100 * landed // started}%)"
            + (f", PR #{worst} re-rode {rr[worst]} times" if ridden else "")
            + ". This points at infra (timebox or load), not the PR: check stage timeouts and host load before re-running.")


def main(argv):
    try:
        path = ledger_path()
        if argv[:1] == ["record"] and len(argv) in (4, 5):
            record(path, argv[1], argv[2].split(), argv[3].split(), argv[4] if len(argv) == 5 else "")
            return 0
        if argv[:1] == ["report"]:
            s, l, rr = stats(path)
            print(f"trains started={s} landed={l} yield={l / s:.2f}" if s else "trains started=0")
            print("re-rides: " + (", ".join(f"#{p}={n}" for p, n in sorted(rr.items())) or "none"))
            print(alarm(path) or "ok")
            return 0
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"train_yield: {e}", file=sys.stderr)
        return 0  # a ledger problem never blocks landing
    print(__doc__.split("\n")[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
