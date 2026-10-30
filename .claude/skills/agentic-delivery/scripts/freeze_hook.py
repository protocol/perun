#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=deny git push and gh pr merge while a freeze is on, review=2027-01-30
"""PreToolUse(Bash) hook: while a freeze is on, deny `git push` and `gh pr merge`.

WHY: `freeze_gate.py` runs inside pre-push, so it only sees a push that reaches git; a `gh pr merge` never does, and a
freeze that a lane can walk around is not a freeze. This hook reads the same freeze file (`$PERUN_FREEZE`,
`<git-common-dir>/PERUN_FREEZE` or a repo-root `.perun-freeze`) and denies (exit 2, reason on stderr) a Bash command whose
parsed argv, after global flags, is `git push`, `gh pr merge`, or a `gh api` call to `pulls/N/merge` or `mergePullRequest`.
Commands are split on `;`, `&`, `|`, newline; env prefixes and `env|command|sudo|nohup|time` wrappers are skipped, and
`bash|sh|zsh -c STR` / `eval STR` are parsed recursively. Lift the freeze by removing the file.

Not a freeze (cwd outside a git repo, no `$PERUN_FREEZE`) -> allow. FAIL CLOSED once a freeze exists or its state cannot
be read (no `git` on PATH, git failing inside a repo): malformed JSON, a non-object payload, a missing or non-string
command, or an unparseable command line is denied.
Known ceiling (a tripwire for honest lanes, not a sandbox): a name built by variable, alias, quoting tricks the parser
cannot see, `eval "$x"`, or a script that runs the push internally is not seen. Real control: branch protection and the
pre-push `freeze_gate.py`. Side effects: none (read-only).
"""
import json
import os
import re
import shlex
import subprocess
import sys

SEP = re.compile(r"[;&|\n]+")
WRAP = {"env", "command", "sudo", "nohup", "time", "exec", "builtin"}
GIT_VAL = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
GH_VAL = {"-R", "--repo", "--hostname"}


def freeze_file():
    """Path of the active freeze file, None when no freeze applies. Raises on an unreadable state."""
    env = os.environ.get("PERUN_FREEZE")
    if env:
        return env if os.path.exists(env) else None
    p = subprocess.run(["git", "rev-parse", "--git-common-dir", "--show-toplevel"], capture_output=True, text=True)
    if p.returncode:
        if "not a git repository" in p.stderr:
            return None  # no repo, no freeze
        raise RuntimeError(p.stderr.strip() or "git failed")
    common, top = p.stdout.split("\n")[:2]
    return next((c for c in (os.path.join(common, "PERUN_FREEZE"), os.path.join(top, ".perun-freeze")) if os.path.exists(c)), None)


def gated(cmd):
    """True when any segment of `cmd` is a gated push/merge. Raises ValueError on an unparseable line."""
    for seg in SEP.split(cmd):
        toks = shlex.split(seg)
        while toks and (re.match(r"\w+=", toks[0]) or os.path.basename(toks[0]) in WRAP):
            toks = toks[1:]
        if not toks:
            continue
        prog, rest = os.path.basename(toks[0]), toks[1:]
        if prog in ("bash", "sh", "zsh") and "-c" in rest and rest.index("-c") + 1 < len(rest):
            if gated(rest[rest.index("-c") + 1]):
                return True
        elif prog == "eval":
            if gated(" ".join(rest)):
                return True
        elif prog in ("git", "gh"):
            val, args, i = (GIT_VAL if prog == "git" else GH_VAL), [], 0
            while i < len(rest):  # drop global flags (and their values) before the subcommand
                t = rest[i]
                if t in val:
                    i += 2
                elif t.startswith("-") and not args:
                    i += 1
                else:
                    args.append(t)
                    i += 1
            if prog == "git" and args[:1] == ["push"]:
                return True
            if prog == "gh" and (args[:2] == ["pr", "merge"] or (args[:1] == ["api"] and re.search(
                    r"pulls/[^/\s]+/merge|mergePullRequest", " ".join(args)))):
                return True
    return False


def main():
    try:
        freeze = freeze_file()
    except Exception as e:  # no git, git failing in a repo: the freeze state is unreadable
        print(f"freeze_hook: cannot read freeze state ({e}); denying", file=sys.stderr)
        return 2
    if not freeze:
        return 0
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name", "Bash") != "Bash":
            return 0
        cmd = data["tool_input"]["command"]
        if not isinstance(cmd, str):
            raise TypeError("command is not a string")
        if not gated(cmd):
            return 0
    except Exception as e:  # malformed input or an unparseable command: fail closed
        print(f"freeze_hook: unreadable tool input ({e}); denying while frozen", file=sys.stderr)
        return 2
    try:
        reason = (open(freeze, errors="replace").readline().strip() if os.path.isfile(freeze) else "") or "(no reason given)"
    except OSError:
        reason = "(no reason given)"
    print(f"FROZEN: {reason}; `git push` and `gh pr merge` are blocked until the freeze file is removed", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
