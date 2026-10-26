#!/usr/bin/env python3
"""file_finding.py — duplicate check to run BEFORE anything files an issue.

  file_finding.py [--repo OWNER/NAME] [--force REASON] TITLE [KEYWORD...]
      && gh issue create ...

WHY: most pipeline-filed issues repeated one that was already closed. This searches, with `gh`, open issues, closed
issues, open PRs and PRs merged in the last 14 days (one search per title word and per KEYWORD, results merged) and matches by
title: a candidate matches when it shares at least 2 of TITLE's keywords (lowercase words of 4+ letters) and at least 60% of
them, or contains any explicit KEYWORD as a whole word (keywords under 3 characters and empty ones are ignored). One shared
word alone never matches; a TITLE with fewer than 2 such words matches only an equal normalized title.
Exit 0: no match (prints "OK"), or a match overridden by --force REASON (the reason, title and matches are appended to
$PERUN_FINDING_LOG, default .perun/finding-force.log). Exit 1: match found, each printed as "REFUSE: #N [state] title url".
Exit 2: usage or `gh` failed (fails closed; nothing is filed on an unchecked search). Side effects: the --force log line only.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys

MAX_TERMS = 8  # gh searches per kind: bounds the call count for a long title
STOP = {"this", "that", "with", "from", "when", "have", "does", "should", "into", "than", "only", "after", "before"}


def words(s: str) -> set:
    return {w for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in STOP}


def norm(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


def keywords(kws: list) -> list:
    """Explicit keywords usable for matching: stripped, lowercase, at least 3 characters (empty and 1-2 char ones are dropped)."""
    return [k for k in (k.strip().lower() for k in kws) if len(k) >= 3]


def matches(title: str, kws: list, cand: str) -> bool:
    """True when `cand` looks like a repeat of `title`: >= 2 shared keywords making up >= 60% of the title's, or any explicit
    keyword as a whole word in it. A title with fewer than 2 qualifying words cannot use the overlap rule, so it matches only
    on equal normalized titles (or a keyword)."""
    a, b = words(title), words(cand)
    if len(a) < 2:
        by_overlap = bool(norm(title)) and norm(title) == norm(cand)  # an empty normalized title matches nothing
    else:
        by_overlap = len(a & b) >= 2 and len(a & b) / len(a) >= 0.6
    return by_overlap or any(re.search(rf"(?<![a-z0-9]){re.escape(k)}(?![a-z0-9])", cand.lower()) for k in keywords(kws))


def gh_json(args: list, repo: str) -> list:
    cmd = ["gh", *args, "--json", "number,title,state,url", "--limit", "100"] + (["--repo", repo] if repo else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"gh {args[0]} failed: {r.stderr.strip()}")
    return json.loads(r.stdout or "[]")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="file_finding.py")
    ap.add_argument("--repo", default="")
    ap.add_argument("--force", metavar="REASON")
    ap.add_argument("title")
    ap.add_argument("keywords", nargs="*")
    a = ap.parse_args(argv)
    since = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    # One search per term (GitHub's search ANDs the words of a single query, so one combined query misses a differently worded repeat).
    terms = sorted(words(a.title) | set(keywords(a.keywords)))[:MAX_TERMS] or [a.title]
    try:
        found = {}
        for t in terms:
            for kind, args in (("issue", ["issue", "list", "--state", "all", "--search", t]),
                               ("open-pr", ["pr", "list", "--state", "open", "--search", t]),
                               ("pr",["pr", "list", "--state", "merged", "--search", f"{t} merged:>={since}"])):
                for c in gh_json(args, a.repo):
                    found[(kind, c["number"])] = c
    except (RuntimeError, OSError, ValueError) as e:
        print(f"file_finding: {e}; not checked, so not safe to file", file=sys.stderr)
        return 2
    hits = [f"#{c['number']} [{c['state']}] {c['title']} {c['url']}" for c in found.values() if matches(a.title, a.keywords, c["title"])]
    if not hits:
        print("OK: no open/closed issue or PR merged in 14d matches")
        return 0
    for h in hits:
        print(f"REFUSE: {h}")
    if not a.force or not a.force.strip():
        return 1
    log = os.environ.get("PERUN_FINDING_LOG", ".perun/finding-force.log")
    os.makedirs(os.path.dirname(log) or ".", exist_ok=True)
    with open(log, "a") as f:
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')}\t{a.title}\t{a.force}\t{'; '.join(hits)}\n")
    print(f"FORCED: reason logged to {log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
