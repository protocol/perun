#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=deny a git hook bypass: fix the failing hook instead, review=2027-01-30
"""PreToolUse(Bash) hook: deny a git hook bypass. Fix the failing hook; never bypass it.

Denies (exit 2, reason on stderr; the host blocks the call) a command that runs
`git commit|push|merge` with `--no-verify` (or an unambiguous prefix such as `--no-verif`), `git commit -n`
(also bundled, e.g. `-an`), with an env prefix `HUSKY=0` / `HUSKY_SKIP_HOOKS=` / `SKIP=` /
`GIT_CONFIG_COUNT|KEY_n|PARAMETERS=`, or any git call with `-c core.hooksPath=` /
`--config-env=core.hooksPath=`; also `git config core.hooksPath` (write form).

Parsing: shlex tokens, split into segments on newline, `;`, `&&`, `||`, `|`. Per segment the leading
VAR=val tokens are env, the next token is argv0; git means basename(argv0) == "git" (so /usr/bin/git
matches), `bash|sh|zsh -c STR` and `eval STR` recurse, and `env [-i|-u X|VAR=v]` / `xargs [opts]` are skipped as wrappers into STR. A bare or `export VAR=val` segment is sticky env
for the rest of the command. Option values (the `-m`/`-F` argument) are skipped, so a message that
says `--no-verify` or `SKIP=1` is not a hit.

Also denies any command whose text mentions `approvals` (any spelling: no slash, `cd` into it, `$VAR`/`$'\\x..'` paths, `ln -s`, an
unparseable line) unless every segment is a read-only command (cat/ls/grep/head/tail/wc/stat/test/diff). Only a verified human writes
gate-override approvals (an owner-run `!` command, which bypasses this hook); a lane never self-approves. This is a TRIPWIRE for honest
mistakes (a name split across quotes still passes); the boundary is the sandbox / filesystem permissions on `.perun/approvals`.

Unparseable input -> allow plus a one-line stderr note.
# ponytail: a deny hook that blocks on a parse error breaks legit commands, so it fails open; ceiling:
# guards honest mistakes; deliberate evasion is backstopped by the host classifier. `g=git; $g commit -n`, aliases and scripts that wrap git are not seen. Upgrade: resolve the command
# through the shell, or a git-level hook (core.hooksPath is the thing being protected, so none here).
Side effects: none.
"""
import json
import os
import re
import shlex
import sys

GATED = ("commit", "push", "merge")
ARG_SHORT = {"commit": "mFCctuz", "merge": "mFsX", "push": "o"}  # short flags whose value is the next token
ARG_LONG = {"message", "file", "author", "date", "cleanup", "template", "reuse-message", "reedit-message",
            "fixup", "squash", "strategy", "strategy-option", "repo", "receive-pack", "exec", "push-option"}
GIT_OPT_VAL = ("-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path")
OPT_VAL = ("-u", "-n", "-I", "-P", "-L", "-d", "-E", "-s", "-a", "-C", "-S")  # wrapper options taking a value
WRAP = ("env", "command", "exec", "nohup", "sudo", "time", "builtin")
MSG = ("Blocked git hook bypass ({why}). Fix the failing hook; never bypass it "
       "(no --no-verify, commit -n, HUSKY=0, SKIP=, GIT_CONFIG_*, core.hooksPath).")


APPROVALS = "approvals"
READ = ("cat", "ls", "grep", "head", "tail", "wc", "stat", "test", "[", "diff")
HUMAN = "a gate override (.perun/approvals) needs a verified human, never a lane"


def _approval_write(cmd, segs):
    """Fail closed: a command that mentions `approvals` in any form is denied unless every segment is led by a read-only command."""
    return APPROVALS in cmd.lower() and not all(os.path.basename(g[0]) in READ for g in segs if g)


def _env_bad(a):
    k, _, v = a.partition("=")
    return (k == "HUSKY" and v == "0") or k in ("HUSKY_SKIP_HOOKS", "SKIP", "GIT_CONFIG_COUNT",
                                                 "GIT_CONFIG_PARAMETERS") or k.startswith("GIT_CONFIG_KEY_")


