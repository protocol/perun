#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=deny gh issue create when the same finding is already filed, review=2027-01-30
"""PreToolUse(Bash) hook: deny `gh issue create` when `file_finding.py` finds the same finding already filed.

WHY: most pipeline-filed issues repeated one already closed. `file_finding.py` (the dedupe search over open and closed issues
and PRs) only helps when it is run; this hook runs it on every `gh issue create --title ...`, so the check cannot be skipped.

Also denies a raw `gh issue create` unless env PERUN_ISSUE_GATE=1 is set in the hook's environment (the owner kill switch;
issue_gate.py's own gh subprocess never reaches this hook). A `PERUN_ISSUE_GATE=1` prefix in the command text does not count.
Matched on shlex tokens: `gh` then `issue create` with any flags between, and a `gh api` POST (-f/-F/--field/--raw-field/--input/-X POST)
to repos/*/*/issues; the old regex is only the fallback when the command does not parse.

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


SEP = (";", "&&", "||", "|", "&", "(", ")")
API_FLAGS = ("-f", "-F", "--field", "--raw-field", "--input")


WRAP = ("env", "command", "xargs", "sudo", "nohup", "time")
HEREDOC = re.compile(r"(<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n).*?\n[ \t]*\2[ \t]*(?=\n|$)", re.S)
FALLBACK = re.compile(r"(?:^|[;&|(\n])\s*(?:\w+=\S*\s+|env\s+|command\s+|xargs\s+|sudo\s+|nohup\s+|time\s+)*"
                      r"gh\s+(?:-\S+\s+(?:[^-\s]\S*\s+)?)*issue\s+create\b")


def raw_create(toks):
    """True when `gh` sits in command position (start, after ; && || | ( or a newline, VAR=val assignments, env/command/xargs/
    sudo/nohup/time) and the rest is `[flags] issue create` or a `gh api` POST to repos/*/*/issues. A quoted title or prose that
    merely contains those words never matches."""
    cmdpos = True
    for i, t in enumerate(toks):
        if t in SEP:
            cmdpos = True
            continue
        if not cmdpos:
            continue
        if re.fullmatch(r"\w+=.*", t) or os.path.basename(t) in WRAP or (t.startswith("-") and i and os.path.basename(toks[i - 1]) in WRAP):
            continue
        cmdpos = False
        if os.path.basename(t) != "gh":
            continue
        pos, post, j, rest = [], False, 0, []
        for r in toks[i + 1:]:
            if r in SEP:
                break
            rest.append(r)
        while j < len(rest):
            r = rest[j]
            if r in ("-R", "--repo", "--hostname") or (r in ("-X", "--method") and j + 1 < len(rest)):
                post = post or (r in ("-X", "--method") and rest[j + 1].upper() == "POST")
                j += 2
                continue
            if r.startswith("-"):
                post = post or r in API_FLAGS or r.startswith(("--field=", "--raw-field=", "--input=")) or \
                    (len(r) > 2 and r[:2] in ("-f", "-F") and r[1] != "-") or r.upper() == "-XPOST" or r.upper() == "--METHOD=POST"
            else:
                pos.append(r)
            j += 1
        if pos[:2] == ["issue", "create"]:
            return True
        if pos[:1] == ["api"] and post and any(re.fullmatch(r"/?repos/[^/]+/[^/]+/issues/?", x) for x in pos[1:]):
            return True
    return False


def verdict(cmd):
    """(exit code, stderr text) for one Bash command."""
    try:
        lex = shlex.shlex(HEREDOC.sub(r"\1", cmd).replace("\n", " ; "), posix=True, punctuation_chars=True)
        lex.whitespace_split, lex.commenters = True, ""  # '#' inside a word is not a comment: `a#b; gh issue create` must not hide
        toks = list(lex)
        raw = raw_create(toks)
    except ValueError:  # unparseable: fall back to the regex, then fail open on the title search
        toks, raw = None, bool(FALLBACK.search(cmd))
    if not raw:
        return 0, ""
    if os.environ.get("PERUN_ISSUE_GATE") != "1":
        return 2, ("Blocked raw `gh issue create`: file through `python3 .claude/skills/agentic-delivery/scripts/issue_gate.py file "
                   "--title T --body-file F --priority P0..P3 --area A` (dedupe, daily cap, low-severity refusal).")
    if toks is None:
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
