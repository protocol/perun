#!/usr/bin/env python3
"""flake_ledger.py — per-test pass/fail ledger keyed by tree SHA, with a time-boxed quarantine list.

WHY: a test that fails and then passes on the SAME tree is nondeterministic (a flake), not a regression.
`train_flake.sh` triages one run and forgets it; this keeps the history so a repeat offender is quarantined
(reported, non-blocking, owner-reviewed expiry) instead of re-triaged on every train. Stdlib only, never a model.

RULES (deterministic)
  evidence     one record per real run: `SUITE id` (failed in the full gate), `FAIL id` / `PASS id` (a solo re-run, or any
               other single run). Verdict labels (FLAKE/REAL) are not evidence and are ignored.
  flake tree   a tree where one test has >= 1 non-suite FAIL AND >= 1 PASS (0 < solo fails < runs). A suite failure
               followed only by passing solo re-runs is NOT a flake tree (it may be load, or an intermittent regression).
  FLAKY        flake trees >= N (default 3, `--n`): the test has been nondeterministic on N distinct trees.
  consistent   on one tree a test has >= 2 fails (suite fails count) and 0 passes. That is a real failure: it is NEVER
               quarantined, and a quarantined test that is consistent on the checked tree is BLOCKING again (`check`). A
               test whose latest recorded tree is consistent is not added by `quarantine`, even if it flaked before.
  quarantine   id -> {since, expires}. `expires` is a date (default today + 14 days). After it the entry stops
               excusing: the test blocks again until the owner reviews it and runs `renew`. `quarantine` never
               extends an existing entry; only `renew` (the owner's review) does.

COMMANDS (state lives in --dir, default .claude/flake-ledger: ledger.jsonl append-only, quarantine.json, .lock)
  record [--tree T]              stdin lines `SUITE id` / `FAIL id` / `PASS id`. Tree default: `git rev-parse HEAD^{tree}`.
                                 Under flock; a torn (unterminated) last line from a crash is dropped before appending.
                                 Re-recording a log only repeats evidence: counts are per distinct tree, so it is harmless.
  report [--n N]                 per-test table (flake trees, status) plus the quarantine list with expiry state.
  quarantine [--n N] [--days D] [--ticket T] [--max M] [--file-issue]
                                 add FLAKY, non-consistent, unlisted tests, each with an expiry and the tracking ticket T
                                 (`report` flags an entry without one as NO-TICKET). Prints `QUARANTINE id expires=DATE
                                 [ticket=T]`. More than M entries (default 10) prints `FULL quarantine list`, exits 1 and, with
                                 --file-issue, files a P0 issue (`gh issue create --label P0`) instead of leaving a note.
  renew ID (--days D | --expires DATE)   owner review: set a new expiry for a listed id.
  check ID... [--tree T] [--quarantine -]
                                 `QUARANTINED id (expires DATE)` (non-blocking, report it) or `BLOCKING id (reason)`;
                                 exit 1 when any id is BLOCKING, 2 on usage/IO error (fails closed). `--quarantine -` reads
                                 the quarantine list from stdin: the caller holds it in memory, read before untrusted code ran
                                 (train_land.sh / train_flake.sh), so no file can be overwritten to forge an entry.
  serial [--n N]                 detector: tests that failed in the full parallel run AND passed solo on >= N distinct trees and
                                 never failed solo on any tree (suite-only failure). Neither a flake nor a real red: prints `SERIAL-CANDIDATE id`;
                                 move it to the serial (one-at-a-time) project the same day. Exit 1 when any candidate.
  serial-move ID...              record tests moved to the serial project (serial-project.txt): excluded from `serial` and `quarantine`,
                                 and `check` reports them BLOCKING (a failure there is a real bug, never excused as a flake).
  guard                          exit 2 when --dir resolves under the cwd or the git toplevel (a path PR code can write).
DECISION (trust boundary) AND KNOWN CEILING
  Context: the code under test (PR code in BROWSER_CMD / RERUN_CMD) runs as the same user as the train and could write the ledger
  directory to forge a quarantine entry that excuses its own failure. Decision: reduce the easy paths (the train refuses a ledger
  dir under the worktree or git toplevel, never exports the path to PR code, and reads quarantine.json once into memory before any
  PR code runs, passing it on stdin) but do NOT sign the files (no HMAC: the key would have to live where the same user can read it).
  Ceiling: same-uid code that learns the directory by other means (a config file, a guessed path) can still write it. The OS sandbox
  is the boundary: run the train sandboxed with the ledger directory OUTSIDE its write set, and treat a ledger written from
  inside the sandbox as untrusted. Consequence: the quarantine list is only as trustworthy as that directory's write permissions.

`--today YYYY-MM-DD` pins the clock (tests). Exit 2 on bad input; a malformed ledger line is an error, never skipped,
except an unterminated last line (a torn write).
"""
import argparse
import contextlib
import datetime
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

