#!/usr/bin/env python3
"""flake_holder.py BASE HEAD — warn when a flaky-test fix touches a test file another open PR already changes.

WHY: two PRs fixing the same flaky test file conflict, double the CI, and the second one lands a stale view of the test.
The fix belongs in the holder's PR. Run by the pre-push hook before a push.

Trigger: some commit subject in BASE..HEAD mentions "flak" (flaky, flake, flakiness; case-insensitive). Then every test file
(`test` in its path) changed in BASE..HEAD is looked up in the open PRs (`gh pr list --state open`, other branches only).
Prints `WARN: <file> is also changed by open PR #N (<branch>): add the fix to that PR instead of opening a second one` per
holder. WARN-ONLY: always exits 0, and a missing `gh`, no network or unparseable output prints nothing (fail open).
`PERUN_GH` overrides the gh binary (tests). Side effects: none (read-only).
"""
import json
import os
import re
import subprocess
import sys


def out(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def holders(changed, prs, branch):
    """[(file, pr number, branch)] for each changed test file that an open PR on another branch also changes."""
    return [(f, p["number"], p.get("headRefName", "")) for p in prs if p.get("headRefName") != branch
            for f in changed if f in {x.get("path") for x in p.get("files") or []}]


def main(argv):
    if len(argv) != 2:
        sys.exit("usage: flake_holder.py BASE HEAD")
    base, head = argv
    try:
        subjects = out("git", "log", "--format=%s", f"{base}..{head}").stdout
        if not re.search(r"flak", subjects, re.I):
            return 0
        changed = [f for f in out("git", "diff", "--name-only", f"{base}...{head}").stdout.split() if "test" in f.lower()]
        branch = out("git", "branch", "--show-current").stdout.strip()
        r = out(os.environ.get("PERUN_GH", "gh"), "pr", "list", "--state", "open", "--limit", "1000",
                "--json", "number,headRefName,files")
        for f, n, b in holders(changed, json.loads(r.stdout or "[]"), branch) if changed and r.returncode == 0 else ():
            print(f"WARN: {f} is also changed by open PR #{n} ({b}): add the fix to that PR instead of opening a second one")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
