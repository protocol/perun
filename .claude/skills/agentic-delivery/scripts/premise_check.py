#!/usr/bin/env python3
"""premise_check.py — before handing PRs or issues to a lane or peer, say which are already done or stale.

  premise_check.py N [N ...] [--repo OWNER/NAME] [--timeout S]

WHY: a handed list is a snapshot that ages (multi-session-coordination.md, "A peer-handed work-partition").
For each number, one `gh api repos/<slug>/issues/N` read (it serves PRs and issues) prints one line:
  `#N PR MERGED|CLOSED|OPEN` or `#N ISSUE OPEN|CLOSED`; an open issue also gets `absent at HEAD: ...` listing the
  backticked file paths and `name()` / snake_case symbols its body cites that this checkout's HEAD does not
  contain (a path missing from the tree, a symbol `git grep -F` does not find). Absent means "premise may have
  drifted, re-read the issue", not "wrong": a file the issue asks you to create is listed too.
Exit 0 when every number is an OPEN PR or an OPEN issue with nothing absent; 1 when any number is MERGED, CLOSED,
absent-flagged or unreadable (`#N UNREADABLE`); 3 on bad arguments. Side effects: none (reads only); needs `gh`
auth or network, else every number reads UNREADABLE. HEAD is the current checkout: fetch first if it lags.
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gh_rest  # noqa: E402  (origin slug)
import surface_check as sc  # noqa: E402  (gh runner with the curl fallback)

TICK = re.compile(r"`([^`\s]+)`")
PATH = re.compile(r"^[\w.-]+(/[\w.-]+)*(/|\.(py|sh|md|json|tsv|ya?ml|js|ts|toml))$")
SYM = re.compile(r"^(\w+\(\)|[a-z]+(_[a-z0-9]+)+)$")  # `fn()` or snake_case; plain words and flags are skipped


def cited(body):
    """(paths, symbols) the issue body cites in backticks, de-duplicated, in order. Pure."""
    toks = list(dict.fromkeys(t.rstrip(".,:;") for t in TICK.findall(body or "")))
    paths = [t for t in toks if PATH.match(t)]
    return paths, [t for t in toks if t not in paths and SYM.match(t)]


def absent(root, body):
    """Cited paths missing from HEAD's tree (as a file, a directory or a bare file name) and cited symbols `git grep -F` cannot find at HEAD."""
    paths, syms = cited(body)
    tree = subprocess.run(["git", "-C", root, "ls-tree", "-r", "--name-only", "HEAD"], capture_output=True, text=True).stdout.splitlines()
    miss = [p for p in paths if not any(f == p or f.startswith(p.rstrip("/") + "/") or f.endswith("/" + p) for f in tree)]
    for s in syms:
        if subprocess.run(["git", "-C", root, "grep", "-qF", s.removesuffix("()"), "HEAD"], capture_output=True).returncode != 0:
            miss.append(s)
    return miss


def line(slug, n, root, timeout):
    """(report line, flagged) for number `n`."""
    rc, out, _ = sc._gh(["gh", "api", f"repos/{slug}/issues/{n}"], timeout)
    try:
        d = json.loads(out)
        state = d["state"]
    except (ValueError, KeyError, TypeError):
        d = None
    if rc != 0 or not isinstance(d, dict):
        return f"#{n} UNREADABLE", True
    if d.get("pull_request"):
        s = "MERGED" if d["pull_request"].get("merged_at") else state.upper()
        return f"#{n} PR {s}", s != "OPEN"
    miss = absent(root, d.get("body")) if state == "open" and root else []  # no local HEAD for another repo
    msg = f"#{n} ISSUE {state.upper()}" + (f"; absent at HEAD: {', '.join(miss)}" if miss else "")
    return msg, state != "open" or bool(miss)


def main(argv):
    """CLI entry point; returns the exit code (0 all clear, 1 something flagged, 3 bad arguments)."""
    ap = argparse.ArgumentParser(prog="premise_check.py", description="Report handed PRs/issues that are already done or stale.")
    ap.add_argument("numbers", type=int, nargs="+")
    ap.add_argument("--repo", default="", help="OWNER/NAME (default: the origin remote)")
    ap.add_argument("--timeout", type=float, default=60.0)
    try:
        a = ap.parse_args(argv)
    except SystemExit as exc:
        return 3 if exc.code else 0
    slug = a.repo or gh_rest._slug() or ""
    if not sc.REPO_SLUG_RE.match(slug):
        print("premise_check: need OWNER/NAME (--repo, or an origin remote on GitHub)", file=sys.stderr)
        return 3
    root = "." if slug == (gh_rest._slug() or "") else None  # --repo names another repo: skip the HEAD check
    res = [line(slug, n, root, a.timeout) for n in a.numbers]
    print("\n".join(r[0] for r in res))
    return int(any(r[1] for r in res))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