DEFAULT_DIR = ".claude/flake-ledger"
STAMP = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")  # noqa: E731


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


@contextlib.contextmanager
def locked(d):
    """Exclusive flock on <dir>/.lock: serializes every writer (record, quarantine, renew)."""
    Path(d).mkdir(parents=True, exist_ok=True)
    with open(Path(d) / ".lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def load(d):
    """Return (stats, latest): stats[test][tree] = [solo fails, passes, suite fails]; latest[test] = tree of its newest record."""
    stats, latest = defaultdict(lambda: defaultdict(lambda: [0, 0, 0])), {}
    p = Path(d) / "ledger.jsonl"
    if not p.exists():
        return stats, latest
    text = p.read_text()
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    elif lines:
        lines.pop()  # unterminated last line = torn write, not evidence
    for n, line in enumerate(lines, 1):
        try:
            r = json.loads(line)
            stats[r["test"]][r["tree"]][2 if r.get("suite") else 0 if r["result"] == "fail" else 1] += 1
            latest[r["test"]] = r["tree"]
        except (ValueError, KeyError, TypeError):
            die(f"{p}:{n}: malformed ledger line; refusing to guess")
    return stats, latest


def load_q(path):
    p = Path(path)
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except ValueError:
        die(f"{p}: not valid JSON")


def load_moved(d):
    """Tests already moved to the serial project (serial-project.txt, one id per line). A failure there is a real bug, never a flake."""
    p = Path(d) / "serial-project.txt"
    return set(p.read_text().split("\n")) - {""} if p.exists() else set()


def save_q(d, q):
    """Write quarantine.json via a unique temp file + os.replace (callers hold the flock)."""
    fd, tmp = tempfile.mkstemp(dir=d, prefix="quarantine.", suffix=".tmp")
    with os.fdopen(fd, "w") as fh:
        fh.write(json.dumps(q, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, Path(d) / "quarantine.json")


def flake_trees(stats, test):
    return sum(1 for f, p, _ in stats[test].values() if f and p)


def serial_trees(stats, test):
    if any(f for f, _, _ in stats[test].values()):  # any solo fail on any tree: a real bug or flake, not a serial-only failure
        return 0
    return sum(1 for f, p, su in stats[test].values() if su and p)  # suite fail + solo PASS record (PASS rows are always solo runs)


def consistent(stats, test, tree):
    f, p, s = stats[test].get(tree, (0, 0, 0))
    return f + s >= 2 and p == 0


def day(s):
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        die(f"bad date {s!r}, want YYYY-MM-DD")


def record(d, tree, text):
    rows = []
    for line in text.splitlines():
        m = re.match(r"(SUITE|FAIL|PASS) +(\S.*?)\s*$", line)
        if m:
            r = {"tree": tree, "test": m[2], "result": "pass" if m[1] == "PASS" else "fail", "ts": STAMP()}
            rows.append(json.dumps({**r, "suite": True} if m[1] == "SUITE" else r))
    if rows:
        with locked(d), open(Path(d) / "ledger.jsonl", "a+b") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            if size:  # drop a torn last line (crash mid-append) so the new rows start on a fresh line
                fh.seek(0)
                data = fh.read()
                if not data.endswith(b"\n"):
                    fh.truncate(data.rfind(b"\n") + 1)
                    fh.seek(0, os.SEEK_END)
            fh.write(("\n".join(rows) + "\n").encode())
    return len(rows)


def under(path, root):
    return path == root or path.startswith(root.rstrip("/") + "/")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--today")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("record"); s.add_argument("--tree")
    s = sub.add_parser("report"); s.add_argument("--n", type=int, default=3)
    s = sub.add_parser("serial"); s.add_argument("--n", type=int, default=3)
    s = sub.add_parser("serial-move"); s.add_argument("ids", nargs="+")
    s = sub.add_parser("quarantine"); s.add_argument("--n", type=int, default=3); s.add_argument("--days", type=int, default=14)
    s.add_argument("--ticket", default=""); s.add_argument("--max", type=int, default=10); s.add_argument("--file-issue", action="store_true")
    s = sub.add_parser("renew"); s.add_argument("id"); g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--days", type=int); g.add_argument("--expires")
    s = sub.add_parser("check"); s.add_argument("ids", nargs="+"); s.add_argument("--tree"); s.add_argument("--quarantine", choices=["-"])
    sub.add_parser("guard")
    a = ap.parse_args(argv)
    today = day(a.today) if a.today else datetime.date.today()
    qpath = Path(a.dir) / "quarantine.json"

    if a.cmd == "guard":
        real, roots = os.path.realpath(a.dir), {os.path.realpath(os.getcwd())}
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        if top.returncode == 0 and top.stdout.strip():
            roots.add(os.path.realpath(top.stdout.strip()))
        for r in sorted(roots):
            if under(real, r):
                die(f"FLAKE_LEDGER_DIR {a.dir!r} resolves under {r}, a path the code under test can write; use a directory outside the worktree")
        return 0
    if a.cmd == "record":
        tree = tree_of(a.tree)
        print(f"recorded {record(a.dir, tree, sys.stdin.read())} result(s) for tree {tree[:12]}")
        return 0
    if a.cmd == "serial-move":
        with locked(a.dir):
            ids = sorted(load_moved(a.dir) | set(a.ids))
            fd, tmp = tempfile.mkstemp(dir=a.dir, prefix="serial-project.", suffix=".tmp")  # tmp + replace: a crash never truncates the moved set
            with os.fdopen(fd, "w") as fh:
                fh.write("\n".join(ids) + "\n")
            os.replace(tmp, Path(a.dir) / "serial-project.txt")
        print(f"serial-project: {len(ids)} test(s)")
        return 0
    if a.cmd == "renew":
        with locked(a.dir):
            q = load_q(qpath)
            if a.id not in q:
                die(f"{a.id!r} is not quarantined")
            q[a.id]["expires"] = (day(a.expires) if a.expires else today + datetime.timedelta(days=a.days)).isoformat()
            save_q(a.dir, q)
        print(f"RENEWED {a.id} expires={q[a.id]['expires']}")
        return 0
    if a.cmd == "quarantine":
        with locked(a.dir):
            stats, latest = load(a.dir)
            q, moved = load_q(qpath), load_moved(a.dir)
            for t in sorted(stats):
                if t not in q and t not in moved and flake_trees(stats, t) >= a.n and not consistent(stats, t, latest[t]):
                    q[t] = {"since": today.isoformat(), "expires": (today + datetime.timedelta(days=a.days)).isoformat(), "ticket": a.ticket}
                    print(f"QUARANTINE {t} expires={q[t]['expires']}" + (f" ticket={a.ticket}" if a.ticket else ""))
            save_q(a.dir, q)
        if len(q) > a.max:  # a full list is a P0 to fix or delete tests, not a note for a human to read
            print(f"FULL quarantine list: {len(q)} > {a.max}")
            if a.file_issue:
                r = subprocess.run(["gh", "issue", "create", "--label", "P0", "--title", f"Quarantine list full ({len(q)} > {a.max}): fix or delete flaky tests",
                                    "--body", "The flake quarantine list is over its cap. Fix or delete tests until it is at or under the cap; each entry needs a ticket and an expiry."],
                                   capture_output=True, text=True)
                print(r.stdout.strip() or f"issue not filed: {r.stderr.strip()}")
            return 1
        return 0

    stats, latest = load(a.dir)
    if a.cmd == "report":
        q = load_q(qpath)
        for t in sorted(stats):
            ft = flake_trees(stats, t)
            status = "consistent-fail" if consistent(stats, t, latest[t]) else "FLAKY" if ft >= a.n else "watch" if ft else "ok"
            print(f"{status}\t{t}\tflake_trees={ft}\ttrees={len(stats[t])}")
        for t, e in sorted(q.items()):
            print(f"{'EXPIRED' if day(e['expires']) < today else 'QUARANTINED'}\t{t}\texpires={e['expires']}"
                  + ("" if e.get("ticket") else "\tNO-TICKET"))
        return 0
    if a.cmd == "serial":
        moved = load_moved(a.dir)
        c = [t for t in sorted(stats) if t not in moved and serial_trees(stats, t) >= a.n]
        for t in c:
            print(f"SERIAL-CANDIDATE {t}\tsuite-only-fail-trees={serial_trees(stats, t)}")
        return 1 if c else 0
    try:  # check
        q = json.loads(sys.stdin.read() or "{}") if a.quarantine == "-" else load_q(qpath)
    except ValueError:
        die("--quarantine -: stdin is not valid JSON")
    tree, bad, moved = tree_of(a.tree), 0, load_moved(a.dir)
    for t in a.ids:
        if t in moved:
            why = "serial-project test: a failure here is a real bug, not a flake"
        elif t not in q:
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