def _git(args):
    """Reason `git <args>` bypasses hooks, or ''. Also returns the gated subcommand via the 2nd value."""
    i, sub = 0, ""
    while i < len(args):
        t = args[i]
        if t in GIT_OPT_VAL:
            if t == "-c" and i + 1 < len(args) and args[i + 1].lower().startswith("core.hookspath"):
                return "-c core.hooksPath=", ""
            if t == "--config-env" and i + 1 < len(args) and args[i + 1].lower().startswith("core.hookspath"):
                return "--config-env core.hooksPath", ""
            i += 2
        elif t.lower().startswith("--config-env=core.hookspath"):
            return "--config-env core.hooksPath", ""
        elif t == "--config-env":
            i += 2
        elif t.startswith("-"):
            i += 1
        else:
            sub = t
            break
    rest = args[i + 1:]
    if sub == "config" and any("core.hookspath" in t.lower() for t in rest) \
            and not {"--get", "--get-all", "--list", "-l", "--unset", "--unset-all"} & set(rest):
        return "git config core.hooksPath", ""
    if sub not in GATED:
        return "", ""
    j = 0
    while j < len(rest):
        t = rest[j]
        j += 1
        if t == "--":
            break
        if t.startswith("--"):
            name = t[2:].split("=")[0]
            if len(name) >= 4 and "no-verify".startswith(name):
                return "--no-verify", sub
            if name in ARG_LONG and "=" not in t:
                j += 1
        elif re.fullmatch(r"-[A-Za-z]+", t):
            for k, ch in enumerate(t[1:], 2):
                if ch == "n" and sub == "commit":
                    return "commit -n", sub
                if ch in ARG_SHORT[sub]:
                    j += k == len(t)  # value is the next token only when the flag ends the bundle
                    break
                if ch == "S":
                    break
    return "", sub


def bypass(cmd, _sticky=None):
    """Return the reason `cmd` bypasses git hooks, or '' when it does not (parse errors allow)."""
    sticky = _sticky if _sticky is not None else []
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>\n")
        lex.whitespace, lex.whitespace_split = " \t\r", True
        toks = list(lex)
    except ValueError as e:
        print(f"bypass_guard: could not parse command ({e}); allowed", file=sys.stderr)
        return HUMAN if APPROVALS in cmd.lower() else ""
    segs = [[]]
    for t in toks:
        if re.fullmatch(r"[;&|()<>\n]+", t):
            segs.append([])
        else:
            segs[-1].append(t)
    if _approval_write(cmd, segs):
        return HUMAN
    gated = False
    for seg in segs:
        i, env = 0, []
        while i < len(seg):
            b = os.path.basename(seg[i])
            if re.match(r"\w+=", seg[i]):
                env.append(seg[i])
                i += 1
            elif b in WRAP + ("export", "xargs"):
                i += 1
                while i < len(seg) and seg[i].startswith("-"):  # wrapper options, e.g. env -i / -u X, xargs -n 1
                    i += 2 if seg[i] in OPT_VAL else 1
            else:
                break
        bad = next((e for e in env if _env_bad(e)), "")
        if i >= len(seg):  # bare assignment / export: sticky for the rest of the command
            sticky += [e for e in env if _env_bad(e)]
            continue
        name = os.path.basename(seg[i])
        if name == "eval":
            r = bypass(" ".join(seg[i + 1:]), sticky)
            if r:
                return r
        if name in ("bash", "sh", "zsh", "dash") and "-c" in seg[i:-1]:
            r = bypass(seg[seg.index("-c", i) + 1], sticky)
            if r:
                return r
        elif name == "git":
            r, sub = _git(seg[i + 1:])
            if r:
                return r
            if sub:
                gated = True
                if bad:
                    return f"env {bad}"
    if gated and sticky:
        return f"env {sticky[0]}"
    return ""


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
