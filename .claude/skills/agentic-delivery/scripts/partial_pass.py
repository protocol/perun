#!/usr/bin/env python3
"""partial_pass.py — PARTIAL-PASS receipt for a PR whose precheck ended COULD_NOT_CHECK on some checks (#1778).

WHY: a broad-diff PR whose precheck could not finish got no receipt, so it could never enter a merge train.
A PARTIAL-PASS receipt names EXACTLY the checks that went unchecked and records a kill criterion. It is never a
pass: merge_train.py waives only the named checks, admits at most one such PR per train, and `partial-kill`
reverts the PR when a named check fails after merge.

  partial_pass.py write PR --head SHA --unchecked NAME [NAME ...]   write $PARTIAL_DIR/<PR>.json
  partial_pass.py --selftest

Receipt: {"pr", "head", "verdict": "PARTIAL-PASS", "unchecked": [names], "kill": KILL}. Dir: env PARTIAL_DIR
(default .perun/partial). `load` returns the receipt only for an exact head match with a non-empty unchecked list;
anything else (missing, unreadable, stale head, empty list) is None, i.e. no receipt, never a crash.
Side effect: `write` creates one file. Not a signature: an honest-process record, like review_gate receipts.
"""
import argparse
import json
import os
import sys
import tempfile

KILL = "revert-pr-if-an-unchecked-check-fails-post-merge"


def _path(pr, d=None):
    return os.path.join(d or os.environ.get("PARTIAL_DIR", ".perun/partial"), f"{pr}.json")


def write(pr, head, unchecked, d=None):
    """Write the receipt; ValueError on an empty or blank unchecked list (a PARTIAL-PASS must name what it skipped)."""
    names = sorted({u.strip() for u in unchecked if u.strip()})
    if not names or not head:
        raise ValueError("a PARTIAL-PASS names its head and at least one unchecked check")
    p = _path(pr, d)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as fh:
        json.dump({"pr": int(pr), "head": head, "verdict": "PARTIAL-PASS", "unchecked": names, "kill": KILL}, fh)
    return p


def load(pr, head, d=None):
    """The receipt for exactly this head, or None."""
    try:
        with open(_path(pr, d)) as fh:
            r = json.load(fh)
        ok = (r["verdict"] == "PARTIAL-PASS" and r["head"] == head and r["kill"] == KILL
              and isinstance(r["unchecked"], list) and r["unchecked"] and all(isinstance(u, str) for u in r["unchecked"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return r if ok else None


def _selftest():
    with tempfile.TemporaryDirectory() as d:
        write(7, "abc", ["e2e", "lint", "e2e"], d)
        r = load(7, "abc", d)
        assert r["unchecked"] == ["e2e", "lint"] and r["kill"] == KILL, r
        assert load(7, "def", d) is None and load(8, "abc", d) is None
        try:
            write(7, "abc", [" "], d)
        except ValueError:
            pass
        else:
            raise AssertionError("empty unchecked list accepted")
    print("partial_pass selftest: ok")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    w = sub.add_parser("write")
    w.add_argument("pr", type=int)
    w.add_argument("--head", required=True)
    w.add_argument("--unchecked", nargs="+", required=True)
    a = p.parse_args(argv)
    if a.selftest:
        return _selftest()
    if a.cmd != "write":
        p.print_usage()
        return 2
    try:
        print(write(a.pr, a.head, a.unchecked))
    except ValueError as e:
        print(f"ERROR {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
