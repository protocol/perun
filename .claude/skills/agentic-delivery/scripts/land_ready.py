#!/usr/bin/env python3
"""land_ready.py — read-only sweep: which open PRs can the train land now, and why not for the rest.

  land_ready.py [--repo OWNER/NAME] [--timeout S]

One line per open PR: `#N ready`, or `#N not ready: <reasons>`. Ready means not draft, no merge conflict, not
BEHIND its base, every check-run green (`surface_check.check_checks`, the repo's one check judge) and commit
status `perun/review` = success on the CURRENT head (posted by `review_status.py`). Reuses `pr_state.read_pr`.
Side effects: none (GET and one GraphQL read per PR). Edge cases: first 100 open PRs only; an unreadable PR
prints `#N not ready: unreadable`. Exit 0 swept, 3 could not list PRs or bad arguments.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gh_rest  # noqa: E402
import pr_state  # noqa: E402  (read_pr, clean)
import surface_check as sc  # noqa: E402

CONTEXT = "perun/review"


def reasons(slug, num, timeout):
    """Why PR `num` (at its current head) is not ready (empty list = ready)."""
    try:
        pr = pr_state.read_pr(slug, num, timeout)
    except pr_state.ReadError:
        return ["unreadable"]
    head = pr["headRefOid"]
    out = []
    if pr.get("isDraft"):
        out.append("draft")
    if pr.get("mergeable") == "CONFLICTING":
        out.append("merge conflict")
    elif pr.get("mergeable") != "MERGEABLE":
        out.append("mergeable unknown")
    if pr.get("mergeStateStatus") == "BEHIND":
        out.append("behind base")
    code, _, why = sc.check_checks(slug, head, [], timeout)
    if code != sc.PASS:
        out.append("checks: " + pr_state.clean(str(why).replace("—", "-"), 120))
    rc, body, _ = sc._gh(["gh", "api", f"repos/{slug}/commits/{head}/status?per_page=100"], timeout)
    try:
        sts = {s["context"]: s["state"] for s in json.loads(body).get("statuses", [])} if rc == 0 else None
    except (ValueError, KeyError, TypeError, AttributeError):
        sts = None
    if sts is None:
        out.append(f"{CONTEXT} unreadable")
    elif sts.get(CONTEXT) != "success":
        out.append(f"{CONTEXT} " + (pr_state.clean(sts[CONTEXT], 20) if CONTEXT in sts else "missing") + " on current head")
    return out


def main(argv):
    """CLI entry point; returns the exit code."""
    ap = argparse.ArgumentParser(prog="land_ready.py", description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default="", help="OWNER/NAME (default: the origin remote)")
    ap.add_argument("--timeout", type=float, default=60.0, help="seconds per gh call")
    try:
        a = ap.parse_args(argv)
    except SystemExit as exc:
        return 3 if exc.code else 0
    slug = a.repo or gh_rest._slug() or ""
    if not sc.REPO_SLUG_RE.match(slug):
        print("land_ready: need OWNER/NAME (--repo, or an origin remote on GitHub)", file=sys.stderr)
        return 3
    rc, out, err = sc._gh(["gh", "api", f"repos/{slug}/pulls?state=open&per_page=100"], a.timeout)
    try:
        prs = json.loads(out) if rc == 0 else None
    except ValueError:
        prs = None
    if not isinstance(prs, list):
        print(f"land_ready: cannot list open PRs (rc {rc}): {err.strip()[:200]}", file=sys.stderr)
        return 3
    if len(prs) == 100:
        print("land_ready: warning: 100 open PRs listed, any beyond the first 100 are not swept", file=sys.stderr)
    for p in prs:
        why = reasons(slug, p["number"], a.timeout)
        print(f"#{p['number']} " + ("not ready: " + "; ".join(why) if why else "ready"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
