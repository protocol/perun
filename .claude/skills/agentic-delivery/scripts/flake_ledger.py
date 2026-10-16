#!/usr/bin/env python3
"""flake_ledger.py — per-test pass/fail ledger keyed by tree SHA, with a time-boxed quarantine list.

WHY: a test that fails and then passes on the SAME tree is nondeterministic (a flake), not a regression.
`train_flake.sh` triages one run and forgets it; this keeps the history so a repeat offender is quarantined
(reported, non-blocking, owner-reviewed expiry) instead of re-triaged on every train. Stdlib only, never a model.

RULES (deterministic)
  flake tree   a tree where one test has >= 1 fail AND >= 1 pass (either order).
  FLAKY        flake trees >= N (default 3, `--n`): the test has been nondeterministic on N distinct trees.
  consistent   on one tree a test has >= 2 fails and 0 passes. That is a real failure: it is NEVER quarantined, and a
               quarantined test that is consistent on the checked tree is BLOCKING again (`check`). A test whose latest
               recorded tree is consistent is not added by `quarantine`, even if it flaked before.
  quarantine   id -> {since, expires}. `expires` is a date (default today + 14 days). After it the entry stops
               excusing: the test blocks again until the owner reviews it and runs `renew`. `quarantine` never
               extends an existing entry; only `renew` (the owner's review) does.

COMMANDS (state lives in --dir, default .claude/flake-ledger: ledger.jsonl append-only, quarantine.json)
  record [--tree T]              stdin lines `PASS id` / `FAIL id` / `FLAKE id...` / `REAL id` (train_flake.sh output; FLAKE =
                                 one fail + one pass, REAL = two fails). Tree default: `git rev-parse HEAD^{tree}`.
                                 Re-recording a log only repeats evidence: counts are per distinct tree, so it is harmless.
  report [--n N]                 per-test table (flake trees, status) plus the quarantine list with expiry state.
  quarantine [--n N] [--days D]  add FLAKY, non-consistent, unlisted tests. Prints `QUARANTINE id expires=DATE`.
  renew ID (--days D | --expires DATE)   owner review: set a new expiry for a listed id.
  check ID... [--tree T]         `QUARANTINED id (expires DATE)` (non-blocking, report it) or `BLOCKING id (reason)`;
                                 exit 1 when any id is BLOCKING, 2 on usage/IO error (fails closed).
`--today YYYY-MM-DD` pins the clock (tests). Exit 2 on bad input; a malformed ledger line is an error, never skipped.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_DIR = ".claude/flake-ledger"
VERB = {"PASS": ("pass",), "FAIL": ("fail",), "FLAKE": ("fail", "pass"), "REAL": ("fail", "fail")}


def die(msg):
    print(f"flake_ledger: {msg}", file=sys.stderr)
    sys.exit(2)


def tree_of(arg):
    if arg:
        return arg
    r = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], capture_output=True, text=True)
    if r.returncode:
        die("no --tree and `git rev-parse HEAD^{tree}` failed")
    return r.stdout.strip()


def load(d):
    """Return (stats, latest): stats[test][tree] = [fails, passes]; latest[test] = tree of its newest record."""
    stats, latest = defaultdict(lambda: defaultdict(lambda: [0, 0])), {}
    p = Path(d) / "ledger.jsonl"
    if not p.exists():
        return stats, latest
    for n, line in enumerate(p.read_text().splitlines(), 1):
        try:
            r = json.loads(line)
            stats[r["test"]][r["tree"]][0 if r["result"] == "fail" else 1] += 1
            latest[r["test"]] = r["tree"]
        except (ValueError, KeyError, TypeError):
            die(f"{p}:{n}: malformed ledger line; refusing to guess")
    return stats, latest


def load_q(d):
    p = Path(d) / "quarantine.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except ValueError:
        die(f"{p}: not valid JSON")


def save_q(d, q):
    p = Path(d) / "quarantine.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(q, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, p)


def flake_trees(stats, test):
    return sum(1 for f, p in stats[test].values() if f and p)


def consistent(stats, test, tree):
    f, p = stats[test].get(tree, (0, 0))
    return f >= 2 and p == 0


def day(s):
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        die(f"bad date {s!r}, want YYYY-MM-DD")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--today")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("record"); s.add_argument("--tree")
    s = sub.add_parser("report"); s.add_argument("--n", type=int, default=3)
    s = sub.add_parser("quarantine"); s.add_argument("--n", type=int, default=3); s.add_argument("--days", type=int, default=14)
    s = sub.add_parser("renew"); s.add_argument("id"); g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--days", type=int); g.add_argument("--expires")
    s = sub.add_parser("check"); s.add_argument("ids", nargs="+"); s.add_argument("--tree")
    a = ap.parse_args(argv)
    today = day(a.today) if a.today else datetime.date.today()

    if a.cmd == "record":
        tree, rows = tree_of(a.tree), []
        for line in sys.stdin.read().splitlines():
            m = re.match(r"(PASS|FAIL|FLAKE|REAL) +(.*?)(?: \(failed \d+ of \d+ alone\))?\s*$", line)
            if m and m[2]:
                rows += [json.dumps({"tree": tree, "test": m[2], "result": r, "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}) for r in VERB[m[1]]]
        if rows:
            Path(a.dir).mkdir(parents=True, exist_ok=True)
            with open(Path(a.dir) / "ledger.jsonl", "a") as fh:
                fh.write("\n".join(rows) + "\n")
        print(f"recorded {len(rows)} result(s) for tree {tree[:12]}")
        return 0

    stats, latest = load(a.dir)
    q = load_q(a.dir)
    if a.cmd == "report":
        for t in sorted(stats):
            ft = flake_trees(stats, t)
            status = "consistent-fail" if consistent(stats, t, latest[t]) else "FLAKY" if ft >= a.n else "watch" if ft else "ok"
            print(f"{status}\t{t}\tflake_trees={ft}\ttrees={len(stats[t])}")
        for t, e in sorted(q.items()):
            print(f"{'EXPIRED' if day(e['expires']) < today else 'QUARANTINED'}\t{t}\texpires={e['expires']}")
        return 0
    if a.cmd == "quarantine":
        for t in sorted(stats):
            if t not in q and flake_trees(stats, t) >= a.n and not consistent(stats, t, latest[t]):
                q[t] = {"since": today.isoformat(), "expires": (today + datetime.timedelta(days=a.days)).isoformat()}
                print(f"QUARANTINE {t} expires={q[t]['expires']}")
        save_q(a.dir, q)
        return 0
    if a.cmd == "renew":
        if a.id not in q:
            die(f"{a.id!r} is not quarantined")
        q[a.id]["expires"] = (day(a.expires) if a.expires else today + datetime.timedelta(days=a.days)).isoformat()
        save_q(a.dir, q)
        print(f"RENEWED {a.id} expires={q[a.id]['expires']}")
        return 0
    tree, bad = tree_of(a.tree), 0  # check
    for t in a.ids:
        if t not in q:
            why = "not quarantined"
        elif day(q[t]["expires"]) < today:
            why = f"quarantine expired {q[t]['expires']}; owner review needed"
        elif t in stats and consistent(stats, t, tree):
            why = "fails consistently on this tree (real failure)"
        else:
            print(f"QUARANTINED {t} (expires {q[t]['expires']})")
            continue
        bad = 1
        print(f"BLOCKING {t} ({why})")
    return bad


if __name__ == "__main__":
    sys.exit(main())
