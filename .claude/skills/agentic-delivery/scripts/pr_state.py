#!/usr/bin/env python3
"""pr_state.py — one command, one compact block: a PR's head, base, checks, review, behind-ness and train state.

  pr_state.py <n> [--repo OWNER/NAME] [--state PATH] [--timeout S]

Prints one line each: head sha; base, mergeable and merge state, commits behind base; labels; the check-runs
summary (PASS/FAIL/PENDING counts plus the failing names); the review decision; merge-train membership when
the train state file exists (`merge_train.py`'s `<git-common-dir>/merge-train.json`, or --state); then `verdict`.
Exit 0 green, 1 red, 2 pending, 3 could not read (bad args, no auth or network, no such PR).
  red      the PR is not OPEN, has a merge conflict, has changes requested, or has a failing check.
  pending  not red, but a check is pending or absent, a review is required, or GitHub's merge state is
           BLOCKED, BEHIND, DRAFT or UNKNOWN.
  green    none of the above. This is GitHub's own view in one glance, not an exact-SHA receipt: before
           claiming a PR is green or mergeable, prove it with `surface_check.py checks`.

Replaces the `gh pr view` / `gh pr checks` / compare round with three `gh api` reads (curl fallback and token
from `gh_rest.py`: GH_TOKEN, GITHUB_TOKEN or `gh auth token`): ONE GraphQL query for every PR-level field,
`surface_check.check_checks` for the per-name latest check-run verdict (the repo's one judge of check runs,
never the combined rollup), and one REST compare for the behind count.
Side effects: none beyond one temp file holding the GraphQL body. Edge cases: a fork PR compares by head sha;
an unreadable compare prints `behind unknown`; labels past 50 are dropped; every name printed is cut to
printable ASCII so a label or check name cannot forge a line of the block.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gh_rest  # noqa: E402  (origin slug)
import surface_check as sc  # noqa: E402  (the check-run judge and the gh runner with the curl fallback)

QUERY = ("query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){"
         "state isDraft headRefOid baseRefName mergeable mergeStateStatus reviewDecision labels(first:50){nodes{name}}"
         "}}}")
WAITING = {"BLOCKED", "BEHIND", "DRAFT", "UNKNOWN"}  # merge states in which GitHub will not merge it yet


class ReadError(Exception):
    """The PR state could not be read at all (exit 3), as opposed to read and red or pending."""


def clean(value, limit=80):
    """`value` as printable ASCII cut to `limit` chars. Pure."""
    return re.sub(r"[^ -~]", "?", str(value))[:limit]


def read_pr(slug, n, timeout):
    """The PR's GraphQL object (state, isDraft, headRefOid, baseRefName, mergeable, mergeStateStatus, reviewDecision, labels).

    One `gh api graphql` call; raises ReadError when gh fails, the PR does not exist, or the reply is not that object.
    """
    owner, name = slug.split("/")
    with tempfile.NamedTemporaryFile("w", suffix=".json") as fh:
        json.dump({"query": QUERY, "variables": {"o": owner, "r": name, "n": n}}, fh)
        fh.flush()
        rc, out, err = sc._gh(["gh", "api", "graphql", "-X", "POST", "--input", fh.name], timeout)
    try:
        pr = json.loads(out)["data"]["repository"]["pullRequest"]
    except (ValueError, KeyError, TypeError):
        pr = None
    if rc != 0 or not isinstance(pr, dict) or not pr.get("headRefOid"):
        raise ReadError(f"PR #{n} of {slug} unreadable (rc {rc}): {clean((err or out).strip(), 200)}")
    return pr


def read_behind(slug, pr, timeout):
    """Commits the PR head is behind its base branch (REST compare), or None when the read fails. One `gh api` call."""
    base = urllib.parse.quote(str(pr.get("baseRefName")), safe="/")
    rc, out, _ = sc._gh(["gh", "api", f"repos/{slug}/compare/{base}...{pr['headRefOid']}?per_page=1"], timeout)
    try:
        return int(json.loads(out)["behind_by"]) if rc == 0 else None
    except (ValueError, KeyError, TypeError):
        return None


def train_line(n, head, path):
    """The `train ...` line for PR `n` from merge_train.py's state file at `path`; '' when no such file. Never raises."""
    if not path or not os.path.exists(path):
        return ""
    try:
        with open(path, encoding="utf-8") as fh:
            st = json.load(fh)
        n = str(n)
        for m in st.get("members") or []:
            if str(m.get("number")) == n:
                moved = "" if m.get("head") == head else " (head moved since the union ran)"
                return f"train member of the verified union on {clean(st.get('base'))}@{clean(st.get('base_sha'))[:7]}{moved}"
        if (st.get("parked") or {}).get(n):
            return f"train parked: {clean(st['parked'][n].get('reason'))}"
        if str((st.get("keystone") or {}).get("pr")) == n:
            return "train keystone"
        return "train not in the recorded union"
    except (OSError, ValueError, AttributeError, TypeError):
        return "train state file unreadable"


