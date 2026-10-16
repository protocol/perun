#!/usr/bin/env python3
"""comms_guard.py — PreToolUse hook: lint a PR or tracker write against its artifact template; ask for one rewrite below the bar.

WHY: agents post PR bodies, status updates and comments that bury the lead, skip the numbers and leave the ask
vague, and nothing checked them before they went out. This hook runs communication-structure's comms_lint.py on the
body of the write and, when the draft is below the bar, denies it once with the exact fix per failing rule.

Covers: Linear MCP `save_status_update` (kind status) and `save_comment` (message) from any server whose name contains
"linear"; Bash `gh pr create|edit` (pr), `gh pr comment` and `gh issue create|edit|comment` (message), `gh release
create|edit` (release); `curl` or `gh api` calls to repos/<owner>/<repo>/pulls (pr) or /issues (message) with a
`body`. The body is read from `--body`/`-b`/`--notes`, a heredoc, `$(cat FILE)`, `--body-file`/`-F FILE`, `-d` JSON,
`-d @FILE`, `--input FILE` or `-f body=...`. A command with no readable body is allowed.

Decision: a JSON `permissionDecision: "deny"` whose reason is the lint report (Claude reads it and rewrites); exit 0,
never 2. A draft already denied in the last 30 minutes (same kind and text, sha1 in a ledger) is allowed, so a false
positive costs one resend and a stuck agent cannot loop. Register it as `python3 ".../comms_guard.py" || true`.

Fail open: bad stdin, a missing communication-structure skill, an unreadable file or any error allows the call.
Opt out for a session or a project with `PERUN_COMMS_GUARD=off` (settings `env`). `PERUN_COMMS_GUARD_DIR` moves the
ledger (default: the temp dir). Side effects: one small ledger file; no network. Test: scripts/test_comms_guard.py.
"""
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

WINDOW = 30 * 60
LINT_DIR = Path(__file__).resolve().parent.parent.parent / "communication-structure" / "scripts"
MCP = re.compile(r"^mcp__.*linear.*__(save_status_update|save_comment)$", re.I)
GH = re.compile(r"\bgh\s+(pr|issue|release)\s+(create|edit|comment)\b")
REST = re.compile(r"(?:\bcurl\b|\bgh\s+api\b)[\s\S]{0,600}?\brepos/[^/\s'\"]+/[^/\s'\"]+/(pulls|issues)((?:/\d+)?(?:/(?:comments|reviews))?)(?=[\s'\"?]|$)")
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1[ \t]*\n(.*?)\n[ \t]*\2[ \t]*(?=\n|\)|\"|'|$)", re.S)
VALUE = re.compile(r"\"((?:[^\"\\]|\\.)*)\"|'([^']*)'|(\S+)", re.S)


def _flags(tail, names):
    """Yield the raw text after each occurrence of a flag in `names` (regex alternation), `--flag value` or `--flag=value`."""
    for m in re.finditer(rf"(?:^|\s)(?:{names})(?:=|[ \t]+)", tail):
        yield tail[m.end():]


def _read(path, cwd):
    p = Path(os.path.expandvars(os.path.expanduser(path)))
    return (p if p.is_absolute() else Path(cwd or ".") / p).read_text(encoding="utf-8")[:200_000]


def _stdin(tail):
    h = HEREDOC.search(tail)
    return h.group(3) if h else None


def _value(rest, cwd):
    """The string a shell value stands for: heredoc, `$(cat FILE)`, a quoted string or a bare word; None if unreadable."""
    if re.match(r"\"?\$\(\s*cat\s*<<", rest):
        return _stdin(rest)
    c = re.match(r"\"?\$\(\s*cat\s+([^\s)\"']+)\s*\)", rest)
    if c:
        return _read(c.group(1), cwd)
    m = VALUE.match(rest)
    if not m:
        return None
    if m.group(1) is not None:
        return re.sub(r"\\([\"\\$`])", r"\1", m.group(1))
    return m.group(2) if m.group(2) is not None else m.group(3)


def _file(name, cwd, tail):
    """File text for a name; `-` and `@-` mean the heredoc on stdin."""
    return _stdin(tail) if name in ("-", "@-") else _read(name.lstrip("@"), cwd)


