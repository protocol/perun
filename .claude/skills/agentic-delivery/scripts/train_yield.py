#!/usr/bin/env python3
"""train_yield.py — train landing yield and per-PR re-ride count, from a small JSONL ledger.

WHY: merges per hour hides a train that keeps starting and landing nothing. One measured fleet ran 17 trains that carried
PRs which stayed open; 3 landed (about 15%), and one PR rode 22 trains. That points at infra (a timebox, host load),
not at the PR, and only the yield and the re-ride count show it.

  train_yield.py record TAG "PR PR ..." "LANDED_PR ..." [OUTCOME ["PR:SHA ..."]]   append one started train (train_land.sh calls this on exit)
  train_yield.py report                                   print yield and the PRs that re-rode, then the alarm if any
  train_yield.py solo PR:SHA...                           print the PRs that rode >= TRAIN_SOLO_AFTER (default 3, 0 = off) culprit-less ("unpinned"/"flaky") trains at that same head SHA

Ledger: env PERUN_TRAIN_LEDGER, else <git-common-dir>/train-yield.jsonl, one {"tag","prs","landed","outcome","heads"} per started train
("heads" = the head SHA each PR rode with; a record without it never counts toward `solo`).
Only the last WINDOW records count; a record with outcome "red" (BASE RED or a CULPRIT: the base or a PR failed, not infra) is
skipped. A record with outcome "unpinned" (every PR passed the failing ids alone, no culprit) or "flaky" (no REAL id, nothing blamed) still counts as a ride and is what
`solo` counts; the "may be an intermittent regression" CANT is ledgered as neither (outcome ""). yield = trains with at least one PR landed / trains started. A PR's re-rides = trains it rode minus one, for PRs that
never landed in the window. alarm() returns one line when at least MIN_TRAINS trains ran and yield < YIELD_FLOOR, or any PR
re-rode >= RERIDE_AT, else None;
zero trains, a missing ledger and unreadable lines give None (never a divide by zero). Side effects: record appends one line.
"""
import json
import os
import subprocess
import sys

WINDOW, YIELD_FLOOR, RERIDE_AT, MIN_TRAINS, SOLO_AT = 50, 0.5, 5, 4, 3
SOLO_OUTCOMES = ("flaky", "unpinned")  # culprit-less ride outcomes that `solo` counts


def ledger_path(cwd=None):
    """Ledger file: env PERUN_TRAIN_LEDGER, else under the git common dir of cwd."""
    p = os.environ.get("PERUN_TRAIN_LEDGER")
    if p:
        return p
    top = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=cwd, capture_output=True, text=True, check=True)
    return os.path.join(top.stdout.strip(), "train-yield.jsonl")


def record(path, tag, prs, landed, outcome="", heads=None):
    """Append one started train. `heads` ({pr: head sha} each PR rode with) is stored when given."""
    r = {"tag": tag, "prs": [str(p) for p in prs], "landed": [str(p) for p in landed], "outcome": outcome}
    if heads:
        r["heads"] = {str(p): h for p, h in heads.items()}
    with open(path, "a") as f:
        f.write(json.dumps(r) + "\n")


def parse_heads(tokens):
    """{pr: sha} from `PR:SHA` tokens; a token without a sha maps to "" (never matches a recorded head)."""
    return {t.partition(":")[0]: t.partition(":")[2] for t in tokens if t.partition(":")[0]}


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


def solo(path, heads, at=None):
    """The PRs in `heads` ({pr: current head sha}) that never landed and rode >= `at` trains (default $TRAIN_SOLO_AFTER, else SOLO_AT) that ended on
    culprit-less reds (outcome "unpinned" or "flaky") WITH THAT SAME HEAD: a ride whose recorded head differs from the PR's current head, or has none, is not counted.

    Those PRs were never blamed for anything, so train_land.sh lands them alone (after a CI check of the head) instead of putting them on another
    union. 0 = off; a missing ledger, an unreadable line or a bad env value gives [] (never raises)."""
    try:
        at = int(os.environ.get("TRAIN_SOLO_AFTER", SOLO_AT) if at is None else at)
        with open(path) as f:
            lines = f.read().splitlines()[-WINDOW:]
    except (OSError, ValueError):
        return []
    n, done = {}, set()
    for ln in lines:
        try:
            r = json.loads(ln)
            done |= set(map(str, r["landed"]))
            if r.get("outcome") in SOLO_OUTCOMES:
                for p in set(map(str, r["prs"])):
                    if heads.get(p) and r.get("heads", {}).get(p) == heads[p]:
                        n[p] = n.get(p, 0) + 1
        except (ValueError, KeyError, TypeError, AttributeError):
            continue
    return [p for p in heads if at > 0 and p not in done and n.get(p, 0) >= at]


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
        if argv[:1] == ["record"] and len(argv) in (4, 5, 6):
            record(path, argv[1], argv[2].split(), argv[3].split(), argv[4] if len(argv) > 4 else "", parse_heads(argv[5].split()) if len(argv) == 6 else None)
            return 0
        if argv[:1] == ["solo"]:
            print(" ".join(solo(path, parse_heads(argv[1:]))))
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