def train_path():
    """`<git-common-dir>/merge-train.json` (merge_train.py's default), or '' outside a git repository."""
    p = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True)
    return os.path.join(os.path.abspath(p.stdout.strip()), "merge-train.json") if p.returncode == 0 and p.stdout.strip() else ""


def verdict(pr, check_code):
    """(exit code, reasons): 1 red, 2 pending, 0 green. Red outranks pending. Pure."""
    red = [why for hit, why in (
        (pr.get("state") != "OPEN", f"state {pr.get('state')}"),
        (pr.get("mergeable") == "CONFLICTING", "merge conflict"),
        (pr.get("reviewDecision") == "CHANGES_REQUESTED", "changes requested"),
        (check_code == sc.FAIL, "check failing")) if hit]
    if red:
        return 1, red
    wait = [why for hit, why in (
        (check_code != sc.PASS, "checks pending, absent or unreadable"),
        (pr.get("mergeStateStatus") in WAITING or pr.get("mergeable") == "UNKNOWN", f"merge state {pr.get('mergeStateStatus')}"),
        (pr.get("reviewDecision") == "REVIEW_REQUIRED", "review required")) if hit]
    return (2, wait) if wait else (0, [])


def main(argv):
    """CLI entry point; returns the exit code (0 green, 1 red, 2 pending, 3 could not read)."""
    ap = argparse.ArgumentParser(prog="pr_state.py", description="One compact block of a PR's state; exit 0 green, 1 red, 2 pending.")
    ap.add_argument("pr", type=int, help="pull request number")
    ap.add_argument("--repo", default="", help="OWNER/NAME (default: the origin remote)")
    ap.add_argument("--state", default=None, help="merge_train.py state file (default <git-common-dir>/merge-train.json)")
    ap.add_argument("--timeout", type=float, default=60.0, help="seconds per gh call")
    try:
        a = ap.parse_args(argv)
    except SystemExit as exc:
        return 3 if exc.code else 0  # argparse's own usage exit is 2, which here would read as pending
    slug = a.repo or gh_rest._slug() or ""
    if a.pr < 1 or not sc.REPO_SLUG_RE.match(slug):
        print("pr_state: need a positive PR number and OWNER/NAME (--repo, or an origin remote on GitHub)", file=sys.stderr)
        return 3
    try:
        pr = read_pr(slug, a.pr, a.timeout)
    except ReadError as exc:
        print(f"pr_state: {exc}", file=sys.stderr)
        return 3
    head = pr["headRefOid"]
    behind = read_behind(slug, pr, a.timeout)
    try:
        check_code, _, check_why = sc.check_checks(slug, head, [], a.timeout)
    except sc.CheckError as exc:  # check_checks normalises the sha outside its own try
        check_code, check_why = sc.COULD_NOT_CHECK, str(exc)
    labels = [clean(n.get("name"), 40) for n in ((pr.get("labels") or {}).get("nodes") or []) if isinstance(n, dict)]
    code, why = verdict(pr, check_code)
    lines = [
        f"#{a.pr} {pr.get('state')}{' draft' if pr.get('isDraft') else ''} head {head}",
        f"base {clean(pr.get('baseRefName'))}  mergeable {pr.get('mergeable')}  state {pr.get('mergeStateStatus')}  "
        f"behind {'unknown' if behind is None else behind}",
        "labels " + (", ".join(labels) or "none"),
        "checks " + clean(check_why.replace("—", "-"), 300),
        "review " + (pr.get("reviewDecision") or "none"),
        train_line(a.pr, head, train_path() if a.state is None else a.state),
        "verdict " + ("green", "red", "pending")[code] + (": " + "; ".join(why) if why else ""),
    ]
    print("\n".join(line for line in lines if line))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
