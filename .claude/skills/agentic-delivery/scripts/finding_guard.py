#!/usr/bin/env python3
"""PreToolUse(Bash) hook: deny `gh issue create` when `file_finding.py` finds the same finding already filed.

WHY: most pipeline-filed issues repeated one already closed. `file_finding.py` (the dedupe search over open and closed issues
and PRs) only helps when it is run; this hook runs it on every `gh issue create --title ...`, so the check cannot be skipped.

Match: a Bash command containing `gh issue create` with `--title X`, `--title=X` or `-t X` (shlex tokens; `--repo R` is passed
through). Then `file_finding.py` (next to this file) runs on the title: exit 1 (a duplicate) -> deny, exit 2 with the
matches on stderr so the agent comments on or reopens the existing item. Explicit override: put `finding-force: REASON`
(non-empty reason) anywhere in the command, e.g. a trailing `# finding-force: distinct root cause`; the reason is logged by
file_finding.py to `$PERUN_FINDING_LOG`. FAIL OPEN: a non-Bash tool, no title, unparseable input, missing file_finding.py,
a failed or timed-out `gh` search (file_finding exit 2) all allow with at most a one-line stderr note.
Side effects: the --force log line, only on an override.
"""
import json
import os
import re
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def opt(toks, longs, short=None):
    for i, t in enumerate(toks):
        for lo in longs:
            if t == lo and i + 1 < len(toks):
                return toks[i + 1]
            if t.startswith(lo + "="):
                return t[len(lo) + 1:]
        if short and t == short and i + 1 < len(toks):
            return toks[i + 1]
    return ""


def verdict(cmd):
    """(exit code, stderr text) for one Bash command."""
    if not re.search(r"\bgh\s+issue\s+create\b", cmd):
        return 0, ""
    try:
        toks = shlex.split(cmd, comments=False)
    except ValueError:
        return 0, ""
    title = opt(toks, ("--title",), "-t")
    if not title:
        return 0, ""
    cli = [sys.executable, os.path.join(HERE, "file_finding.py")]
    repo = opt(toks, ("--repo",), "-R")
    if repo:
        cli += ["--repo", repo]
    force = re.search(r"finding-force:\s*(\S.*)", cmd)
    if force:
        cli += ["--force", force.group(1).strip("'\" ")]
    try:
        r = subprocess.run(cli + [title], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return 0, "finding_guard: duplicate search did not run; allowing"
    if r.returncode == 1:
        return 2, ("Blocked `gh issue create`: a matching issue or PR already exists (below). Comment on or reopen it instead. "
                   "If this is genuinely different, add `# finding-force: <reason>` to the command.\n" + r.stdout.strip())
    return 0, "" if r.returncode == 0 else "finding_guard: duplicate search failed; allowing"


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name", "Bash") != "Bash":
            return 0
        code, msg = verdict((data.get("tool_input") or {}).get("command") or "")
    except Exception:
        return 0
    if msg:
        print(msg, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
