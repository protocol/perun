#!/usr/bin/env python3
"""PreToolUse(Bash) hook: deny a git hook bypass. Fix the failing hook; never bypass it.

Denies (exit 2, reason on stderr; the host blocks the call) a command that runs
`git commit|push|merge` with `--no-verify`, `git commit -n` (also bundled, e.g. `-an`), an env
prefix `HUSKY=0` / `HUSKY_SKIP_HOOKS=` / `SKIP=`, or any git call with `-c core.hooksPath=`.
Tokenizes with shlex, so `-n` or `--no-verify` inside a quoted commit message is not a hit.
Unparseable stdin, a non-Bash tool or no command -> silent exit 0 (a guard must never wedge a
session). Known limit: `git config core.hooksPath` or a hook edited out of the tree is not seen.
Side effects: none.
"""
import json
import re
import shlex
import sys

ENV = re.compile(r"^(HUSKY=0|HUSKY_SKIP_HOOKS=|SKIP=)")
GATED = ("commit", "push", "merge")
ARG_FLAGS = "mFCctSu"  # short commit flags that take a value; a bundle's remaining chars are that value
MSG = ("Blocked git hook bypass ({why}). Fix the failing hook; never bypass it "
       "(no --no-verify, commit -n, HUSKY=0, SKIP=, -c core.hooksPath=).")


def bypass(cmd):
    """Return the reason `cmd` bypasses git hooks, or '' when it does not."""
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        toks = list(lex)
    except ValueError:
        return ""
    segs = [[]]
    for t in toks:
        if re.fullmatch(r"[();<>|&]+", t):
            segs.append([])
        else:
            segs[-1].append(t)
    env = next((t for t in toks if ENV.match(t)), "")
    gated = ""
    for seg in segs:
        if "git" not in seg:
            continue
        i, sub, hp = seg.index("git") + 1, "", False
        while i < len(seg):
            t = seg[i]
            if t in ("-c", "-C") and i + 1 < len(seg):
                hp = hp or seg[i + 1].lower().startswith("core.hookspath=") and t == "-c"
                i += 2
            elif t.startswith("-"):
                i += 1
            else:
                sub = t
                break
        if hp:
            return "-c core.hooksPath="
        if sub not in GATED:
            continue
        gated = gated or sub
        rest = seg[i + 1:]
        if "--no-verify" in rest:
            return "--no-verify"
        if sub == "commit":
            for t in rest:
                if re.fullmatch(r"-[A-Za-z]+", t):
                    for ch in t[1:]:
                        if ch == "n":
                            return "commit -n"
                        if ch in ARG_FLAGS:
                            break
    return f"env {env}" if env and gated else ""


def main():
    try:
        data = json.load(sys.stdin)
        cmd = (data.get("tool_input") or {}).get("command") or ""
    except (ValueError, AttributeError):
        return 0
    why = bypass(cmd) if data.get("tool_name", "Bash") == "Bash" else ""
    if why:
        print(MSG.format(why=why), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