def _gh_body(tail, noun, cwd):
    names, files = (r"--notes|-n", r"--notes-file|-F") if noun == "release" else (r"--body|-b", r"--body-file|-F")
    for rest in _flags(tail, names):
        return _value(rest, cwd)
    for rest in _flags(tail, files):
        name = _value(rest, cwd)
        return _file(name, cwd, tail) if name else None
    return None


def _rest_body(tail, cwd):
    for rest in _flags(tail, r"-f|-F|--field|--raw-field"):  # gh api -f body=TEXT, -f 'body=TEXT', -F body=@FILE
        q = re.match(r"([\"'])body=", rest)
        if q:
            return _value(q.group(1) + rest[q.end():], cwd)
        if rest.startswith("body="):
            return _file(rest[5:], cwd, tail) if rest[5:].startswith("@") else _value(rest[5:], cwd)
    for rest in _flags(tail, r"-d|--data|--data-raw|--data-binary"):  # curl -d '{"body": ...}' or -d @FILE
        raw = _value(rest, cwd)
        raw = _file(raw, cwd, tail) if raw and (raw.startswith("@") or raw == "-") else raw
        return json.loads(raw).get("body") if raw else None
    for rest in _flags(tail, r"--input"):  # gh api --input FILE
        name = _value(rest, cwd)
        raw = _file(name, cwd, tail) if name else None
        return json.loads(raw).get("body") if raw else None
    return None


def extract(tool_name, tool_input, cwd=""):
    """(kind, body) for a PR or tracker write this hook covers, else None. Never raises on a malformed command."""
    if MCP.match(tool_name or ""):
        body = (tool_input or {}).get("body")
        return ("status" if tool_name.lower().endswith("save_status_update") else "message", body) if isinstance(body, str) else None
    cmd = (tool_input or {}).get("command")
    if tool_name != "Bash" or not isinstance(cmd, str) or not re.search(r"\b(?:gh|curl)\b", cmd):
        return None
    try:
        m = GH.search(cmd)
        if m:
            noun, verb = m.group(1), m.group(2)
            kind = "release" if noun == "release" else "pr" if noun == "pr" and verb != "comment" else "message"
            body = _gh_body(cmd[m.start():], noun, cwd)
        elif (m := REST.search(cmd)):
            kind = "pr" if m.group(1) == "pulls" and not m.group(2).endswith(("comments", "reviews")) else "message"
            body = _rest_body(cmd[m.start():], cwd)
        else:
            return None
    except (OSError, ValueError, AttributeError):  # unreadable file, non-JSON data: nothing to lint
        return None
    return (kind, body) if isinstance(body, str) and body.strip() else None


def seen_before(kind, body, now=None):
    """True when this exact draft was already denied within WINDOW (so the resend is allowed); records it otherwise."""
    now = time.time() if now is None else now
    d = Path(os.environ.get("PERUN_COMMS_GUARD_DIR") or tempfile.gettempdir())
    d.mkdir(parents=True, exist_ok=True)
    f, key = d / "perun-comms-guard.json", hashlib.sha1(f"{kind}\0{body}".encode()).hexdigest()
    with open(d / "perun-comms-guard.lock", "a") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        led = json.loads(f.read_text()) if f.is_file() else {}
        led = {k: t for k, t in led.items() if now - t < WINDOW}
        hit = led.pop(key, None) is not None
        if not hit:
            led[key] = now
        f.write_text(json.dumps(led))
    return hit


def main():
    if os.environ.get("PERUN_COMMS_GUARD", "").lower() in ("off", "0", "false"):
        return 0
    try:
        data = json.load(sys.stdin)
        got = extract(data.get("tool_name") or "", data.get("tool_input") or {}, str(data.get("cwd") or ""))
        if not got:
            return 0
        sys.path.insert(0, str(LINT_DIR))
        import comms_lint
        kind, body = got
        res = comms_lint.lint(kind, body)
        if res["ok"] or seen_before(kind, body):
            return 0
        lines = comms_lint.render(res).splitlines()
        report = "\n".join([ln for ln in lines[:-1] if ln.startswith("FAIL")][:8] + lines[-1:])
        reason = (f"Below the comms bar for a {res['kind']} write; rewrite it and resend.\n{report}\n"
                  "Template: .claude/skills/communication-structure/references/artifact-templates.md. "
                  "Add nothing the source lacks. A false positive: resend the identical text once and it goes through.")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": reason}}))
    except Exception:  # fail open: a broken quality hook must never block work
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
