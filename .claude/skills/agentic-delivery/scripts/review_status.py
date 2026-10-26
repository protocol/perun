#!/usr/bin/env python3
"""review_status.py — post a review verdict as commit status `perun/review` on an exact PR head SHA.

  review_status.py --sha <40-hex> --red N [--repo OWNER/NAME] [--dry-run]

State is `success` when N (the count of red findings) is 0, else `failure`. `land_ready.py` reads this status,
so the train needs no human relay of review verdicts. Status is per SHA: a push to the PR moves the head and the
verdict no longer applies until the new head is reviewed and posted again.
Side effects: one `gh api` POST to repos/<repo>/statuses/<sha> (none with --dry-run, which prints the request).
Exit 0 posted or dry-run, 1 post failed, 3 bad arguments.
"""
import argparse
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gh_rest  # noqa: E402
import surface_check as sc  # noqa: E402  (gh runner with the curl fallback)

CONTEXT = "perun/review"


def main(argv):
    """CLI entry point; returns the exit code."""
    ap = argparse.ArgumentParser(prog="review_status.py", description=__doc__.splitlines()[0])
    ap.add_argument("--sha", required=True, help="full 40-hex PR head sha")
    ap.add_argument("--red", required=True, type=int, help="count of red findings (0 = success)")
    ap.add_argument("--repo", default="", help="OWNER/NAME (default: the origin remote)")
    ap.add_argument("--dry-run", action="store_true", help="print the request, post nothing")
    try:
        a = ap.parse_args(argv)
    except SystemExit as exc:
        return 3 if exc.code else 0
    slug = a.repo or gh_rest._slug() or ""
    if a.red < 0 or not re.fullmatch(r"[0-9a-f]{40}", a.sha) or not sc.REPO_SLUG_RE.match(slug):
        print("review_status: need --red >= 0, a full lowercase 40-hex --sha and OWNER/NAME", file=sys.stderr)
        return 3
    state = "success" if a.red == 0 else "failure"
    body = {"state": state, "context": CONTEXT, "description": f"review: {a.red} red"}
    path = f"repos/{slug}/statuses/{a.sha}"
    if a.dry_run:
        print(f"DRY-RUN POST {path} {json.dumps(body)}")
        return 0
    with tempfile.NamedTemporaryFile("w", suffix=".json") as fh:
        json.dump(body, fh)
        fh.flush()
        rc, _, err = sc._gh(["gh", "api", "-X", "POST", path, "--input", fh.name], 60)
    if rc != 0:
        print(f"review_status: post failed (rc {rc}): {err.strip()[:200]}", file=sys.stderr)
        return 1
    print(f"posted {CONTEXT}={state} on {a.sha[:7]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
